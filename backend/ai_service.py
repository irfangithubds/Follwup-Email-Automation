import re
import httpx
from typing import Dict, Any, Optional, List
from backend.database import get_setting

TONE_PROMPTS = {
    "gentle": "Polite, considerate, warm, acknowledging they are busy, soft check-in without pressure.",
    "professional": "Direct, executive, clear, professional, concise, focused on decision or next action.",
    "value_add": "Collaborative, offering help, suggesting a short 10-minute alignment call or clarification.",
    "urgent": "Time-sensitive, polite yet emphasizing upcoming milestones or schedule requirements."
}

def clean_recipient_first_name(recipient_raw: str) -> str:
    if not recipient_raw:
        return "there"
    name = recipient_raw.split(";")[0].strip()
    if "<" in name:
        name = name.split("<")[0].strip()
    name = name.strip('"\' ')
    parts = name.split()
    if parts:
        first = parts[0]
        # Ignore titles
        if first.lower() in ["mr.", "ms.", "mrs.", "dr.", "eng."]:
            return parts[1] if len(parts) > 1 else name
        return first.capitalize()
    return "there"

def extract_core_topic(subject: str, body: str) -> str:
    clean_sub = re.sub(r'^(re|fwd|fw):\s*', '', subject, flags=re.IGNORECASE).strip()
    return clean_sub if clean_sub else "our recent discussion"

def format_attachment_reference(attachments: Optional[List[str]]) -> str:
    if not attachments:
        return ""
    # Filter out image artifacts
    valid_files = [f for f in attachments if not re.match(r'^image\d+\.(png|jpg|jpeg|gif)$', f, re.I)]
    if not valid_files:
        return ""
    
    first_file = valid_files[0]
    first_lower = first_file.lower()
    
    if any(ext in first_lower for ext in ['.xlsx', '.xls', '.csv']):
        if "evaluation" in first_lower:
            return f"the attached evaluation Excel sheet ({first_file})"
        elif "pricing" in first_lower or "commercial" in first_lower:
            return f"the attached commercial/pricing sheet ({first_file})"
        return f"the attached Excel file ({first_file})"
    elif ".pdf" in first_lower:
        if "proposal" in first_lower:
            return f"the attached proposal document ({first_file})"
        return f"the attached PDF document ({first_file})"
    elif any(ext in first_lower for ext in ['.docx', '.doc']):
        return f"the attached document ({first_file})"
    elif any(ext in first_lower for ext in ['.pptx', '.ppt']):
        return f"the attached presentation deck ({first_file})"
    
    return f"the attached file ({first_file})"

def clean_trail_text(text: str) -> str:
    """Clean signatures, quoted replies, disclaimers, and whitespace."""
    if not text:
        return ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    meaningful = []
    for l in lines:
        if l.startswith(">") or l.startswith("-----") or l.startswith("_____"):
            continue
        if any(l.lower().startswith(h) for h in ["from:", "sent:", "to:", "cc:", "subject:", "date:"]):
            continue
        if any(d in l.lower() for d in [
            "caution: this email originated", 
            "the information in this email is confidential",
            "you don't often get email from",
            "##- please type your reply above this line"
        ]):
            continue
        if any(s in l.lower() for s in ["best regards", "kind regards", "regards,", "sincerely", "thanks & regards"]):
            break
        meaningful.append(l)
    return " ".join(meaningful[:6]).strip()

