; (function () {
  if (window.__meetiq_injected) return
  window.__meetiq_injected = true

  const PLATFORM = detectPlatform()
  if (!PLATFORM) return

  // Notify background that we're on a meeting page
  chrome.runtime.sendMessage({
    type: 'MEETING_DETECTED',
    payload: { platform: PLATFORM, url: location.href },
  })

  // Run auto-detection after a short delay so the page title has loaded
  setTimeout(runMeetingTypeDetection, 1500)
  // Re-run when participants load (may take a few seconds on join)
  setTimeout(runMeetingTypeDetection, 6000)

  observeParticipants()
  observeMeetingEnd()

  // ─── Platform detection ────────────────────────────────────────────────────
  function detectPlatform() {
    const h = location.hostname
    if (h.includes('meet.google.com')) return 'google-meet'
    if (h.includes('teams.microsoft.com')) return 'teams'
    if (h.includes('whereby.com')) return 'whereby'
    if (h.includes('zoom.us')) return 'zoom'
    return null
  }

  // ─── Smart Meeting Type Detection ─────────────────────────────────────────
  function runMeetingTypeDetection() {
    const signals = []
    let scores = {
      'Discovery call': 0,
      'Sales demo': 0,
      'Interview': 0,
      'Project kickoff': 0,
      'Status update': 0,
      'Technical review': 0,
    }

    // Signal 1: page / document title keywords
    const title = (document.title || '').toLowerCase()
    const url = location.href.toLowerCase()
    const text = (title + ' ' + url)

    const titleKeywords = {
      'Discovery call': ['discovery', 'intro call', 'intro meeting', 'first call', 'exploratory'],
      'Sales demo': ['demo', 'product demo', 'sales call', 'pricing', 'proposal', 'pitch'],
      'Interview': ['interview', 'screening', 'hiring', 'candidate', 'hr round', 'onsite'],
      'Project kickoff': ['kickoff', 'kick-off', 'kick off', 'launch', 'onboarding', 'project start'],
      'Status update': ['standup', 'stand-up', 'sync', 'status', 'check-in', 'weekly', 'daily', 'sprint', 'retro'],
      'Technical review': ['review', 'architecture', 'design review', 'code review', 'tech', 'sprint review', 'planning'],
    }

    for (const [type, keywords] of Object.entries(titleKeywords)) {
      for (const kw of keywords) {
        if (text.includes(kw)) {
          scores[type] += 3
          signals.push(`title:"${kw}"`)
        }
      }
    }

    // Signal 2: participant count heuristics
    const participants = getParticipants()
    const count = participants.length
    if (count === 2) {
      scores['Discovery call'] += 2
      scores['Sales demo'] += 2
      scores['Interview'] += 3
      signals.push('participants:1on1')
    } else if (count >= 3 && count <= 6) {
      scores['Project kickoff'] += 2
      scores['Technical review'] += 2
      scores['Status update'] += 1
      signals.push('participants:small-group')
    } else if (count > 6) {
      scores['Status update'] += 3
      scores['Project kickoff'] += 2
      signals.push('participants:large-group')
    }

    // Signal 3: meeting time heuristics (Mon/Wed morning = standups)
    const day = new Date().getDay()
    const hour = new Date().getHours()
    if ((day >= 1 && day <= 5) && hour >= 9 && hour <= 10) {
      scores['Status update'] += 1
      signals.push('time:morning-weekday')
    }

    // Pick the winner
    const winner = Object.entries(scores).sort((a, b) => b[1] - a[1])[0]
    if (!winner || winner[1] === 0) return   // not enough signal

    const [suggestedType, bestScore] = winner
    // Confidence: normalise to 0–1 relative to max possible (≈10)
    const confidence = Math.min(1, bestScore / 8)

    chrome.runtime.sendMessage({
      type: 'MEETING_TYPE_HINT',
      payload: { suggestedType, confidence, signals },
    }).catch(() => { })
  }

  // ─── Participant scraping ──────────────────────────────────────────────────
  function getParticipants() {
    try {
      if (PLATFORM === 'google-meet') {
        const names = new Set()
        document.querySelectorAll('.dwSJ2e, [data-self-name]').forEach(el => {
          const n = el.textContent?.trim() || el.getAttribute('data-self-name')
          if (n && n.length > 1) names.add(n)
        })
        return [...names]
      }
      if (PLATFORM === 'teams') {
        const names = []
        document.querySelectorAll('[data-tid="roster-participant"]').forEach(el => {
          const n = el.querySelector('[class*="participantItemName"]')?.textContent?.trim()
          if (n) names.push(n)
        })
        return names
      }
      if (PLATFORM === 'whereby') {
        const names = []
        document.querySelectorAll('[class*="participantName"]').forEach(el => {
          if (el.textContent?.trim()) names.push(el.textContent.trim())
        })
        return names
      }
    } catch (e) { }
    return []
  }

  function observeParticipants() {
    let last = 0
    setInterval(() => {
      const p = getParticipants()
      if (p.length !== last) {
        last = p.length
        chrome.runtime.sendMessage({
          type: 'PARTICIPANTS_UPDATE',
          payload: { participants: p, platform: PLATFORM },
        }).catch(() => { })
        // Re-score meeting type when participant count changes
        runMeetingTypeDetection()
      }
    }, 5000)
  }

  function observeMeetingEnd() {
    const ob = new MutationObserver(() => {
      const ended = document.querySelector('[data-call-ended], .crqnQb, [data-tid="call-ended"]')
      if (ended) {
        chrome.runtime.sendMessage({ type: 'MEETING_ENDED_BY_PLATFORM' }).catch(() => { })
        ob.disconnect()
      }
    })
    ob.observe(document.body, { childList: true, subtree: true })
  }
})()
