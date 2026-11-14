// Remembers whether this browser has already passed the landing page.

/** localStorage key set once a visitor has entered the dashboard. */
export const ENTERED_KEY = 'signaldesk-entered'

/** True when this browser has entered the dashboard before. */
export function hasEntered(): boolean {
  try {
    return localStorage.getItem(ENTERED_KEY) === '1'
  } catch {
    return false
  }
}

/** Forget that this browser has entered, so the landing page shows again. */
export function clearEntered() {
  try {
    localStorage.removeItem(ENTERED_KEY)
  } catch {
    /* storage unavailable: nothing to clear */
  }
}

/** Remember that this browser has entered, so the landing page is skipped next time. */
export function markEntered() {
  try {
    localStorage.setItem(ENTERED_KEY, '1')
  } catch {
    /* storage unavailable (private mode): the landing page just shows again */
  }
}
