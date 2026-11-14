import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getToken, setToken } from '@/lib/api'

const KEY = 'signaldesk-settings'

interface SettingsValue {
  compact: boolean
  setCompact: (v: boolean) => void
  /** Group reports of the same event into one story card. */
  grouped: boolean
  setGrouped: (v: boolean) => void
  token: string
  saveToken: (v: string) => void
}

const Ctx = createContext<SettingsValue | null>(null)

function readSaved(key: string, fallback: boolean): boolean {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '{}')[key]
    return typeof v === 'boolean' ? v : fallback
  } catch {
    return fallback
  }
}

function writeSaved(key: string, value: boolean) {
  try {
    const prev = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    localStorage.setItem(KEY, JSON.stringify({ ...prev, [key]: value }))
  } catch {
    /* storage unavailable: the choice just won't persist */
  }
}

function readCompact(): boolean {
  const q = new URLSearchParams(location.search)
  if (q.has('compact')) return q.get('compact') !== '0'
  try {
    return !!JSON.parse(localStorage.getItem(KEY) ?? '{}').compact
  } catch {
    return false
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [compact, setCompactState] = useState(readCompact)
  const [token, setTokenState] = useState(getToken)
  const [grouped, setGroupedState] = useState(() => readSaved('grouped', true))

  useEffect(() => {
    document.documentElement.dataset.compact = compact ? 'on' : 'off'
  }, [compact])

  const setCompact = useCallback((v: boolean) => {
    setCompactState(v)
    try {
      const prev = JSON.parse(localStorage.getItem(KEY) ?? '{}')
      localStorage.setItem(KEY, JSON.stringify({ ...prev, compact: v }))
    } catch {
      /* ignore */
    }
  }, [])

  const setGrouped = useCallback((v: boolean) => {
    setGroupedState(v)
    writeSaved('grouped', v)
  }, [])

  const saveToken = useCallback((v: string) => {
    setToken(v.trim())
    setTokenState(v.trim())
  }, [])

  const value = useMemo(
    () => ({ compact, setCompact, grouped, setGrouped, token, saveToken }),
    [compact, setCompact, grouped, setGrouped, token, saveToken],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useSettings(): SettingsValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSettings must be used inside SettingsProvider')
  return v
}
