// ==========================================================================
// Ensaan FollowUp Copilot - Frontend Application Logic
// ==========================================================================

const state = {
  accounts: [],
  emails: [],
  filteredEmails: [],
  currentIndex: 0,
  currentStatus: 'needs_followup',
  currentAccount: 'all',
  currentDays: 90,
  currentTone: 'gentle',
  searchQuery: '',
  draftCache: {}, // entry_id -> { subject, body, tone, engine }
  settings: {},
  isLoading: false
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
  setupKeyboardShortcuts();
  setupTextareaWordCount();
  await loadSignature();
  await loadAccounts();
  await loadSettings();
  await loadEmails();
});

// --- API Calls ---

async function loadSignature() {
  try {
    const res = await fetch('/api/signature');
    const data = await res.json();
    const container = document.getElementById('active-signature-render');
    if (container && data.html) {
      container.innerHTML = data.html;
    }
  } catch (err) {
    console.error('Failed to load active signature:', err);
  }
}

async function loadAccounts() {
  try {
    const res = await fetch('/api/accounts');
    const data = await res.json();
    state.accounts = data.accounts || [];
    
    const select = document.getElementById('select-account');
    select.innerHTML = '<option value="all">All Accounts</option>';
    
    state.accounts.forEach(acc => {
      const opt = document.createElement('option');
      opt.value = acc.name;
      opt.textContent = `${acc.name} (${acc.total_sent} sent)`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Failed to load accounts:', err);
  }
}

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    state.settings = await res.json();
  } catch (err) {
    console.error('Failed to load settings:', err);
  }
}

async function loadEmails(showSync = false) {
  const syncBtn = document.getElementById('btn-sync');
  if (showSync && syncBtn) {
    syncBtn.classList.add('spinning');
  }

  const account = document.getElementById('select-account').value;
  const days = document.getElementById('select-days').value;
  state.currentAccount = account;
  state.currentDays = days;

  try {
    // 1. Fetch stats for topbar KPIs
    updateStats(account, days);

    // 2. Fetch emails for current status tab
    const url = `/api/emails?account=${encodeURIComponent(account)}&days_back=${days}&status=${state.currentStatus}&search=${encodeURIComponent(state.searchQuery)}`;
    const res = await fetch(url);
    const data = await res.json();
    state.emails = data.emails || [];

    renderThreadList();

    if (state.emails.length > 0) {
      if (state.currentIndex >= state.emails.length) {
        state.currentIndex = 0;
      }
      selectEmail(state.currentIndex);
    } else {
      showEmptyState();
    }
  } catch (err) {
    console.error('Failed to load emails:', err);
    showToast('Failed to connect to Outlook sent folder.', 'error');
  } finally {
    if (syncBtn) syncBtn.classList.remove('spinning');
  }
}

async function updateStats(account, days) {
  try {
    const res = await fetch(`/api/stats?account=${encodeURIComponent(account)}&days_back=${days}`);
    const stats = await res.json();
    
    document.getElementById('count-awaiting').textContent = stats.awaiting_reply ?? 0;
    document.getElementById('count-replied').textContent = stats.replied ?? 0;
    document.getElementById('count-followed').textContent = stats.approved_sent ?? 0;
    document.getElementById('tab-count-pending').textContent = stats.awaiting_reply ?? 0;
  } catch (err) {
    console.error('Failed to fetch stats:', err);
  }
}

// --- Rendering Thread List ---