def format_attachment_reference(attachments: Optional[List[str]]) -> str:
    if not attachments:
        return ""
    valid_files = [f for f in attachments if not re.match(r'^image\d+\.(png|jpg|jpeg|gif)$', f, re.I)]
    if not valid_files:
        return ""
    
    first_file = valid_files[0]
    first_lower = first_file.lower()
    
    if any(ext in first_lower for ext in ['.xlsx', '.xls', '.csv']):
        if "eval" in first_lower:
            return f"the completed technical evaluation sheet ({first_file})"
        elif "pricing" in first_lower or "commercial" in first_lower or "boq" in first_lower:
            return f"the commercial/pricing sheet ({first_file})"
        return f"the attached Excel file ({first_file})"
    elif ".pdf" in first_lower:
        if any(k in first_lower for k in ["proposal", "quotation", "quote", "renewal"]):
            return f"the submitted renewal proposal ({first_file})"
        return f"the attached PDF document ({first_file})"
    elif any(ext in first_lower for ext in ['.docx', '.doc']):
        return f"the attached document ({first_file})"
    elif any(ext in first_lower for ext in ['.pptx', '.ppt']):
        return f"the updated presentation deck ({first_file})"
    
    return f"the attached file ({first_file})"

from backend.research_service import get_research_intelligence

