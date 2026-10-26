import re
import httpx
from typing import Dict, Any, Optional
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
    # Clean subject prefixes
    clean_sub = re.sub(r'^(re|fwd|fw):\s*', '', subject, flags=re.IGNORECASE).strip()
    return clean_sub if clean_sub else "our recent discussion"

def generate_smart_builtin_draft(
    original_subject: str,
    original_body: str,
    recipient_name: str,
    days_waiting: int,
    tone: str = "gentle",
    custom_instruction: Optional[str] = None,
    sender_name: str = "Irfan"
) -> Dict[str, str]:
    first_name = clean_recipient_first_name(recipient_name)
    topic = extract_core_topic(original_subject, original_body)
    
    # Body keyword hints
    body_lower = original_body.lower()
    has_proposal = any(k in body_lower for k in ["proposal", "quote", "pricing", "commercial", "rfq"])
    has_meeting = any(k in body_lower for k in ["meeting", "call", "schedule", "calendar", "connect", "discuss"])
    has_document = any(k in body_lower for k in ["attached", "document", "deck", "presentation", "draft", "contract"])
    
    context_str = f"regarding \"{topic}\""
    if has_proposal:
        context_str = f"regarding the proposal details for {topic}"
    elif has_meeting:
        context_str = f"regarding our discussion on {topic}"
    elif has_document:
        context_str = f"regarding the documents shared for {topic}"
        
    days_text = f"sent {days_waiting} days ago" if days_waiting > 1 else "sent earlier this week"

    if tone == "professional":
        greeting = f"Hi {first_name},"
        opening = f"I am following up on my previous email {context_str}."
        if has_proposal:
            middle = "Could you please let me know if you had an opportunity to review the details or if any adjustments are needed from our side?"
        elif has_meeting:
            middle = "Kindly let me know if the proposed schedule works for your team or if an alternative time would be preferred."
        else:
            middle = "Could you please share a quick update on your team's feedback so we can plan the next steps accordingly?"
        closing = "Looking forward to your guidance."

    elif tone == "value_add":
        greeting = f"Dear {first_name},"
        opening = f"Hope you're having a productive week.\n\nI wanted to circle back on my last note {context_str}."
        middle = "I would be glad to jump on a quick 10-15 minute sync if that helps clarify any open questions or address any specific requirements."
        closing = "Please let me know what day and time might work best for you."

    elif tone == "urgent":
        greeting = f"Hi {first_name},"
        opening = f"Hope all is well.\n\nI am writing to check in on the below thread {context_str}."
        middle = "As we are organizing upcoming project deliverables and milestones, your input on this would be greatly appreciated to keep everything on track."
        closing = "Could you please provide a brief update at your earliest convenience?"

    else: # gentle / default
        greeting = f"Hi {first_name},"
        opening = f"Hope you are doing well.\n\nJust wanted to gently follow up on my previous email {context_str}."
        if has_proposal:
            middle = "I understand you have a busy schedule, so please take your time. Just checking if you have any questions or require any additional information."
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
        "engine": "Built-in Smart Template"
    }

async def generate_llm_draft(
    original_subject: str,
    original_body: str,
    recipient_name: str,
    days_waiting: int,
    tone: str = "gentle",
    custom_instruction: Optional[str] = None
) -> Dict[str, str]:
    """Generates draft using OpenAI, Gemini, Anthropic, or falls back to Smart Engine."""
    provider = get_setting("ai_provider", "smart_builtin")
    sender_name = get_setting("sender_name", "Irfan")
    tone_desc = TONE_PROMPTS.get(tone, TONE_PROMPTS["gentle"])
    
    # Excerpt body to avoid token limits
    clean_body_excerpt = original_body[:2500].strip()

    system_prompt = f"""You are an elite executive assistant crafting natural, highly professional follow-up email drafts for {sender_name}.
Tone requested: {tone.upper()} ({tone_desc})
Target Recipient: {recipient_name}
Days elapsed since original sent email: {days_waiting} days.

Guidelines:
1. Write in the first person as {sender_name}.
2. Be natural, contextual, and polite. Reference key context from the original email organically.
3. Keep it crisp, readable (1 to 3 short paragraphs maximum).
4. Do NOT include placeholder tokens like [Your Name] or [Recipient Name]. Use exact names provided.
5. Do NOT include any signoff or signature block (e.g., do not add 'Best Regards' or your name at the end), because an active HTML corporate signature is appended automatically.
6. Respond with ONLY the email body text. Do not add quotes, introductory commentary, or subject line in the body.
"""

    user_prompt = f"""Original Subject: {original_subject}
Original Email Body:
---
{clean_body_excerpt}
---

Additional Custom Instruction from user:
{custom_instruction if custom_instruction else 'None. Follow the requested tone.'}

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
        sender_name=sender_name
    )
