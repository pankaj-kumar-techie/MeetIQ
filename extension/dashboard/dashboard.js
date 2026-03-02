// dashboard.js — MeetIQ Dashboard Logic

document.addEventListener('DOMContentLoaded', async () => {
    const params = new URLSearchParams(window.location.hash.replace('#', '?'));
    const meetingId = params.get('meeting-id');
    window.MEETING_ID = meetingId; // Global for easy access

    if (!meetingId) {
        showEmptyState('No meeting selected.');
        return;
    }

    await loadMeeting(meetingId);
});

async function loadMeeting(id) {
    try {
        const { meetings = [] } = await chrome.storage.local.get('meetings');
        const meeting = meetings.find(m => m.meetingId === id);

        if (!meeting || !meeting.result) {
            showEmptyState('Meeting data not found locally.');
            return;
        }

        await renderMeeting(meeting);
    } catch (err) {
        console.error('Error loading meeting:', err);
        showEmptyState('Failed to load meeting data.');
    }
}

async function renderMeeting(m) {
    const r = m.result;
    const s = r.summary || {};
    const content = document.getElementById('content');

    const date = new Date(m.savedAt || Date.now()).toLocaleDateString('en-US', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });

    const isAnalyzed = s.overview && !s.overview.includes('Transcript ready');
    const navActions = document.getElementById('nav-actions');

    if (!isAnalyzed) {
        navActions.innerHTML = `
            <button id="btn-analyze" class="btn-analyze" data-action="run-analysis">
                <span class="icon">✨</span>
                Run AI Brain
            </button>
        `;
    } else {
        navActions.innerHTML = `<span class="tag">✅ AI Analyzed</span>`;
    }

    content.innerHTML = `
        <div class="header-section">
            <h1>${esc(r.meetingName || 'Unnamed Meeting')}</h1>
            <div class="meta">
                <span>📅 ${date}</span>
                <span>⏱ ${Math.round((r.duration_ms || 0) / 60000)} min</span>
                <span class="tag">${esc(r.detected_meeting_type || r.meeting_type || 'discovery')}</span>
            </div>
        </div>

        <div class="grid">
            <div class="left">
                <div class="card">
                    <h2>✨ Summary Overview</h2>
                    <p class="overview">${esc(s.overview || 'No overview generated.')}</p>
                    
                    <h2>🔑 Key Points</h2>
                    <ul style="list-style: none; margin-bottom: 24px;">
                        ${(s.key_points || []).map(p => `<li style="margin-bottom: 8px;">• ${esc(p)}</li>`).join('')}
                    </ul>

                    <h2>📋 Full Conversation</h2>
                    <div class="transcript" id="transcript-container">
                        ${await renderChatBubbles(r.segments || [])}
                    </div>
                </div>
            </div>

            <div class="right">
                <div class="card">
                    <h2>⚠️ Commitments (${r.commitments?.length || 0})</h2>
                    ${(r.commitments || []).length ? r.commitments.map(c => `
                        <div class="commitment-card ${c.risk_level}">
                            <div class="commit-text">${esc(c.text)}</div>
                            <div class="commit-meta">
                                <span style="text-transform: capitalize;">👤 ${esc(c.speaker)}</span>
                                <span style="font-weight: 600;">🚩 ${c.risk_level.toUpperCase()} RISK</span>
                            </div>
                        </div>
                    `).join('') : '<p style="color: var(--muted); font-size: 14px;">No commitments detected.</p>'}
                </div>

                <div class="card">
                    <h2>✅ Action Items (${r.action_items?.length || 0})</h2>
                    ${(r.action_items || []).length ? r.action_items.map(a => `
                        <div class="action-item">
                            <div class="action-check">✔</div>
                            <div class="action-content">
                                <div class="action-task">${esc(a.task)}</div>
                                <div class="action-owner">${esc(a.owner)} ${a.deadline !== 'Not specified' ? `· ⏰ ${esc(a.deadline)}` : ''}</div>
                            </div>
                        </div>
                    `).join('') : '<p style="color: var(--muted); font-size: 14px;">No action items found.</p>'}
                </div>
            </div>
        </div>
    `;

    // 🚀 Auto-scroll to the bottom of the chat
    setTimeout(() => {
        const transcript = document.getElementById('transcript-container');
        if (transcript) {
            transcript.scrollTop = transcript.scrollHeight;
        }
    }, 150);
}

