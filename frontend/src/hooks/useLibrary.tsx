// Context for the reader's saved and read articles, kept in localStorage.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { addRead, parseIds, toggleId } from '@/lib/library'

/** localStorage key for saved ids. */
const SAVED_KEY = 'signaldesk-saved'
/** localStorage key for read ids. */
const READ_KEY = 'signaldesk-read'

/** Saved and read article state and actions. */
interface LibraryValue {
  /** Saved article ids, newest first. */
  saved: number[]
  isSaved: (id: number) => boolean
  toggleSaved: (id: number) => void
  isRead: (id: number) => boolean
  markRead: (id: number) => void
}

/** Context holding the library value. */
const Ctx = createContext<LibraryValue | null>(null)

/** Load an id list from localStorage, or [] when unavailable. */
function load(key: string): number[] {
  try {
    return parseIds(localStorage.getItem(key))
  } catch {
    return []
  }
}

/** Store an id list in localStorage, ignoring failures. */
function save(key: string, ids: number[]) {
  try {
    localStorage.setItem(key, JSON.stringify(ids))
  } catch {
    /* storage unavailable (private mode): the library just won't persist */
  }
}

/** Saved and read articles, kept in this browser only (no account needed). */
export function LibraryProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState<number[]>(() => load(SAVED_KEY))
  const [read, setRead] = useState<number[]>(() => load(READ_KEY))
  const readSet = useMemo(() => new Set(read), [read])

  // keep several open tabs in step
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === SAVED_KEY) setSaved(load(SAVED_KEY))
      if (e.key === READ_KEY) setRead(load(READ_KEY))
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const toggleSaved = useCallback((id: number) => {
    setSaved((prev) => {
      const next = toggleId(prev, id)
      save(SAVED_KEY, next)
      return next
    })
  }, [])

  const markRead = useCallback((id: number) => {
    setRead((prev) => {
      if (prev[0] === id) return prev
      const next = addRead(prev, id)
      save(READ_KEY, next)
      return next
    })
  }, [])

  const value = useMemo<LibraryValue>(
    () => ({
      saved,
      isSaved: (id) => saved.includes(id),
      toggleSaved,
      isRead: (id) => readSet.has(id),
      markRead,
    }),
    [saved, readSet, toggleSaved, markRead],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** Read the library; must be used inside LibraryProvider. */
export function useLibrary(): LibraryValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useLibrary must be used inside LibraryProvider')
  return v
}