def generate_smart_builtin_draft(
    original_subject: str,
    original_body: str,
    recipient_name: str,
    days_waiting: int,
    tone: str = "gentle",
    custom_instruction: Optional[str] = None,
    sender_name: str = "Irfan",
    attachments: Optional[List[str]] = None,
    thread_trail: Optional[List[Dict[str, Any]]] = None,
    to_address: Optional[str] = None,
    include_intelligence: bool = True
) -> Dict[str, Any]:
    first_name = clean_recipient_first_name(recipient_name)
    clean_sub = re.sub(r'^(re|fwd|fw):\s*', '', original_subject, flags=re.IGNORECASE).strip()
    file_ref = format_attachment_reference(attachments)
    
    # Clean the last sent email body
    clean_last_sent = clean_trail_text(original_body)
    
    # Extract client and partner messages from thread trail (up to last 3 conversations)
    client_messages = []
    recent_trail_msgs = []
    if thread_trail:
        for msg in thread_trail:
            b = clean_trail_text(msg.get("body", "") or msg.get("snippet", ""))
            if b and "teams.microsoft.com" not in b:
                recent_trail_msgs.append(msg)
                if not msg.get("is_self", False):
                    client_messages.append({
                        "sender": msg.get("sender", ""),
                        "text": b,
                        "date": msg.get("date", "")
                    })
    
    last_client_msg = client_messages[-1] if client_messages else None
    
    # Combined context from subject, last sent email, and latest client request
    all_context = (clean_last_sent + " " + clean_sub + " " + (last_client_msg["text"] if last_client_msg else "")).lower()

    # Determine specific conversation theme and logical next step
    if "evaluation" in all_context or (file_ref and "evaluation" in file_ref.lower()):
        if file_ref:
            context_desc = f"{file_ref} which I shared for your team's review regarding \"{clean_sub}\""
            action_desc = "Could you please let me know if your team had an opportunity to review the filled evaluation sheet? We would be pleased to answer any questions or jump on a brief call if you need any walkthrough."
        else:
            context_desc = f"the technical evaluation form for \"{clean_sub}\""
            action_desc = "Kindly let me know if you have received feedback from your technical team or if any additional clarifications are required from our side."

    elif any(k in all_context for k in ["proposal", "renewal", "rfq", "quote", "commercial"]) or (file_ref and "proposal" in file_ref.lower()):
        if file_ref:
            context_desc = f"{file_ref} submitted for \"{clean_sub}\""
            action_desc = "Could you please share an update on the review status or let us know if any further commercial or technical details are needed to proceed with the next steps?"
        else:
            context_desc = f"the proposal submitted for \"{clean_sub}\""
            action_desc = "Kindly let me know if your team had a chance to review the proposal and if there are any questions we can assist with."

    elif any(k in all_context for k in ["slide#", "slide #", "deck", "presentation", "pptx"]) or (file_ref and "deck" in file_ref):
        if file_ref:
            context_desc = f"{file_ref} with the updated revisions shared for \"{clean_sub}\""
            action_desc = "Could you please confirm if the updated slides meet your expectations, or if you would like any further adjustments made?"
        else:
            context_desc = f"the updated presentation deck shared for \"{clean_sub}\""
            action_desc = "Please let me know if you need any adjustments or if everything is aligned for our next discussion."

    elif any(k in all_context for k in ["demo", "demonstration", "walkthrough"]):
        context_desc = f"our recent demo and discussions regarding \"{clean_sub}\""
        action_desc = "Could you please share your team's thoughts following the session, and let us know how you would like to proceed with the next milestones?"

    elif any(k in all_context for k in ["reschedule", "rescheduling", "meeting", "call"]):
        context_desc = f"the scheduling of our meeting for \"{clean_sub}\""
        action_desc = "Could you please suggest a convenient day and time that works best for you and your team to reconnect?"

    else:
        if file_ref:
            context_desc = f"{file_ref} shared for \"{clean_sub}\""
            action_desc = "Could you please let me know if your team had a chance to review, or if any additional details are needed from our side?"
        else:
            context_desc = f"my previous note regarding \"{clean_sub}\""
            action_desc = "Kindly let me know if you had an opportunity to review, or if there is anything we can assist with to move this forward."

    # Retrieve live research intelligence (Prospect News + Solution Product Innovation)
    intel = {}
    hook_paragraph = ""
    if include_intelligence:
        try:
            intel = get_research_intelligence(
                subject=original_subject,
                body=original_body,
                to_address=to_address or "",
                recipient_name=recipient_name,
                thread_trail=thread_trail
            )
            hook_paragraph = intel.get("combined_hook", "")
        except Exception as e:
            print(f"Intelligence lookup notice: {e}")

    # Construct tone-specific email
    if tone == "professional":
        greeting = f"Dear {first_name},"
        opening = f"I am writing to follow up on {context_desc}."
        closing = "Looking forward to your guidance."
    elif tone == "value_add":
        greeting = f"Hi {first_name},"
        opening = f"Hope you are having a productive week.\n\nI am circling back on {context_desc}."
        action_desc += "\n\nI would be more than happy to arrange a brief 10-15 minute sync if you or the team would like to review this together."
        closing = "Please let me know what day and time suits you best."
    elif tone == "urgent":
        greeting = f"Dear {first_name},"
        opening = f"Hope all is well with you.\n\nI am writing to check in on {context_desc}."
        action_desc = f"As we are finalizing our project schedules and upcoming milestones, your guidance on this would be greatly appreciated to keep everything on track."
        closing = "Could you please provide a brief update at your earliest convenience?"
    else: # gentle / default
        greeting = f"Hi {first_name},"
        opening = f"Hope you are doing well.\n\nJust wanted to gently check in on {context_desc}."
        closing = "Whenever you have a moment, please let me know your thoughts."

    custom_add = f"\n\nNote: {custom_instruction.strip()}" if custom_instruction else ""
    
    if hook_paragraph and include_intelligence:
        draft_body = f"{greeting}\n\n{opening}\n\n{hook_paragraph}\n\n{action_desc}{custom_add}\n\n{closing}"
    else:
        draft_body = f"{greeting}\n\n{opening}\n\n{action_desc}{custom_add}\n\n{closing}"

    subject_prefix = "Follow-up: " if not original_subject.lower().startswith("re:") else ""
    draft_subject = f"{subject_prefix}{original_subject}"

    return {
        "subject": draft_subject,
        "body": draft_body,
        "engine": "Contextual AI & Market Intelligence Engine",
        "company_news": intel.get("top_news", ""),
        "solution_highlight": f"{intel.get('solution_name')}: {intel.get('solution_headline')}" if intel else "",
        "research_intel": intel
    }

