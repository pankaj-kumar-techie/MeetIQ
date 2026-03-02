export class MeetingStore {
  #state = { activeMeeting: null, recording: false }

  constructor() {
    this.#loadSync();
  }

  async #loadSync() {
    const data = await chrome.storage.local.get(['activeMeeting', 'recording']);
    if (data.activeMeeting) {
      this.#state.activeMeeting = data.activeMeeting;
      this.#state.recording = !!data.recording;
    }
  }

  async ensureLoaded() {
    await this.#loadSync();
  }

  getState() { return { ...this.#state, active: !!this.#state.activeMeeting } }
  getActiveMeeting() { return this.#state.activeMeeting }
  async setActiveMeeting(meeting) {
    this.#state = { activeMeeting: meeting, recording: true }
    await chrome.storage.local.set({ activeMeeting: meeting, recording: true })
  }
  async updateActiveMeeting(patch) {
    if (!this.#state.activeMeeting) return
    this.#state.activeMeeting = { ...this.#state.activeMeeting, ...patch }
    await chrome.storage.local.set({ activeMeeting: this.#state.activeMeeting })
  }
  async clearActiveMeeting() {
    this.#state = { activeMeeting: null, recording: false }
    await chrome.storage.local.remove(['activeMeeting', 'recording'])
  }
  async setMeetingResult(meetingId, result) {
    const { meetings = [] } = await chrome.storage.local.get('meetings')
    // Remove if already exists (avoids duplicates)
    const filtered = meetings.filter(m => m.meetingId !== meetingId)
    filtered.unshift({
      meetingId,
      result,
      status: 'done', // CRITICAL: needs status for popup.js logic
      savedAt: Date.now()
    })
    await chrome.storage.local.set({ meetings: filtered.slice(0, 50) })
  }
  async getAllMeetings() {
    const { meetings = [] } = await chrome.storage.local.get('meetings')
    return meetings
  }
  async deleteMeeting(meetingId) {
    const { meetings = [] } = await chrome.storage.local.get('meetings')
    await chrome.storage.local.set({ meetings: meetings.filter(m => m.meetingId !== meetingId) })
    return { ok: true }
  }
}