function showEmptyState(msg) {
    document.getElementById('content').innerHTML = `
        <div class="empty">
            <div class="empty-icon">🔍</div>
            <p>${esc(msg)}</p>
            <button onclick="window.close()" style="margin-top: 20px; padding: 10px 20px; border-radius: 8px; border: 1px solid var(--card-border); background: var(--card); color: white; cursor: pointer;">Go Back</button>
        </div>
    `;
}

function formatTime(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    return `${h > 0 ? h + ':' : ''}${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function renderChatBubbles(segments) {
    if (!segments || segments.length === 0) {
        return '<p style="color:var(--muted); text-align:center; padding:20px;">No transcript data available.</p>';
    }

    const { settings = {} } = await chrome.storage.local.get('settings');
    const myName = (settings.speakerName || 'Me').toLowerCase();

    return segments.map(seg => {
        const speaker = seg.speaker || 'Unknown';
        const initials = speaker.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);

        const isSelf = speaker.toLowerCase().includes(myName) ||
            speaker.toLowerCase().includes('speaker 1') ||
            speaker.toLowerCase().includes('me');

        const side = isSelf ? 'self' : 'other';

        return `
            <div class="chat-msg ${side}">
                <div class="avatar">${esc(initials)}</div>
                <div class="msg-container">
                    <div class="msg-meta">
                        <span class="speaker-name">${esc(speaker)}</span>
                        <span class="msg-time">${formatTime(seg.start)}</span>
                    </div>
                    <div class="chat-bubble">
                        ${esc(seg.text)}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// 🚀 Use Event Delegation to avoid CSP issues with inline onclick
document.addEventListener('click', (e) => {
    if (e.target.closest('[data-action="run-analysis"]')) {
        runAnalysis();
    }
});

// 🚀 Manual Analysis Trigger
async function runAnalysis() {
    const btn = document.getElementById('btn-analyze');
    if (!btn || btn.disabled) return;

    btn.disabled = true;
    btn.classList.add('loading');
    btn.innerHTML = `<span class="icon">⏳</span> Analyzing...`;

    try {
        const { settings = {} } = await chrome.storage.local.get('settings');
        const baseUrl = settings.serverUrl || 'http://localhost:8000';

        console.log(`[MeetIQ Dashboard] Triggering manual analysis for ${window.MEETING_ID}...`);
        const res = await fetch(`${baseUrl}/api/recordings/${window.MEETING_ID}/analyze`, { method: 'POST' });
        if (!res.ok) throw new Error('Analysis failed.');

        const data = await res.json();
        const result = data.result;

        // 1. Update Storage
        const { meetings = [] } = await chrome.storage.local.get('meetings');
        const mIdx = meetings.findIndex(m => m.meetingId === window.MEETING_ID);
        if (mIdx !== -1) {
            meetings[mIdx].result.summary = result.summary;
            meetings[mIdx].result.commitments = result.commitments;
            meetings[mIdx].result.action_items = result.action_items;
            meetings[mIdx].result.follow_up = result.follow_up;
            meetings[mIdx].result.detected_meeting_type = result.detected_meeting_type;
            await chrome.storage.local.set({ meetings });
        }

        // 2. Re-render UI
        const meeting = meetings.find(m => m.meetingId === window.MEETING_ID);
        await renderMeeting(meeting);

    } catch (err) {
        console.error('Manual Analysis error:', err);
        btn.innerHTML = `<span class="icon">❌</span> Error`;
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = `<span class="icon">✨</span> Run AI Brain`;
        }, 3000);
    } finally {
        btn.classList.remove('loading');
    }
}
