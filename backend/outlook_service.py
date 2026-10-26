import pythoncom
import win32com.client
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import re
import html
from backend.database import get_reviewed_status_map, update_email_status
from backend.signature_service import get_active_signature_html

def clean_html_to_text(html_content: str) -> str:
    """Utility to extract clean readable text from HTML email bodies."""
    if not html_content:
        return ""
    # Remove script and style elements
    text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html_content, flags=re.IGNORECASE)
    text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', text, flags=re.IGNORECASE)
    # Replace breaks and paragraph ends with newlines
    text = re.sub(r'<(br|/p|/div|/tr)>', '\n', text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean up excess whitespace
    lines = [line.strip() for line in text.split('\n')]
    clean_lines = [l for l in lines if l]
    return '\n'.join(clean_lines)

def get_outlook_accounts() -> List[Dict[str, str]]:
    """List available Outlook mail stores/accounts."""
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        accounts = []
        for store in mapi.Stores:
            name = store.DisplayName
            # Check if store has a Sent Items folder
            try:
                sent = store.GetDefaultFolder(5)
                accounts.append({
                    "name": name,
                    "email": name if "@" in name else store.FilePath,
                    "total_sent": sent.Items.Count
                })
            except Exception:
                continue
        return accounts
    finally:
        pythoncom.CoUninitialize()

def get_sent_emails(
    account_filter: Optional[str] = None,
    days_back: int = 90,
    min_days_waiting: int = 2,
    limit: int = 300
) -> List[Dict[str, Any]]:
    """
    Fetch sent emails from the past N days.
    Checks conversations to identify which emails received a reply and which need follow-up.
    """
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        
        # Calculate date cutoff
        now = datetime.now()
        dt_cutoff = (now - timedelta(days=days_back)).strftime("%m/%d/%Y %H:%M")
        filter_str = f"[SentOn] >= '{dt_cutoff}' AND [MessageClass] = 'IPM.Note'"
        
        status_map = get_reviewed_status_map()
        results = []
        seen_threads = set()

        for store in mapi.Stores:
            store_name = store.DisplayName
            if account_filter and account_filter != "all" and account_filter.lower() not in store_name.lower():
                continue
            
            try:
                sent_folder = store.GetDefaultFolder(5) # olFolderSentMail
            except Exception:
                continue

            try:
                items = sent_folder.Items.Restrict(filter_str)
                items.Sort("[SentOn]", True)
            except Exception as e:
                print(f"Error querying store {store_name}: {e}")
                continue

            count = items.Count
            for i in range(1, min(count + 1, limit)):
                try:
                    item = items.Item(i)
                    entry_id = getattr(item, "EntryID", "")
                    if not entry_id:
                        continue
                    
                    subject = getattr(item, "Subject", "(No Subject)")
                    to_address = getattr(item, "To", "")
                    cc_address = getattr(item, "CC", "")
                    sent_on = item.SentOn # Returns datetime object
                    
                    # Convert sent_on to ISO string and calculate elapsed days
                    if hasattr(sent_on, "timestamp"):
                        sent_dt = datetime.fromtimestamp(sent_on.timestamp(), tz=timezone.utc)
                    else:
                        sent_dt = sent_on
                    
                    now_utc = datetime.now(timezone.utc)
                    days_elapsed = (now_utc - sent_dt).total_seconds() / 86400.0
                    days_elapsed_int = int(days_elapsed)
                    
                    # Conversation tracking: check if recipient replied
                    conv = None
                    try:
                        conv = item.GetConversation()
                    except Exception:
                        pass
                    
                    has_replied = False
                    last_reply_from = None
                    last_reply_time = None
                    
                    if conv:
                        try:
                            table = conv.GetTable()
                            while not table.EndOfTable:
                                row = table.GetNextRow()
                                try:
                                    eid = row["EntryID"]
                                    if eid == entry_id:
                                        continue
                                    conv_msg = mapi.GetItemFromID(eid)
                                    recv_time = getattr(conv_msg, "ReceivedTime", None)
                                    if recv_time and recv_time > sent_on:
                                        sender_name = getattr(conv_msg, "SenderName", "")
                                        sender_email = getattr(conv_msg, "SenderEmailAddress", "")
                                        # Check if sender is not current user
                                        if "mirfan" not in sender_email.lower() and "mirfan" not in sender_name.lower():
                                            has_replied = True
                                            last_reply_from = sender_name or sender_email
                                            last_reply_time = recv_time.strftime("%Y-%m-%d %H:%M")
                                            break
                                except Exception:
                                    continue
                        except Exception:
                            pass
                    
                    # Determine status
                    db_entry = status_map.get(entry_id, {})
                    db_status = db_entry.get("status")
                    
                    if db_status:
                        computed_status = db_status
                    elif has_replied:
                        computed_status = "replied"
                    elif days_elapsed_int >= min_days_waiting:
                        computed_status = "needs_followup"
                    else:
                        computed_status = "recent_pending"
                        
                    # Extract body text snippet
                    raw_body = getattr(item, "Body", "")
                    clean_body = raw_body.strip()
                    # First 300 characters for list snippet
                    snippet = clean_body[:250].replace("\r", " ").replace("\n", " ").strip()
                    if len(clean_body) > 250:
                        snippet += "..."
                    
                    # Clean recipient display name
                    recipient_clean = to_address.split(";")[0].strip() if to_address else "Unknown"
                    if "<" in recipient_clean:
                        recipient_name = recipient_clean.split("<")[0].strip().strip('"')
                    else:
                        recipient_name = recipient_clean

                    results.append({
                        "entry_id": entry_id,
                        "account": store_name,
                        "subject": subject,
                        "to": to_address,
                        "cc": cc_address,
                        "recipient_name": recipient_name,
                        "sent_on": sent_dt.isoformat(),
                        "sent_on_formatted": sent_dt.strftime("%b %d, %Y %I:%M %p"),
                        "days_waiting": days_elapsed_int,
                        "has_replied": has_replied,
                        "last_reply_from": last_reply_from,
                        "last_reply_time": last_reply_time,
                        "status": computed_status,
                        "snippet": snippet,
                        "body": clean_body[:5000], # Cap for payload size
                        "saved_draft": db_entry.get("draft_body", "")
                    })
                except Exception as ex:
                    continue

        return results
    finally:
        pythoncom.CoUninitialize()

def get_single_email(entry_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full detail for a single sent email thread."""
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        item = mapi.GetItemFromID(entry_id)
        if not item:
            return None
        
        subject = getattr(item, "Subject", "(No Subject)")
        to_address = getattr(item, "To", "")
        cc_address = getattr(item, "CC", "")
        body = getattr(item, "Body", "")
        html_body = getattr(item, "HTMLBody", "")
        sent_on = item.SentOn
        
        status_map = get_reviewed_status_map()
        db_entry = status_map.get(entry_id, {})
        
        return {
            "entry_id": entry_id,
            "subject": subject,
            "to": to_address,
            "cc": cc_address,
            "body": body,
            "html_body": html_body,
            "sent_on": sent_on.strftime("%b %d, %Y %I:%M %p"),
            "status": db_entry.get("status", "needs_followup"),
            "saved_draft": db_entry.get("draft_body", ""),
            "saved_subject": db_entry.get("draft_subject", f"Follow-up: {subject}")
        }
    except Exception as e:
        print(f"Error fetching email {entry_id}: {e}")
        return None
    finally:
        pythoncom.CoUninitialize()

def clean_recipient_list(addr_str: str, exclude_patterns: list) -> str:
    """Filter out user's own email from recipient lists."""
    if not addr_str:
        return ""
    parts = [p.strip() for p in addr_str.split(";") if p.strip()]
    cleaned = [p for p in parts if not any(x.lower() in p.lower() for x in exclude_patterns)]
    return "; ".join(cleaned)

def send_followup_email(
    entry_id: str,
    draft_body: str,
    draft_subject: Optional[str] = None,
    to: Optional[str] = None,
    cc: Optional[str] = None
) -> Dict[str, Any]:
    """
    Approve and send follow-up reply email via Outlook.
    Explicitly addresses the client recipient (original_item.To) instead of self.
    """
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        original_item = mapi.GetItemFromID(entry_id)
        
        # Create reply item
        reply = original_item.ReplyAll() if original_item.CC else original_item.Reply()
        
        # CRITICAL FIX: When replying to a Sent Items message, Outlook sets reply.To to the
        # sender (the current user). We MUST explicitly set reply.To to the client recipient!
        client_to = to.strip() if to and to.strip() else original_item.To
        
        # Clean out current user's email if accidentally present in To or CC
        user_patterns = ["mirfan@ensaantech.com", "mirfan@squareonemea.com"]
        cleaned_to = clean_recipient_list(client_to, user_patterns) or client_to
        reply.To = cleaned_to
        
        if cc is not None and cc.strip():
            reply.CC = clean_recipient_list(cc.strip(), user_patterns)
        elif original_item.CC:
            reply.CC = clean_recipient_list(original_item.CC, user_patterns)
            
        if draft_subject:
            reply.Subject = draft_subject
            
        # Format HTML body with clean styling and active signature above quoted history
        formatted_content = draft_body.replace("\n", "<br>")
        signature_html = get_active_signature_html(use_base64_img=True)
        styled_html = f"""
        <div style="font-family: Calibri, 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1f2937; line-height: 1.5;">
            {formatted_content}
        </div>
        {signature_html}
        <br>
        """
        reply.HTMLBody = styled_html + reply.HTMLBody
        
        # Send immediately via Outlook
        reply.Send()
        
        # Record status in database
        update_email_status(
            entry_id=entry_id,
            status="approved_sent",
            draft_subject=draft_subject or reply.Subject,
            draft_body=draft_body
        )
        
        return {
            "success": True,
            "message": f"Follow-up email sent successfully to {cleaned_to}!",
            "entry_id": entry_id,
            "to": cleaned_to,
            "subject": draft_subject or reply.Subject
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        pythoncom.CoUninitialize()

def save_draft_in_outlook(
    entry_id: str,
    draft_body: str,
    draft_subject: Optional[str] = None,
    to: Optional[str] = None,
    cc: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create and save reply draft into Outlook's 'Drafts' folder.
    Explicitly addresses client recipient (original_item.To).
    """
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        original_item = mapi.GetItemFromID(entry_id)
        
        reply = original_item.ReplyAll() if original_item.CC else original_item.Reply()
        
        # Explicitly set To to client recipient
        client_to = to.strip() if to and to.strip() else original_item.To
        user_patterns = ["mirfan@ensaantech.com", "mirfan@squareonemea.com"]
        cleaned_to = clean_recipient_list(client_to, user_patterns) or client_to
        reply.To = cleaned_to
        
        if cc is not None and cc.strip():
            reply.CC = clean_recipient_list(cc.strip(), user_patterns)
        elif original_item.CC:
            reply.CC = clean_recipient_list(original_item.CC, user_patterns)
            
        if draft_subject:
            reply.Subject = draft_subject
            
        formatted_content = draft_body.replace("\n", "<br>")
        signature_html = get_active_signature_html(use_base64_img=True)
        styled_html = f"""
        <div style="font-family: Calibri, 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1f2937; line-height: 1.5;">
            {formatted_content}
        </div>
        {signature_html}
        <br>
        """
        reply.HTMLBody = styled_html + reply.HTMLBody
        
        # Save to Outlook Drafts folder
        reply.Save()
        
        # Update database
        update_email_status(
            entry_id=entry_id,
            status="saved_draft",
            draft_subject=draft_subject or reply.Subject,
            draft_body=draft_body
        )
        
        return {
            "success": True,
            "message": f"Draft created for {cleaned_to} and saved to Outlook Drafts folder!",
            "entry_id": entry_id,
            "to": cleaned_to
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        pythoncom.CoUninitialize()