function renderThreadList() {
  const container = document.getElementById('thread-list');
  container.innerHTML = '';

  if (state.emails.length === 0) {
    container.innerHTML = `
      <div class="loading-state">
        <p>No emails found for this filter.</p>
      </div>
    `;
    return;
  }

  state.emails.forEach((email, index) => {
    const item = document.createElement('div');
    item.className = `thread-item ${index === state.currentIndex ? 'active' : ''}`;
    item.onclick = () => selectEmail(index);

    // Badge styling based on days waiting or status
    let badgeHtml = '';
    if (email.status === 'replied') {
      badgeHtml = `<span class="thread-badge blue">Replied</span>`;
    } else if (email.status === 'approved_sent') {
      badgeHtml = `<span class="thread-badge green">Followed Up</span>`;
    } else if (email.days_waiting >= 7) {
      badgeHtml = `<span class="thread-badge rose">${email.days_waiting}d waiting</span>`;
    } else {
      badgeHtml = `<span class="thread-badge amber">${email.days_waiting}d waiting</span>`;
    }

    item.innerHTML = `
      <div class="thread-top">
        <span class="thread-recipient" title="${escapeHtml(email.to)}">${escapeHtml(email.recipient_name)}</span>
        ${badgeHtml}
      </div>
      <div class="thread-subject" title="${escapeHtml(email.subject)}">${escapeHtml(email.subject)}</div>
      <div class="thread-snippet">${escapeHtml(email.snippet || 'No text snippet')}</div>
      <div class="thread-footer">
        <span>Sent: ${escapeHtml(email.sent_on_formatted)}</span>
        <span>${escapeHtml(email.account.split('@')[1] || '')}</span>
      </div>
    `;

    container.appendChild(item);
  });
}

// --- Email Selection & Workspace Binding ---

async function selectEmail(index) {
  if (index < 0 || index >= state.emails.length) return;
  state.currentIndex = index;

  // Update active state in list
  document.querySelectorAll('.thread-item').forEach((el, i) => {
    el.classList.toggle('active', i === index);
  });

  const email = state.emails[index];
  showActiveReviewCard();

  // Update stepper
  document.getElementById('current-step').textContent = index + 1;
  document.getElementById('total-steps').textContent = state.emails.length;
  const progressPercent = ((index + 1) / state.emails.length) * 100;
  document.getElementById('progress-bar-fill').style.width = `${progressPercent}%`;

  document.getElementById('btn-prev').disabled = index === 0;
  document.getElementById('btn-next').disabled = index === state.emails.length - 1;

  // Update recipient metadata
  const avatarLetter = (email.recipient_name || 'U').trim().charAt(0).toUpperCase();
  document.getElementById('active-avatar').textContent = avatarLetter;
  document.getElementById('active-recipient-name').textContent = email.recipient_name;
  document.getElementById('active-recipient-email').textContent = email.to;
  document.getElementById('active-sent-date').textContent = email.sent_on_formatted;
  document.getElementById('active-account-tag').textContent = email.account;

  const waitingBadge = document.getElementById('active-waiting-badge');
  if (email.has_replied) {
    waitingBadge.textContent = `Replied by ${email.last_reply_from || 'Recipient'}`;
    waitingBadge.className = 'badge-waiting green';
  } else {
    waitingBadge.textContent = `${email.days_waiting} days without reply`;
    waitingBadge.className = email.days_waiting >= 7 ? 'badge-waiting rose' : 'badge-waiting amber';
  }

  // Bind Original Email
  document.getElementById('active-original-subject').textContent = email.subject;
  document.getElementById('active-original-body').textContent = email.body || '(Email body is empty)';

  // Render Attachments Bar
  const attsBar = document.getElementById('active-attachments-bar');
  const attsTags = document.getElementById('active-attachment-tags');
  if (email.attachments && email.attachments.length > 0) {
    attsBar.style.display = 'flex';
    attsTags.innerHTML = email.attachments.map(att => {
      const isExcel = att.toLowerCase().includes('.xls') || att.toLowerCase().includes('.csv');
      return `<span class="attachment-pill ${isExcel ? 'excel' : ''}">📎 ${escapeHtml(att)}</span>`;
    }).join('');
  } else {
    attsBar.style.display = 'none';
  }

  // Fetch conversation trail for this email if not yet loaded
  if (!email.thread_trail) {
    try {
      const trailRes = await fetch(`/api/email/${encodeURIComponent(email.entry_id)}/trail`);
      if (trailRes.ok) {
        const trailData = await trailRes.json();
        email.thread_trail = trailData.trail || [];
      }
    } catch (e) {
      console.warn('Could not load thread trail:', e);
      email.thread_trail = [];
    }
  }

  // Render Conversation Trail
  const trailContainer = document.getElementById('active-trail-container');
  const trailList = document.getElementById('active-trail-list');
  const trailCount = document.getElementById('trail-count');
  if (email.thread_trail && email.thread_trail.length > 0) {
    trailContainer.style.display = 'flex';
    trailCount.textContent = email.thread_trail.length;
    trailList.innerHTML = email.thread_trail.map(t => `
      <div class="trail-msg ${t.is_self ? 'self' : 'client'}">
        <div class="trail-msg-top">
          <span>${escapeHtml(t.sender)} ${t.is_self ? '<span style="font-size:0.65rem; color:#818cf8; margin-left:4px;">(You)</span>' : '<span style="font-size:0.65rem; color:#34d399; margin-left:4px;">(Client)</span>'}</span>
          <span class="trail-msg-date">${escapeHtml(t.date)}</span>
        </div>
        <div class="trail-msg-body">${escapeHtml(t.body || t.snippet)}</div>
        ${t.attachments && t.attachments.length ? `<div class="trail-msg-atts" style="margin-top:4px;">📎 Attached: <span style="color:#6ee7b7; font-weight:500;">${escapeHtml(t.attachments.join(', '))}</span></div>` : ''}
      </div>
    `).join('');
    // Ensure trail is visible by default
    trailList.style.display = 'flex';
    document.getElementById('trail-toggle-label').innerHTML = 'Hide &uarr;';
  } else {
    trailContainer.style.display = 'none';
  }

  // Reset Draft Studio To, CC & Subject
  document.getElementById('draft-to').value = email.to || '';
  document.getElementById('draft-cc').value = email.cc || '';
  document.getElementById('input-custom-prompt').value = '';

  // Check if draft already exists in cache or saved draft in DB
  if (state.draftCache[email.entry_id]) {
    const cached = state.draftCache[email.entry_id];
    setDraftContent(cached.subject, cached.body, cached.engine, cached.tone, cached.research_intel, cached.company_news, cached.solution_highlight);
  } else if (email.saved_draft) {
    setDraftContent(`Follow-up: ${email.subject}`, email.saved_draft, 'Saved Draft', 'gentle');
  } else {
    // Generate AI draft automatically for this email
    await generateDraftForEmail(email, state.currentTone);
  }
}

