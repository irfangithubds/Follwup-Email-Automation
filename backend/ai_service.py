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

def generate_smart_builtin_draft(
    original_subject: str,
    original_body: str,
    recipient_name: str,
    days_waiting: int,
    tone: str = "gentle",
    custom_instruction: Optional[str] = None,
    sender_name: str = "Irfan",
    attachments: Optional[List[str]] = None,
    thread_trail: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, str]:
    first_name = clean_recipient_first_name(recipient_name)
    topic = extract_core_topic(original_subject, original_body)
    
    # Check attachments
    att_ref = format_attachment_reference(attachments)
    
    # Analyze body and thread trail for context
    body_lower = original_body.lower()
    trail_text = " ".join([t.get("snippet", "").lower() for t in (thread_trail or [])])
    combined_context = f"{body_lower} {trail_text}"

    has_evaluation = "evaluation" in combined_context or "form" in combined_context
    has_demo = "demo" in combined_context or "presentation" in combined_context
    has_proposal = any(k in combined_context for k in ["proposal", "quote", "commercial", "rfq", "pricing"])
    has_meeting = any(k in combined_context for k in ["meeting", "call", "schedule", "connect", "discussion"])

    # Construct intelligent contextual context sentence
    if att_ref:
        context_str = f"regarding {att_ref} on \"{topic}\""
    elif has_evaluation and has_demo:
        context_str = f"regarding the evaluation form following our demo on \"{topic}\""
    elif has_proposal:
        context_str = f"regarding the proposal shared for \"{topic}\""
    elif has_demo:
        context_str = f"following up on our recent demo and discussion for \"{topic}\""
    else:
        context_str = f"regarding \"{topic}\""

    # Construct tone-based draft
    if tone == "professional":
        greeting = f"Hi {first_name},"
        opening = f"I am following up on my previous email {context_str}."
        if att_ref:
            middle = f"Could you please let me know if your team had an opportunity to review {att_ref}? Please let me know if you need any adjustments or further clarifications from our side."
        elif has_proposal or has_evaluation:
            middle = "Could you please share a quick update on your team's feedback so we can plan the next steps accordingly?"
        else:
            middle = "Kindly let me know if you had an opportunity to review, or if any additional information is required from our side to proceed."
        closing = "Looking forward to your guidance."

    elif tone == "value_add":
        greeting = f"Dear {first_name},"
        opening = f"Hope you're having a productive week.\n\nI wanted to circle back on my last note {context_str}."
        if att_ref:
            middle = f"I would be glad to jump on a quick 10-15 minute sync if that helps answer any questions regarding {att_ref} or walk through any specific details together."
        else:
            middle = "I would be glad to jump on a quick 10-15 minute sync if that helps clarify any open points or address any specific requirements."
        closing = "Please let me know what day and time might work best for you."

    elif tone == "urgent":
        greeting = f"Hi {first_name},"
        opening = f"Hope all is well.\n\nI am writing to check in on the below thread {context_str}."
        if att_ref:
            middle = f"As we are organizing upcoming project deliverables and timelines, your feedback on {att_ref} would be greatly appreciated to keep everything on track."
        else:
            middle = "As we are organizing upcoming project deliverables and milestones, your input on this would be greatly appreciated to keep everything on track."
        closing = "Could you please provide a brief update at your earliest convenience?"

    else: # gentle / default
        greeting = f"Hi {first_name},"
        opening = f"Hope you are doing well.\n\nJust wanted to gently follow up on my previous email {context_str}."
        if att_ref:
            middle = f"I understand you have a busy schedule. Just checking if you had a chance to review {att_ref}, or if you require any additional information from our side."
        else:
            middle = "Whenever you have a moment, please let me know your thoughts or if there is anything else I can assist with."
        closing = "Have a great day ahead!"

    custom_add = ""
    if custom_instruction:
        custom_add = f"\n\nNote: {custom_instruction.strip()}"

    draft_body = f"{greeting}\n\n{opening}\n\n{middle}{custom_add}\n\n{closing}"
    
    subject_prefix = "Follow-up: " if not original_subject.lower().startswith("re:") else ""
    draft_subject = f"{subject_prefix}{original_subject}"

    return {
        "subject": draft_subject,
        "body": draft_body,
        "engine": "Built-in Smart Template (Context & Attachment Aware)"
    }

async def generate_llm_draft(
    original_subject: str,
    original_body: str,
    recipient_name: str,
    days_waiting: int,
    tone: str = "gentle",
    custom_instruction: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    thread_trail: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, str]:
    """Generates draft using OpenAI, Gemini, Anthropic, or falls back to Smart Engine."""
    provider = get_setting("ai_provider", "smart_builtin")
    sender_name = get_setting("sender_name", "Irfan")
    tone_desc = TONE_PROMPTS.get(tone, TONE_PROMPTS["gentle"])
    
    clean_body_excerpt = original_body[:3000].strip()

    # Format attachments for prompt
    valid_attachments = [f for f in (attachments or []) if not re.match(r'^image\d+\.(png|jpg|jpeg|gif)$', f, re.I)]
    attachments_str = ", ".join(valid_attachments) if valid_attachments else "None (No non-image files attached)"

    # Format chronological conversation trail
    trail_formatted_lines = []
    if thread_trail:
        for i, msg in enumerate(thread_trail, 1):
            sender = msg.get("sender", "Unknown")
            date_str = msg.get("date", "")
            snip = msg.get("snippet", "")
            atts = msg.get("attachments", [])
            att_info = f" [Attached: {', '.join(atts)}]" if atts else ""
            trail_formatted_lines.append(f"{i}. [{date_str}] From: {sender}{att_info}\n   Message excerpt: {snip}")
    
    trail_str = "\n\n".join(trail_formatted_lines) if trail_formatted_lines else "No previous messages in trail."

    system_prompt = f"""You are an elite executive assistant drafting context-aware follow-up email replies for {sender_name}.
Tone requested: {tone.upper()} ({tone_desc})
Target Recipient: {recipient_name}
Days elapsed since last email: {days_waiting} days.

CRITICAL CONTEXT & ATTACHMENT RULES:
1. Examine the email subject, latest message, conversation trail, and attached files.
2. If files were attached (e.g., Excel evaluation sheets like .xlsx, proposal PDFs, price quotes, slide decks), YOU MUST EXPLICITLY REFER TO THEM BY NAME OR PURPOSE in your follow-up note (e.g., "Following up on the Excel evaluation sheet I shared...", "Checking in to see if you had a chance to review the attached evaluation form...").
3. Connect the email organically to what was discussed in the thread (e.g. following up after a demo, providing the requested evaluation form, checking on next steps).
4. Write in the first person as {sender_name}.
5. Keep it natural, polite, and concise (1 to 3 short paragraphs).
6. Do NOT include any signoff or signature block (e.g. do NOT write 'Best Regards', 'Sincerely', or your name at the bottom). The corporate HTML signature is appended automatically.
7. Return ONLY the email body text. Do not add quotes, introductory commentary, or subject line.
"""

    user_prompt = f"""Original Subject: {original_subject}
Attached Files in This Email:
{attachments_str}

Latest Sent Email Body:
---
{clean_body_excerpt}
---

Full Conversation Trail History (Chronological):
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
                            "engine": f"OpenAI ({model})"
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
                            "engine": f"Gemini ({model})"
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
                            "engine": f"Anthropic ({model})"
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
        thread_trail=thread_trail
    )
