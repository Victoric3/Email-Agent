# Email Scheduler API Specification

## Overview
This endpoint accepts email details and a scheduled time, queues them, and sends them via SMTP (ZeptoMail) at the designated time.

## Endpoint
**URL:** `https://render.eulaiq.com/schedule-email`
**Method:** `POST`
**Content-Type:** `application/json`

## Request Payload

The endpoint should accept a JSON object with the following structure:

```json
{
  "sender": {
    "email": "victor@eulaiq.com",
    "username": "emailapikey",
    "password": "YOUR_SMTP_PASSWORD",
    "smtp_host": "smtp.zeptomail.com",
    "smtp_port": 587
  },
  "recipient": {
    "email": "client@example.com",
    "name": "Client Name"
  },
  "email": {
    "subject": "Subject Line",
    "body": "<html>Body content...</html>"
  },
  "schedule": {
    "send_at": "2025-12-12T14:30:00"
  }
}
```

### Field Descriptions

*   **sender**:
    *   `email`: The "From" address.
    *   `username`: SMTP username (e.g., for ZeptoMail).
    *   `password`: SMTP password/token.
    *   `smtp_host`: Hostname of the SMTP server (default: `smtp.zeptomail.com`).
    *   `smtp_port`: Port number (default: `587`).
*   **recipient**:
    *   `email`: The "To" address.
    *   `name`: Name of the recipient (optional, for logging).
*   **email**:
    *   `subject`: Email subject line.
    *   `body`: Email body content (HTML or Text).
*   **schedule**:
    *   `send_at`: ISO 8601 formatted date-time string indicating when the email should be sent.

## Expected Behavior

1.  **Validation**: Validate that all required fields are present.
2.  **Queueing**: Store the email task in a persistent queue or database.
3.  **Execution**:
    *   A background worker should monitor the queue.
    *   When `send_at` time is reached (or passed), the worker should attempt to send the email.
    *   Use the provided `sender` credentials to authenticate with the SMTP server.
4.  **Response**:
    *   Return `200 OK` or `201 Created` if the task was successfully queued.
    *   Return `400 Bad Request` if validation fails.
    *   Return `500 Internal Server Error` if queueing fails.

## Example Response

```json
{
  "status": "success",
  "message": "Email scheduled for 2025-12-12T14:30:00",
  "id": "unique_task_id_123"
}
```