function toggleTrail() {
  const list = document.getElementById('active-trail-list');
  const label = document.getElementById('trail-toggle-label');
  const isHidden = list.style.display === 'none';
  list.style.display = isHidden ? 'flex' : 'none';
  label.innerHTML = isHidden ? 'Hide &uarr;' : 'Show &darr;';
}

// --- Draft Generation ---

async function generateDraftForEmail(email, tone, customPrompt = '') {
  const regenBtn = document.getElementById('btn-regenerate');
  if (regenBtn) regenBtn.classList.add('spinning');
  
  document.getElementById('ai-engine-badge').textContent = 'Researching & Drafting...';

  try {
    const payload = {
      entry_id: email.entry_id,
      original_subject: email.subject,
      original_body: email.body,
      recipient_name: email.recipient_name,
      days_waiting: email.days_waiting,
      tone: tone,
      custom_instruction: customPrompt,
      attachments: email.attachments || [],
      thread_trail: email.thread_trail || [],
      to_address: email.to || '',
      include_intelligence: state.includeIntelligence !== false
    };

    const res = await fetch('/api/generate-draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    setDraftContent(
      data.subject, 
      data.body, 
      data.engine, 
      tone, 
      data.research_intel, 
      data.company_news, 
      data.solution_highlight
    );

    // Cache draft
    state.draftCache[email.entry_id] = {
      subject: data.subject,
      body: data.body,
      engine: data.engine,
      tone: tone,
      research_intel: data.research_intel,
      company_news: data.company_news,
      solution_highlight: data.solution_highlight
    };
  } catch (err) {
    console.error('Draft generation failed:', err);
    showToast('Failed to generate draft. Please check your AI settings.', 'error');
  } finally {
    if (regenBtn) regenBtn.classList.remove('spinning');
  }
}

