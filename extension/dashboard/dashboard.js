// dashboard.js — MeetIQ Dashboard Logic

document.addEventListener('DOMContentLoaded', async () => {
    const params = new URLSearchParams(window.location.hash.replace('#', '?'));
    const meetingId = params.get('meeting-id');

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

        renderMeeting(meeting);
    } catch (err) {
        console.error('Error loading meeting:', err);
        showEmptyState('Failed to load meeting data.');
    }
}

function renderMeeting(m) {
    const r = m.result;
    const s = r.summary || {};
    const content = document.getElementById('content');

    const date = new Date(m.savedAt || Date.now()).toLocaleDateString('en-US', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });

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

                    <h2>📋 Transcript Preview</h2>
                    <div class="transcript">
                        ${(r.segments || []).map(seg => `
                            <div class="transcript-segment">
                                <span class="speaker">${esc(seg.speaker)}</span>
                                <span class="text">${esc(seg.text)}</span>
                                <span class="timestamp">${formatTime(seg.start)}</span>
                            </div>
                        `).join('')}
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
