#!/usr/bin/env python3
"""
MongoDB Client for EulaIQ Outreach Pipeline.

This module provides a centralized interface for all database operations.
It manages the 'leads' collection with full CRUD + specialized queries.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pymongo import MongoClient
from pymongo.collection import Collection
from bson import ObjectId
from dotenv import load_dotenv

import sys

load_dotenv()

# MongoDB Connection - pick from environment variables. Do NOT hard-code credentials.
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGODB_DEV")
if not MONGODB_URI:
    print("⚠️ ERROR: No MongoDB URI found in environment. Please copy .env.example -> .env and set MONGODB_URI.")
    sys.exit(1)
DATABASE_NAME = "eulaiq_outreach"
LEADS_COLLECTION = "leads"

# Followup Pattern (days after initial outreach)
FOLLOWUP_PATTERN = [3, 7, 10, 15]


class LeadStatus:
    """Enum-like class for lead statuses."""
    QUALIFIED = "qualified"           # Just qualified, no asset yet
    ASSET_GENERATING = "asset_generating"
    ASSET_GENERATED = "asset_generated"
    DRAFTED = "drafted"               # Email drafted, pending review
    READY_TO_SEND = "ready_to_send"   # Approved for sending
    SENT = "sent"                     # Initial outreach sent
    FOLLOWUP_1 = "followup_1"         # After 3-day followup
    FOLLOWUP_2 = "followup_2"         # After 7-day followup
    FOLLOWUP_3 = "followup_3"         # After 10-day followup
    FOLLOWUP_4 = "followup_4"         # After 15-day followup
    REPLIED = "replied"               # Creator responded
    CONVERTED = "converted"           # Closed deal
    UNSUBSCRIBED = "unsubscribed"     # Requested no contact
    DEAD = "dead"                     # No response after all followups


class OutreachDB:
    """MongoDB client for the outreach pipeline."""
    
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.leads: Collection = self.db[LEADS_COLLECTION]
        
        # Ensure indexes for common queries
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Create indexes for performance."""
        self.leads.create_index("channel_id", unique=True)
        self.leads.create_index("status")
        self.leads.create_index("next_followup_date")
        self.leads.create_index("email")
    
    # ==================== CREATE ====================
    
    def create_lead(self, lead_data: Dict[str, Any]) -> str:
        """
        Insert a new qualified lead into the database.
        Returns the inserted document's _id as string.
        """
        now = datetime.utcnow()
        
        document = {
            # Core Identity
            "channel_id": lead_data["channel_id"],
            "channel_name": lead_data["channel_name"],
            "creator_name": lead_data.get("creator_name", lead_data["channel_name"]),
            "email": lead_data.get("email"),
            
            # Video Context
            "video_id": lead_data.get("video_id") or lead_data.get("lead_id"),
            "video_title": lead_data.get("video_title"),
            "video_url": lead_data.get("video_url"),
            "video_description": lead_data.get("description", ""),
            
            # Qualification
            "icp_score": lead_data.get("icp_score", 0),
            "icp_reason": lead_data.get("icp_reason", ""),
            "keyword_source": lead_data.get("keyword_source", ""),
            
            # Pipeline Status
            "status": LeadStatus.QUALIFIED,
            
            # Generated Asset
            "branded_player_url": None,
            "s3_video_url": None,
            "eulaiq_video_id": None,
            
            # Outreach
            "draft_email": {
                "subject": None,
                "body": None,
                "drafted_at": None
            },
            "sent_email": {
                "subject": None,
                "body": None,
                "sent_at": None,
                "sent_via": None
            },
            
            # Followup Management
            "reached_out_at": None,
            "next_followup_date": None,
            "followup_count": 0,
            "followup_thread": [],  # List of {date, type, content, response}
            
            # Conversation History (for replies)
            "conversation_history": [],  # List of {date, direction, content}
            
            # Timestamps
            "created_at": now,
            "updated_at": now,
            
            # Notes (for manual annotations)
            "notes": ""
        }
        
        result = self.leads.insert_one(document)
        return str(result.inserted_id)
    
    # ==================== READ ====================
    
    def get_lead_by_id(self, lead_id: str) -> Optional[Dict]:
        """Get a lead by MongoDB _id."""
        return self.leads.find_one({"_id": ObjectId(lead_id)})
    
    def get_lead_by_channel(self, channel_id: str) -> Optional[Dict]:
        """Get a lead by YouTube channel ID."""
        return self.leads.find_one({"channel_id": channel_id})
    
    def get_lead_by_email(self, email: str) -> Optional[Dict]:
        """Get a lead by email address."""
        return self.leads.find_one({"email": email})
    
    def get_leads_by_status(self, status: str) -> List[Dict]:
        """Get all leads with a specific status."""
        return list(self.leads.find({"status": status}))
    
    def get_leads_needing_followup(self, as_of: datetime = None) -> List[Dict]: # type: ignore
        """Get leads where next_followup_date is today or earlier."""
        if as_of is None:
            as_of = datetime.utcnow()
        
        # Include all leads with followup date <= today and not in terminal states
        terminal_states = [LeadStatus.REPLIED, LeadStatus.CONVERTED, LeadStatus.UNSUBSCRIBED, LeadStatus.DEAD]
        
        return list(self.leads.find({
            "next_followup_date": {"$lte": as_of},
            "status": {"$nin": terminal_states}
        }))
    
    def get_all_leads(self, limit: int = 100, skip: int = 0) -> List[Dict]:
        """Get all leads with pagination."""
        return list(self.leads.find().sort("created_at", -1).skip(skip).limit(limit))
    
    def search_leads(self, query: str) -> List[Dict]:
        """Search leads by name, channel, or email."""
        regex = {"$regex": query, "$options": "i"}
        return list(self.leads.find({
            "$or": [
                {"creator_name": regex},
                {"channel_name": regex},
                {"email": regex}
            ]
        }))
    
    def channel_exists(self, channel_id: str) -> bool:
        """Check if a channel is already in the database."""
        return self.leads.count_documents({"channel_id": channel_id}) > 0
    
    # ==================== UPDATE ====================
    
    def update_lead(self, lead_id: str, updates: Dict[str, Any]) -> bool:
        """Generic update for a lead by _id."""
        updates["updated_at"] = datetime.utcnow()
        result = self.leads.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    def update_lead_by_channel(self, channel_id: str, updates: Dict[str, Any]) -> bool:
        """Update a lead by channel_id."""
        updates["updated_at"] = datetime.utcnow()
        result = self.leads.update_one(
            {"channel_id": channel_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    def set_asset_generated(self, channel_id: str, branded_url: str, s3_url: str = None, eulaiq_video_id: str = None): # type: ignore
        """Mark lead as having a generated asset."""
        self.update_lead_by_channel(channel_id, {
            "status": LeadStatus.ASSET_GENERATED,
            "branded_player_url": branded_url,
            "s3_video_url": s3_url,
            "eulaiq_video_id": eulaiq_video_id
        })
    
    def set_draft_email(self, channel_id: str, subject: str, body: str):
        """Save the draft email for a lead."""
        self.update_lead_by_channel(channel_id, {
            "status": LeadStatus.DRAFTED,
            "draft_email": {
                "subject": subject,
                "body": body,
                "drafted_at": datetime.utcnow()
            }
        })
    
    def mark_ready_to_send(self, channel_id: str):
        """Mark a draft as approved and ready to send."""
        self.update_lead_by_channel(channel_id, {
            "status": LeadStatus.READY_TO_SEND
        })
    
    def mark_sent(self, channel_id: str, subject: str, body: str, sent_via: str):
        """Mark lead as sent and schedule first followup."""
        now = datetime.utcnow()
        next_followup = now + timedelta(days=FOLLOWUP_PATTERN[0])
        
        self.leads.update_one(
            {"channel_id": channel_id},
            {
                "$set": {
                    "status": LeadStatus.SENT,
                    "reached_out_at": now,
                    "next_followup_date": next_followup,
                    "sent_email": {
                        "subject": subject,
                        "body": body,
                        "sent_at": now,
                        "sent_via": sent_via
                    },
                    "updated_at": now
                },
                "$push": {
                    "followup_thread": {
                        "date": now,
                        "type": "initial_outreach",
                        "content": {"subject": subject, "body": body},
                        "response": None
                    }
                }
            }
        )
    
    def record_followup_sent(self, channel_id: str, followup_number: int, subject: str, body: str):
        """Record a followup email and schedule the next one."""
        now = datetime.utcnow()
        
        # Determine next followup date (or None if this was the last)
        if followup_number < len(FOLLOWUP_PATTERN):
            next_followup = now + timedelta(days=FOLLOWUP_PATTERN[followup_number])
            next_status = f"followup_{followup_number}"
        else:
            next_followup = None
            next_status = LeadStatus.DEAD  # No more followups
        
        self.leads.update_one(
            {"channel_id": channel_id},
            {
                "$set": {
                    "status": next_status,
                    "next_followup_date": next_followup,
                    "followup_count": followup_number,
                    "updated_at": now
                },
                "$push": {
                    "followup_thread": {
                        "date": now,
                        "type": f"followup_{followup_number}",
                        "content": {"subject": subject, "body": body},
                        "response": None
                    }
                }
            }
        )
    
    def record_reply(self, channel_id: str, reply_content: str, reply_date: datetime = None): # pyright: ignore[reportArgumentType]
        """Record that the creator replied."""
        now = reply_date or datetime.utcnow()
        
        self.leads.update_one(
            {"channel_id": channel_id},
            {
                "$set": {
                    "status": LeadStatus.REPLIED,
                    "next_followup_date": None,
                    "updated_at": now
                },
                "$push": {
                    "conversation_history": {
                        "date": now,
                        "direction": "inbound",
                        "content": reply_content
                    }
                }
            }
        )
    
    def record_outbound_message(self, channel_id: str, content: str):
        """Record an outbound message in conversation history."""
        now = datetime.utcnow()
        
        self.leads.update_one(
            {"channel_id": channel_id},
            {
                "$set": {"updated_at": now},
                "$push": {
                    "conversation_history": {
                        "date": now,
                        "direction": "outbound",
                        "content": content
                    }
                }
            }
        )
    
    def add_note(self, channel_id: str, note: str):
        """Append a note to the lead's notes field."""
        now = datetime.utcnow()
        timestamped_note = f"[{now.isoformat()}] {note}\n"
        
        self.leads.update_one(
            {"channel_id": channel_id},
            {
                "$set": {"updated_at": now},
                "$push": {"notes": timestamped_note}  # Use concat if string, or change to array
            }
        )
        # Alternative: if notes is a string, use $concat or fetch-modify-save
    
    def update_email(self, channel_id: str, new_email: str):
        """Update the email address for a lead."""
        self.update_lead_by_channel(channel_id, {"email": new_email})
    
    def set_status(self, channel_id: str, status: str):
        """Manually set the status of a lead."""
        self.update_lead_by_channel(channel_id, {"status": status})
    
    # ==================== DELETE ====================
    
    def delete_lead(self, channel_id: str) -> bool:
        """Delete a lead by channel_id."""
        result = self.leads.delete_one({"channel_id": channel_id})
        return result.deleted_count > 0
    
    # ==================== STATS ====================
    
    def get_pipeline_stats(self) -> Dict[str, int]:
        """Get counts of leads in each status."""
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        results = list(self.leads.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}
    
    def get_total_leads(self) -> int:
        """Get total number of leads."""
        return self.leads.count_documents({})


# Singleton instance for convenience
_db_instance = None

def get_db() -> OutreachDB:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = OutreachDB()
    return _db_instance


# Quick test
if __name__ == "__main__":
    db = get_db()
    print(f"Connected to MongoDB. Total leads: {db.get_total_leads()}")
    print(f"Pipeline stats: {db.get_pipeline_stats()}")
