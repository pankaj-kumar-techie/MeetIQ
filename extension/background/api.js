async function getBase() {
  const { settings = {} } = await chrome.storage.local.get('settings')
  return settings.apiUrl || 'http://localhost:8000'
}

export async function uploadChunk(recordingId, base64Chunk) {
  const base = await getBase()
  const url = `${base}/api/recordings/${recordingId}/chunk`
  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chunk: base64Chunk }),
  }).catch(e => {
    console.warn(`[MeetIQ] Chunk upload failed to ${url}:`, e.message);
    chrome.runtime.sendMessage({ type: 'REMOTE_LOG', level: 'warn', tag: 'api', message: `Upload failed to ${url}: ${e.message}` }).catch(() => { });
  });
}

export async function finalizeMeeting(recordingId) {
  const base = await getBase()
  const r = await fetch(`${base}/api/recordings/${recordingId}/finalize`, { method: 'POST' })
  return r.json()
}

export async function sendAlert(meeting, result) {
  const { settings = {} } = await chrome.storage.local.get('settings')
  const tasks = []
  if (settings.discordWebhook) tasks.push(discord(settings.discordWebhook, meeting, result))
  if (settings.slackWebhook) tasks.push(slack(settings.slackWebhook, meeting, result))
  await Promise.allSettled(tasks)
}

async function discord(url, meeting, result) {
  const s = result.summary || {}
  const commits = result.commitments || []
  const actions = result.action_items || []
  const riskCol = { low: 0x22c55e, medium: 0xeab308, high: 0xef4444 }
  const topRisk = commits.find(c => c.risk_level === 'high') || commits[0]

  const fields = []
  if (meeting.purpose) fields.push({ name: '📌 Purpose', value: meeting.purpose, inline: true })
  if (meeting.participants?.length) fields.push({ name: '👥 Participants', value: meeting.participants.join(', '), inline: true })

  const dur = meeting.startedAt && meeting.endedAt
    ? `${Math.round((meeting.endedAt - meeting.startedAt) / 60000)}min`
    : '—'
  fields.push({ name: '⏱ Duration', value: dur, inline: true })

  if (s.key_points?.length)
    fields.push({ name: '🔑 Key Points', value: s.key_points.slice(0, 4).map(p => `• ${p}`).join('\n') })

  if (commits.length)
    fields.push({ name: `⚠️ Commitments (${commits.length})`, value: commits.slice(0, 3).map(c => `\`${c.risk_level.toUpperCase()}\` ${c.text.slice(0, 90)}`).join('\n') })

  if (actions.length)
    fields.push({ name: `✅ Action Items (${actions.length})`, value: actions.slice(0, 4).map(a => `• **${a.task}** — ${a.owner}${a.deadline !== 'Not specified' ? ` *(${a.deadline})*` : ''}`).join('\n') })

  if (s.open_questions?.length)
    fields.push({ name: '❓ Open Questions', value: s.open_questions.slice(0, 3).map(q => `• ${q}`).join('\n') })

  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      embeds: [{
        title: `📋 MeetIQ — ${meeting.name}`,
        description: s.overview || 'Meeting analyzed.',
        color: topRisk ? riskCol[topRisk.risk_level] : 0x1a4f8a,
        fields,
        timestamp: new Date().toISOString(),
        footer: { text: 'MeetIQ AI Meeting Intelligence' },
      }]
    })
  })
}

async function slack(url, meeting, result) {
  const s = result.summary || {}
  const actions = result.action_items || []
  const commits = result.commitments || []
  const dur = meeting.startedAt && meeting.endedAt
    ? `${Math.round((meeting.endedAt - meeting.startedAt) / 60000)}min`
    : '—'

  const blocks = [
    { type: 'header', text: { type: 'plain_text', text: `📋 ${meeting.name} — Complete` } },
    { type: 'section', text: { type: 'mrkdwn', text: `*${s.overview || 'Meeting analyzed.'}*` } },
    {
      type: 'section', fields: [
        { type: 'mrkdwn', text: `*Purpose:*\n${meeting.purpose || '—'}` },
        { type: 'mrkdwn', text: `*Participants:*\n${meeting.participants?.join(', ') || '—'}` },
        { type: 'mrkdwn', text: `*Duration:*\n${dur}` },
        { type: 'mrkdwn', text: `*Sentiment:*\n${s.sentiment || '—'}` },
      ]
    },
  ]

  if (s.key_points?.length)
    blocks.push({ type: 'section', text: { type: 'mrkdwn', text: `*🔑 Key Points:*\n${s.key_points.slice(0, 4).map(p => `• ${p}`).join('\n')}` } })

  if (commits.length)
    blocks.push({ type: 'section', text: { type: 'mrkdwn', text: `*⚠️ Commitments (${commits.length}):*\n${commits.slice(0, 3).map(c => `• \`${c.risk_level}\` ${c.text.slice(0, 90)}`).join('\n')}` } })

  if (actions.length)
    blocks.push({ type: 'section', text: { type: 'mrkdwn', text: `*✅ Action Items (${actions.length}):*\n${actions.slice(0, 4).map(a => `• *${a.task}* — ${a.owner}`).join('\n')}` } })

  blocks.push({ type: 'divider' })
  blocks.push({ type: 'context', elements: [{ type: 'mrkdwn', text: 'Sent by *MeetIQ AI Meeting Intelligence*' }] })

  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ blocks })
  })
}