function setDraftContent(subject, body, engine, tone, intel = null, companyNews = '', solutionHighlight = '') {
  document.getElementById('draft-subject').value = subject;
  document.getElementById('draft-body').value = body;
  document.getElementById('ai-engine-badge').textContent = engine || 'Smart Engine';
  updateWordCount();

  // Update Market & Solution Intelligence Card
  renderIntelligenceCard(intel, companyNews, solutionHighlight);

  // Update tone chips
  document.querySelectorAll('.tone-chip').forEach(chip => {
    chip.classList.toggle('active', chip.dataset.tone === tone);
  });
}

function renderIntelligenceCard(intel, companyNews, solutionHighlight) {
  const compName = document.getElementById('intel-company-name');
  const newsText = document.getElementById('intel-news-text');
  const solName = document.getElementById('intel-solution-name');
  const solText = document.getElementById('intel-solution-text');

  if (intel) {
    if (compName) compName.textContent = intel.company || 'Prospect';
    if (newsText) newsText.textContent = intel.top_news || 'Verified business expansion & infrastructure milestones in KSA';
    if (solName) solName.textContent = intel.solution_name || 'Solution Provider';
    if (solText) solText.textContent = intel.solution_headline ? `${intel.solution_headline} — ${intel.solution_summary || ''}` : 'Latest AI workforce updates and enterprise capabilities';
  } else {
    if (companyNews && newsText) newsText.textContent = companyNews;
    if (solutionHighlight && solText) solText.textContent = solutionHighlight;
  }
}

function handleIntelToggle(checked) {
  state.includeIntelligence = checked;
  regenerateDraft();
}

async function refreshIntelligence() {
  const email = state.emails[state.currentIndex];
  if (!email) return;

  const refreshBtn = document.getElementById('btn-refresh-intel');
  if (refreshBtn) refreshBtn.classList.add('spinning');

  try {
    const res = await fetch('/api/research-intelligence', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: email.subject,
        body: email.body,
        to_address: email.to || '',
        recipient_name: email.recipient_name || '',
        thread_trail: email.thread_trail || []
      })
    });
    if (res.ok) {
      const intel = await res.json();
      renderIntelligenceCard(intel);
      delete state.draftCache[email.entry_id];
      await regenerateDraft();
      showToast('Live company research & solution updates refreshed', 'info');
    }
  } catch (err) {
    console.error('Failed to refresh intelligence:', err);
  } finally {
    if (refreshBtn) refreshBtn.classList.remove('spinning');
  }
}

function selectTone(tone, btn) {
  state.currentTone = tone;
  document.querySelectorAll('.tone-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');

  const email = state.emails[state.currentIndex];
  if (email) {
    const customPrompt = document.getElementById('input-custom-prompt').value;
    generateDraftForEmail(email, tone, customPrompt);
  }
}

function regenerateDraft() {
  const email = state.emails[state.currentIndex];
  if (!email) return;
  const customPrompt = document.getElementById('input-custom-prompt').value;
  generateDraftForEmail(email, state.currentTone, customPrompt);
}

// --- Action Executions: Send, Save Draft, Dismiss, Snooze ---

