# Ensaan FollowUp Copilot 🚀

An AI-powered Outlook follow-up automation tool. It tracks your Sent folder over the past 3 months (or customizable date range), identifies emails that haven't received a reply, drafts context-aware follow-up emails, and lets you review, adjust, and approve them one by one before sending.

---

## 🌟 Key Features

1. **Direct Outlook Desktop Integration (Zero-OAuth Setup)**:
   - Uses local Outlook MAPI via `pywin32` to connect directly to your configured accounts (`mirfan@ensaantech.com`, `mirfan@squareonemea.com`).
   - Automatically detects conversation threads and whether recipients have replied.

2. **One-by-One Review & Approval Workspace**:
   - Split view showing the original sent email side-by-side with the AI follow-up studio.
   - Stepper progress bar showing your review queue (e.g. "Reviewing 3 of 18").
   - Quick navigation (`Next`, `Prev`, `Skip`).

3. **Multi-Engine AI Follow-up Studio**:
   - **Smart Built-in Engine**: Works offline immediately with zero API keys required.
   - **OpenAI (ChatGPT / GPT-4o)**: Contextual, executive follow-ups.
   - **Google Gemini (1.5 / 2.0 Flash)**: Fast, intelligent drafting.
   - **Anthropic Claude (3.5 Sonnet / Haiku)**: Eloquent, natural tone.
   - Preset tone chips: *⚡ Gentle & Warm*, *🎯 Direct & Crisp*, *🤝 Next Steps / Call*, *⏱️ Urgent / Milestone*.
   - Instant prompt adjustments (e.g., *"Ask if they can meet Thursday at 2 PM"*).

4. **1-Click Actions**:
   - **🚀 Approve & Send Now**: Directly sends the follow-up through Outlook as a properly threaded reply.
   - **📝 Save to Outlook Drafts**: Saves the draft into your Outlook Drafts folder to send later.
   - **⏰ Snooze**: Postpone follow-up for 3, 7, or 14 days.
   - **🗑️ Dismiss**: Mark as no follow-up needed.

5. **Keyboard Shortcuts**:
   - `Ctrl + Enter`: Approve & Send Now
   - `Alt + S`: Save to Outlook Drafts
   - `Alt + N` or `Alt + Right`: Next Email
   - `Alt + Left`: Previous Email

---

## 🚀 Quick Start

### 1. Launch with One Click
Double-click `run.bat` or run:
```bash
python run.py
```
This automatically starts the local server and opens your browser at:
`http://127.0.0.1:8000`

### 2. Configure AI (Optional)
Click the **Settings** gear icon in the top right to select your preferred AI engine and enter your API key (stored safely in local SQLite), or leave it on the **Smart Built-in Engine** for instant use without any API key.

---

## 📂 Project Structure

```
├── backend/
│   ├── database.py         # SQLite persistence for reviews and settings
│   ├── outlook_service.py  # Outlook COM interface & conversation tracker
│   ├── ai_service.py       # Multi-model draft generator (OpenAI, Gemini, Claude, Smart)
│   └── main.py             # FastAPI backend REST API
├── frontend/
│   ├── index.html          # Modern dark-mode web application interface
│   ├── style.css           # Design system, glassmorphism, animations
│   └── app.js              # Application state and approval flow
├── data/                   # Local database storage
├── run.py                  # Python launcher
├── run.bat                 # Windows batch launcher
├── requirements.txt        # Python dependencies
└── README.md
```
