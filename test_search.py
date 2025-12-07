"""Quick check of MongoDB leads"""
import sys
sys.path.insert(0, "scripts")
from db_client import get_db

db = get_db()
leads = list(db.leads.find({}))

print(f"\n{'='*80}")
print(f"LEADS IN MONGODB: {len(leads)}")
print(f"{'='*80}")

for lead in leads:
    name = lead.get('channel_name', 'Unknown')[:35]
    subs = lead.get('subscriber_count')
    subs_str = f"{subs:,}" if subs else "?"
    tier = lead.get('subscriber_tier', '?')
    score = lead.get('pre_score', '?')
    subject = lead.get('subject_classification', {}).get('subject_tier', '?')
    matched = lead.get('subject_classification', {}).get('matched_keywords', [])[:3]
    
    tier_emoji = {"sweet_spot": "⭐", "big": "🔥", "small": "📈", "unknown": "❓"}.get(tier, "")
    
    print(f"{name:35} | {subs_str:>12} subs | {tier:12} {tier_emoji} | score: {score:2} | {subject} {matched}")