async function approveAndSend() {
  const email = state.emails[state.currentIndex];
  if (!email) return;

  const draftTo = document.getElementById('draft-to').value.trim();
  const draftBody = document.getElementById('draft-body').value.trim();
  const draftSubject = document.getElementById('draft-subject').value.trim();
  const cc = document.getElementById('draft-cc').value.trim();

  if (!draftBody) {
    showToast('Draft body cannot be empty!', 'error');
    return;
  }

  const sendBtn = document.getElementById('btn-approve-send');
  sendBtn.disabled = true;
  sendBtn.innerHTML = `<span>Sending via Outlook...</span>`;

  try {
    const res = await fetch('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entry_id: email.entry_id,
        draft_body: draftBody,
        draft_subject: draftSubject,
        to: draftTo,
        cc: cc
      })
    });

    const result = await res.json();
    if (result.success) {
      showToast(`Follow-up sent successfully to ${result.to || email.recipient_name}!`, 'success');
      // Advance to next email and refresh counts
      advanceAfterAction(email.entry_id);
    } else {
      showToast(`Send failed: ${result.error}`, 'error');
    }
  } catch (err) {
    showToast(`Error sending email: ${err.message}`, 'error');
  } finally {
    sendBtn.disabled = false;
    sendBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
      <span>Approve & Send Now</span>
    `;
  }
}

async function saveAsDraft() {
  const email = state.emails[state.currentIndex];
  if (!email) return;

  const draftTo = document.getElementById('draft-to').value.trim();
  const draftBody = document.getElementById('draft-body').value.trim();
  const draftSubject = document.getElementById('draft-subject').value.trim();
  const cc = document.getElementById('draft-cc').value.trim();

  try {
    const res = await fetch('/api/save-draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entry_id: email.entry_id,
        draft_body: draftBody,
        draft_subject: draftSubject,
        to: draftTo,
        cc: cc
      })
    });

    const result = await res.json();
    if (result.success) {
      showToast('Saved to Outlook Drafts folder!', 'success');
      advanceAfterAction(email.entry_id);
    } else {
      showToast(`Failed to save draft: ${result.error}`, 'error');
    }
  } catch (err) {
    showToast(`Error saving draft: ${err.message}`, 'error');
  }
}

async function dismissCurrentEmail() {
  const email = state.emails[state.currentIndex];
  if (!email) return;

  try {
    const res = await fetch('/api/dismiss', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entry_id: email.entry_id,
        status: 'dismissed'
      })
    });

    showToast(`Dismissed follow-up for ${email.recipient_name}`, 'success');
    advanceAfterAction(email.entry_id);
  } catch (err) {
    showToast('Failed to dismiss email', 'error');
  }
}

async function snoozeCurrentEmail(days) {
  const email = state.emails[state.currentIndex];
  if (!email) return;

  try {
    await fetch('/api/snooze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entry_id: email.entry_id,
        status: 'snoozed',
        snooze_days: days
      })
    });

    toggleSnoozeMenu(false);
    showToast(`Snoozed for ${days} days`, 'success');
    advanceAfterAction(email.entry_id);
  } catch (err) {
    showToast('Failed to snooze email', 'error');
  }
}

function advanceAfterAction(removedEntryId) {
  // Remove email from current view list if in 'needs_followup'
  if (state.currentStatus === 'needs_followup') {
    state.emails = state.emails.filter(e => e.entry_id !== removedEntryId);
    renderThreadList();
    if (state.emails.length > 0) {
      if (state.currentIndex >= state.emails.length) {
        state.currentIndex = state.emails.length - 1;
      }
      selectEmail(state.currentIndex);
    } else {
      showEmptyState();
    }
  } else {
    navigateQueue(1);
  }
  updateStats(state.currentAccount, state.currentDays);
}

function navigateQueue(delta) {
  const newIndex = state.currentIndex + delta;
  if (newIndex >= 0 && newIndex < state.emails.length) {
    selectEmail(newIndex);
  }
}

// --- Navigation & Filter Handlers ---

function setStatusTab(status, btn) {
  state.currentStatus = status;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  document.querySelectorAll('.kpi-pill').forEach(p => p.classList.remove('active'));
  if (status === 'needs_followup') document.getElementById('kpi-awaiting').classList.add('active');
  if (status === 'replied') document.getElementById('kpi-replied').classList.add('active');
  if (status === 'approved_sent') document.getElementById('kpi-sent').classList.add('active');

  loadEmails();
}

function filterByStatus(status) {
  const targetTab = document.querySelector(`.tab-btn[data-status="${status}"]`);
  if (targetTab) {
    setStatusTab(status, targetTab);
  }
}

let searchDebounce = null;
function handleSearch(val) {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.searchQuery = val.trim();
    loadEmails();
  }, 300);
}

// --- View State Helpers ---

function showEmptyState() {
  document.getElementById('empty-state').style.display = 'flex';
  document.getElementById('review-card').style.display = 'none';
}

function showActiveReviewCard() {
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('review-card').style.display = 'flex';
}

function toggleSnoozeMenu(force) {
  const menu = document.getElementById('snooze-menu');
  if (force !== undefined) {
    menu.classList.toggle('show', force);
  } else {
    menu.classList.toggle('show');
  }
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.dropdown-container')) {
    toggleSnoozeMenu(false);
  }
});

function updateWordCount() {
  const text = document.getElementById('draft-body').value.trim();
  const words = text ? text.split(/\s+/).length : 0;
  document.getElementById('char-count').textContent = `${words} words`;
}

function setupTextareaWordCount() {
  const textarea = document.getElementById('draft-body');
  if (textarea) {
    textarea.addEventListener('input', updateWordCount);
  }
}

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Ctrl + Enter => Approve & Send
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      approveAndSend();
    }
    // Alt + S => Save Draft
    if (e.altKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      saveAsDraft();
    }
    // Alt + Right / Alt + N => Next
    if (e.altKey && (e.key === 'ArrowRight' || e.key === 'n')) {
      e.preventDefault();
      navigateQueue(1);
    }
    // Alt + Left => Prev
    if (e.altKey && e.key === 'ArrowLeft') {
      e.preventDefault();
      navigateQueue(-1);
    }
  });
}

// --- Settings Modal Logic ---

function openSettingsModal() {
  const s = state.settings;
  const modal = document.getElementById('settings-modal');
  
  // Set provider radio
  const provider = s.ai_provider || 'smart_builtin';
  const radio = document.querySelector(`input[name="ai_provider"][value="${provider}"]`);
  if (radio) radio.checked = true;

  // General fields
  document.getElementById('cfg-sender-name').value = s.sender_name || 'Irfan';
  document.getElementById('cfg-min-days').value = s.min_days_waiting || '2';

  // API Keys (show masked placeholder if already set)
  document.getElementById('cfg-openai-key').placeholder = s.openai_api_key_masked || 'sk-...';
  document.getElementById('cfg-gemini-key').placeholder = s.gemini_api_key_masked || 'AIzaSy...';
  document.getElementById('cfg-anthropic-key').placeholder = s.anthropic_api_key_masked || 'sk-ant-...';

  toggleProviderFields();
  modal.style.display = 'flex';
}

function closeSettingsModal() {
  document.getElementById('settings-modal').style.display = 'none';
}

function toggleProviderFields() {
  const selected = document.querySelector('input[name="ai_provider"]:checked')?.value || 'smart_builtin';
  document.getElementById('group-openai').style.display = selected === 'openai' ? 'flex' : 'none';
  document.getElementById('group-gemini').style.display = selected === 'gemini' ? 'flex' : 'none';
  document.getElementById('group-anthropic').style.display = selected === 'anthropic' ? 'flex' : 'none';
}

async function saveSettings() {
  const provider = document.querySelector('input[name="ai_provider"]:checked').value;
  const senderName = document.getElementById('cfg-sender-name').value.trim();
  const minDays = document.getElementById('cfg-min-days').value.trim();

  const settingsToUpdate = {
    ai_provider: provider,
    sender_name: senderName || 'Irfan',
    min_days_waiting: minDays || '2'
  };

  const openaiKey = document.getElementById('cfg-openai-key').value.trim();
  const geminiKey = document.getElementById('cfg-gemini-key').value.trim();
  const anthropicKey = document.getElementById('cfg-anthropic-key').value.trim();

  if (openaiKey) settingsToUpdate.openai_api_key = openaiKey;
  if (geminiKey) settingsToUpdate.gemini_api_key = geminiKey;
  if (anthropicKey) settingsToUpdate.anthropic_api_key = anthropicKey;

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: settingsToUpdate })
    });
    const result = await res.json();
    if (result.success) {
      showToast('Settings saved successfully!', 'success');
      closeSettingsModal();
      await loadSettings();
      // Regenerate current draft with new settings if email selected
      const email = state.emails[state.currentIndex];
      if (email) {
        generateDraftForEmail(email, state.currentTone);
      }
    }
  } catch (err) {
    showToast('Failed to save settings', 'error');
  }
}

// --- Toast Notifications ---

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success' ? 
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>` :
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

  toast.innerHTML = `${icon}<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
