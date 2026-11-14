// Route wrapper for /demo and /workspace: makes sure the visitor has that kind of session before showing the app.
import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Outlet, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useDashboard } from '@/hooks/useDashboard'
import { useSettings } from '@/hooks/useSettings'
import { getToken, sessionMode, startDemo, startWorkspace } from '@/lib/api'
import { markEntered } from '@/lib/entry'
import type { PrefixMode } from '@/lib/mode'

/** True when the stored token already fits the mode (the owner's token fits both). */
function fits(mode: PrefixMode, token: string): boolean {
  const have = sessionMode(token)
  return have === mode || have === 'owner'
}

/** Starts (or resumes) the demo or workspace session for the URL, then renders the app inside it. */
export function ModeGate({ mode }: { mode: PrefixMode }) {
  const { token, saveToken } = useSettings()
  const { refreshAll } = useDashboard()
  const navigate = useNavigate()
  const [ready, setReady] = useState(() => fits(mode, token))
  const started = useRef(false)

  useEffect(() => {
    if (ready || started.current) return
    started.current = true
    void (async () => {
      if (mode === 'workspace') {
        const r = await startWorkspace()
        if (!r.ok) {
          toast.error(r.message ?? 'Could not start a workspace')
          navigate('/welcome', { replace: true })
          return
        }
        toast.success('Your workspace is ready: add feeds, watch terms and run ingests')
      } else {
        const live = await startDemo()
        toast.success(live ? 'Demo started: you can run live ingests' : 'Welcome! This deployment is read-only')
      }
      saveToken(getToken()) // sync the settings state with the token the start call stored
      markEntered()
      void refreshAll() // the data on screen belongs to whichever mode the visitor was in before
      setReady(true)
    })()
  }, [ready, mode, navigate, saveToken, refreshAll])

  if (!ready) {
    return (
      <div className="grid min-h-dvh place-items-center text-sm text-muted-foreground">
        <span className="flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {mode === 'workspace' ? 'Opening your workspace…' : 'Starting the demo…'}
        </span>
      </div>
    )
  }
  return <Outlet />
}