async def generate_llm_draft(
    original_subject: str,
    original_body: str,
    recipient_name: str,
    days_waiting: int,
    tone: str = "gentle",
    custom_instruction: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    thread_trail: Optional[List[Dict[str, Any]]] = None,
    to_address: Optional[str] = None,
    include_intelligence: bool = True
) -> Dict[str, Any]:
    """Generates draft using OpenAI, Gemini, Anthropic, or falls back to Smart Engine."""
    provider = get_setting("ai_provider", "smart_builtin")
    sender_name = get_setting("sender_name", "Irfan")
    tone_desc = TONE_PROMPTS.get(tone, TONE_PROMPTS["gentle"])
    
    clean_body_excerpt = original_body[:3000].strip()

    # Format attachments for prompt
    valid_attachments = [f for f in (attachments or []) if not re.match(r'^image\d+\.(png|jpg|jpeg|gif)$', f, re.I)]
    attachments_str = ", ".join(valid_attachments) if valid_attachments else "None (No non-image files attached)"

    # Format chronological conversation trail (focus on last 3-4 messages)
    trail_formatted_lines = []
    if thread_trail:
        recent_subset = thread_trail[-4:] if len(thread_trail) > 4 else thread_trail
        for i, msg in enumerate(recent_subset, 1):
            sender = msg.get("sender", "Unknown")
            date_str = msg.get("date", "")
            snip = msg.get("body", "") or msg.get("snippet", "")
            atts = msg.get("attachments", [])
            att_info = f" [Attached: {', '.join(atts)}]" if atts else ""
            trail_formatted_lines.append(f"{i}. [{date_str}] From: {sender}{att_info}\n   Message excerpt: {snip}")
    
    trail_str = "\n\n".join(trail_formatted_lines) if trail_formatted_lines else "No previous messages in trail."

    # Retrieve live research intelligence
    intel = {}
    intel_prompt_block = ""
    if include_intelligence:
        try:
            intel = get_research_intelligence(
                subject=original_subject,
                body=original_body,
                to_address=to_address or "",
                recipient_name=recipient_name,
                thread_trail=thread_trail
            )
            intel_prompt_block = f"""
LIVE RESEARCHED PROSPECT COMPANY NEWS & SOLUTION INNOVATIONS:
- Prospect Company: {intel['company']}
- Latest Company Milestone / News: {intel['top_news'] or 'Active expansion and Vision 2030 initiatives in Saudi Arabia'}
- Relevant Solution Partner: {intel['solution_name']}
- Latest Solution Innovation / Update: {intel['solution_headline']} — {intel['solution_summary']}

CRITICAL INSTRUCTIONS FOR INCORPORATING RESEARCH:
1. First, anchor the email in the previous email trail and explicitly reference any deliverables or files attached (e.g. {attachments_str}).
2. Include a thoughtful, natural mention acknowledging their company's recent milestone/momentum ({intel['company']}), showing you are genuinely informed.
3. Bridge this smoothly to how {intel['solution_name']} has recently evolved to help them address these exact enterprise/workforce needs.
4. Keep the email concise, executive, and non-generic (3 to 4 short paragraphs total).
5. Conclude with a clear, polite next step or offer for a 10-15 minute walk-through.
6. Do NOT include any signoff or signature block.
"""
        except Exception as e:
            print(f"Intel lookup error: {e}")

    system_prompt = f"""You are an elite executive assistant drafting context-aware follow-up email replies for {sender_name}.
Tone requested: {tone.upper()} ({tone_desc})
Target Recipient: {recipient_name}
Days elapsed since last email: {days_waiting} days.

CRITICAL CONTEXT & ATTACHMENT RULES:
1. Examine the email subject, latest message, conversation trail, and attached files.
2. Focus especially on the LAST 3 CONVERSATIONS in the email trail:
   - What did the recipient ask for or discuss previously (e.g. evaluation form, demo feedback, quotation, meeting schedule)?
   - What did {sender_name} share or promise in the very last email (e.g. sharing the filled technical evaluation sheet, submitting a proposal, sending revised slides)?
3. If files were attached (e.g., Excel evaluation sheets like .xlsx, proposal PDFs, price quotes, slide decks), YOU MUST EXPLICITLY REFER TO THEM BY NAME OR PURPOSE in your follow-up note (e.g., "Following up on the completed technical evaluation form (LMS Features - Cornerstone - Albawani Evaluation.xlsx) I shared...").
4. Write in the first person as {sender_name}.
5. Keep it natural, polite, and concise (1 to 3 short paragraphs).
6. Do NOT include any signoff or signature block (e.g. do NOT write 'Best Regards', 'Sincerely', or your name at the bottom). The corporate HTML signature is appended automatically.
7. Return ONLY the email body text. Do not add quotes, introductory commentary, or subject line.
{intel_prompt_block}
"""

    user_prompt = f"""Original Subject: {original_subject}
Attached Files in This Email:
{attachments_str}

Latest Sent Email Body:
---
{clean_body_excerpt}
---

Recent Conversation Trail (Last 3-4 Chronological Interactions):
---
{trail_str}
---

Additional User Instructions:
{custom_instruction if custom_instruction else 'None. Follow requested tone and reference attachments/context accurately.'}

Please draft the follow-up email response:"""

    try:
        # 1. OpenAI
        if provider == "openai":
            api_key = get_setting("openai_api_key")
            model = get_setting("openai_model", "gpt-4o-mini")
            if api_key:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            "temperature": 0.7
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        generated_text = data["choices"][0]["message"]["content"].strip()
                        return {
                            "subject": f"Follow-up: {original_subject}" if not original_subject.lower().startswith("re:") else original_subject,
                            "body": generated_text,
                            "engine": f"OpenAI ({model}) + Market Intelligence",
                            "company_news": intel.get("top_news", ""),
                            "solution_highlight": f"{intel.get('solution_name')}: {intel.get('solution_headline')}" if intel else "",
                            "research_intel": intel
                        }

        # 2. Google Gemini
        elif provider == "gemini":
            api_key = get_setting("gemini_api_key")
            model = get_setting("gemini_model", "gemini-1.5-flash")
            if api_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        url,
                        json={
                            "contents": [
                                {"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
                            ],
                            "generationConfig": {"temperature": 0.7}
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        generated_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return {
                            "subject": f"Follow-up: {original_subject}" if not original_subject.lower().startswith("re:") else original_subject,
                            "body": generated_text,
                            "engine": f"Gemini ({model}) + Market Intelligence",
                            "company_news": intel.get("top_news", ""),
                            "solution_highlight": f"{intel.get('solution_name')}: {intel.get('solution_headline')}" if intel else "",
                            "research_intel": intel
                        }

        # 3. Anthropic Claude
        elif provider == "anthropic":
            api_key = get_setting("anthropic_api_key")
            model = get_setting("anthropic_model", "claude-3-5-haiku-20241022")
            if api_key:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json"
                        },
                        json={
                            "model": model,
                            "max_tokens": 800,
                            "system": system_prompt,
                            "messages": [{"role": "user", "content": user_prompt}],
                            "temperature": 0.7
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        generated_text = data["content"][0]["text"].strip()
                        return {
                            "subject": f"Follow-up: {original_subject}" if not original_subject.lower().startswith("re:") else original_subject,
                            "body": generated_text,
                            "engine": f"Anthropic ({model}) + Market Intelligence",
                            "company_news": intel.get("top_news", ""),
                            "solution_highlight": f"{intel.get('solution_name')}: {intel.get('solution_headline')}" if intel else "",
                            "research_intel": intel
                        }

    except Exception as e:
        print(f"Error calling {provider} API: {e}. Falling back to Smart Engine.")

    # Fallback to Smart Built-in
    return generate_smart_builtin_draft(
        original_subject=original_subject,
        original_body=original_body,
        recipient_name=recipient_name,
        days_waiting=days_waiting,
        tone=tone,
        custom_instruction=custom_instruction,
        sender_name=sender_name,
        attachments=attachments,
        thread_trail=thread_trail,
        to_address=to_address,
        include_intelligence=include_intelligence
    )
