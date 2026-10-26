import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from backend.database import (
    init_db,
    get_all_settings,
    set_setting,
    get_setting,
    update_email_status
)
from backend.outlook_service import (
    get_outlook_accounts,
    get_sent_emails,
    get_single_email,
    get_email_thread_trail,
    send_followup_email,
    save_draft_in_outlook
)
from backend.ai_service import generate_llm_draft
from backend.signature_service import get_active_signature_html

# Initialize DB on start
init_db()

app = FastAPI(title="Ensaan FollowUp Copilot API", version="1.0.0")

# Request Models
class GenerateDraftRequest(BaseModel):
    entry_id: Optional[str] = None
    original_subject: str
    original_body: str
    recipient_name: str
    days_waiting: int
    tone: Optional[str] = "gentle"
    custom_instruction: Optional[str] = None
    attachments: Optional[List[str]] = None
    thread_trail: Optional[List[Dict[str, Any]]] = None

class SendEmailRequest(BaseModel):
    entry_id: str
    draft_body: str
    draft_subject: Optional[str] = None
    to: Optional[str] = None
    cc: Optional[str] = None

class StatusUpdateRequest(BaseModel):
    entry_id: str
    status: str
    notes: Optional[str] = None
    snooze_days: Optional[int] = 3

class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]

# --- API Endpoints ---

@app.get("/api/accounts")
def list_accounts():
    """List available Outlook mail accounts."""
    try:
        return {"accounts": get_outlook_accounts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/signature")
def get_signature(dark: bool = True):
    """Retrieve active HTML signature with working links and design."""
    try:
        return {"html": get_active_signature_html(use_base64_img=True, is_dark_preview=dark)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/emails")
def list_sent_emails(
    account: Optional[str] = None,
    days_back: int = Query(default=90, ge=1, le=365),
    min_days: int = Query(default=2, ge=0, le=60),
    status: Optional[str] = "needs_followup",
    search: Optional[str] = None
):
    """Retrieve filtered sent emails with conversation reply detection."""
    try:
        emails = get_sent_emails(
            account_filter=account,
            days_back=days_back,
            min_days_waiting=min_days
        )
        
        # Apply status filter
        if status and status != "all":
            emails = [e for e in emails if e["status"] == status]
            
        # Apply keyword search
        if search:
            q = search.lower()
            emails = [
                e for e in emails if
                q in e["subject"].lower() or
                q in e["to"].lower() or
                q in e["recipient_name"].lower() or
                q in e["snippet"].lower()
            ]
            
        return {"emails": emails, "count": len(emails)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/email/{entry_id}")
def get_email_detail(entry_id: str):
    """Retrieve full content of a specific sent email."""
    data = get_single_email(entry_id)
    if not data:
        raise HTTPException(status_code=404, detail="Email not found")
    return data

@app.post("/api/generate-draft")
async def generate_draft(req: GenerateDraftRequest):
    """Generate an AI-powered follow-up email draft."""
    try:
        thread_trail = req.thread_trail
        if req.entry_id and not thread_trail:
            try:
                thread_trail = get_email_thread_trail(req.entry_id)
            except Exception:
                thread_trail = []

        result = await generate_llm_draft(
            original_subject=req.original_subject,
            original_body=req.original_body,
            recipient_name=req.recipient_name,
            days_waiting=req.days_waiting,
            tone=req.tone,
            custom_instruction=req.custom_instruction,
            attachments=req.attachments,
            thread_trail=thread_trail
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/send")
def send_email(req: SendEmailRequest):
    """Approve and send follow-up email directly via Outlook."""
    result = send_followup_email(
        entry_id=req.entry_id,
        draft_body=req.draft_body,
        draft_subject=req.draft_subject,
        to=req.to,
        cc=req.cc
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send"))
    return result

@app.post("/api/save-draft")
def save_draft(req: SendEmailRequest):
    """Save follow-up draft to Outlook Drafts folder."""
    result = save_draft_in_outlook(
        entry_id=req.entry_id,
        draft_body=req.draft_body,
        draft_subject=req.draft_subject,
        to=req.to,
        cc=req.cc
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to save draft"))
    return result

@app.post("/api/dismiss")
def dismiss_email(req: StatusUpdateRequest):
    """Dismiss email from the follow-up queue."""
    update_email_status(
        entry_id=req.entry_id,
        status="dismissed",
        notes=req.notes
    )
    return {"success": True, "message": "Email dismissed"}

@app.post("/api/snooze")
def snooze_email(req: StatusUpdateRequest):
    """Snooze follow-up for a specified number of days."""
    snooze_until = (datetime.now() + timedelta(days=req.snooze_days or 3)).isoformat()
    update_email_status(
        entry_id=req.entry_id,
        status="snoozed",
        snooze_until=snooze_until,
        notes=req.notes
    )
    return {"success": True, "message": f"Snoozed for {req.snooze_days} days"}

@app.get("/api/stats")
def get_stats(days_back: int = 90, account: Optional[str] = None):
    """Get metrics and counters for dashboard overview."""
    try:
        all_emails = get_sent_emails(account_filter=account, days_back=days_back, min_days_waiting=0)
        
        total_sent = len(all_emails)
        awaiting_reply = len([e for e in all_emails if e["status"] == "needs_followup"])
        replied = len([e for e in all_emails if e["status"] == "replied"])
        approved_sent = len([e for e in all_emails if e["status"] == "approved_sent"])
        saved_draft = len([e for e in all_emails if e["status"] == "saved_draft"])
        dismissed = len([e for e in all_emails if e["status"] == "dismissed"])
        
        return {
            "total_sent": total_sent,
            "awaiting_reply": awaiting_reply,
            "replied": replied,
            "approved_sent": approved_sent,
            "saved_draft": saved_draft,
            "dismissed": dismissed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
def fetch_settings():
    """Retrieve app settings."""
    settings = get_all_settings()
    # Mask API keys partially for security
    masked = dict(settings)
    for k in ["openai_api_key", "gemini_api_key", "anthropic_api_key"]:
        val = masked.get(k, "")
        if val and len(val) > 8:
            masked[k + "_masked"] = val[:4] + "..." + val[-4:]
            masked[k + "_set"] = True
        else:
            masked[k + "_masked"] = ""
            masked[k + "_set"] = False
    return masked

@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest):
    """Save app settings."""
    for k, v in req.settings.items():
        if v is not None:
            set_setting(k, str(v))
    return {"success": True, "message": "Settings updated successfully"}

# Serve frontend static assets
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
