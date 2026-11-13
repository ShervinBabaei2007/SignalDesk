import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getToken, setToken } from '@/lib/api'

const KEY = 'signaldesk-settings'

interface SettingsValue {
  compact: boolean
  setCompact: (v: boolean) => void
  token: string
  saveToken: (v: string) => void
}

const Ctx = createContext<SettingsValue | null>(null)

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

  const saveToken = useCallback((v: string) => {
    setToken(v.trim())
    setTokenState(v.trim())
  }, [])

  const value = useMemo(() => ({ compact, setCompact, token, saveToken }), [compact, setCompact, token, saveToken])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useSettings(): SettingsValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSettings must be used inside SettingsProvider')
  return v
}
