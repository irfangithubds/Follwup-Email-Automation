import sqlite3
import os
import json
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "followup_copilot.db")

def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table to track email review states
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_reviews (
            entry_id TEXT PRIMARY KEY,
            conversation_id TEXT,
            account TEXT,
            subject TEXT,
            to_address TEXT,
            sent_on TEXT,
            status TEXT DEFAULT 'pending', 
            draft_subject TEXT,
            draft_body TEXT,
            draft_tone TEXT,
            action_taken_at TEXT,
            snooze_until TEXT,
            notes TEXT
        )
    """)
    
    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Default settings if not already present
    default_settings = {
        "ai_provider": "smart_builtin", # smart_builtin, openai, gemini, anthropic
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "gemini_api_key": "",
        "gemini_model": "gemini-1.5-flash",
        "anthropic_api_key": "",
        "anthropic_model": "claude-3-5-haiku-20241022",
        "min_days_waiting": "3",
        "default_tone": "gentle",
        "sender_name": "Irfan",
        "auto_detect_replies": "true"
    }
    
    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.cursor().execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    conn = get_connection()
    conn.cursor().execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_all_settings() -> dict:
    conn = get_connection()
    rows = conn.cursor().execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    # Hide sensitive API keys in response representation if needed, or pass masked
    return settings

def update_email_status(entry_id: str, status: str, draft_subject: str = None, draft_body: str = None, draft_tone: str = None, snooze_until: str = None, notes: str = None):
    conn = get_connection()
    now_str = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO email_reviews (entry_id, status, draft_subject, draft_body, draft_tone, action_taken_at, snooze_until, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entry_id) DO UPDATE SET
            status = excluded.status,
            draft_subject = COALESCE(excluded.draft_subject, email_reviews.draft_subject),
            draft_body = COALESCE(excluded.draft_body, email_reviews.draft_body),
            draft_tone = COALESCE(excluded.draft_tone, email_reviews.draft_tone),
            action_taken_at = excluded.action_taken_at,
            snooze_until = excluded.snooze_until,
            notes = COALESCE(excluded.notes, email_reviews.notes)
    """, (entry_id, status, draft_subject, draft_body, draft_tone, now_str, snooze_until, notes))
    conn.commit()
    conn.close()

def get_reviewed_status_map():
    conn = get_connection()
    rows = conn.cursor().execute("SELECT entry_id, status, snooze_until, draft_subject, draft_body, draft_tone FROM email_reviews").fetchall()
    conn.close()
    return {r["entry_id"]: dict(r) for r in rows}
