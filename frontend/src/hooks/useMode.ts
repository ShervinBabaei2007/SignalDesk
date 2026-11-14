// The mode the interface is showing, and which features it locks.
import { useLocation } from 'react-router'
import { useSettings } from '@/hooks/useSettings'
import { sessionMode, type SessionMode } from '@/lib/api'
import { isLocked, modeFromPath, type Feature, type PrefixMode } from '@/lib/mode'

/** The current mode: the URL prefix wins (`/demo`, `/workspace`), otherwise the stored token decides. */
export function useMode(): { mode: SessionMode; prefix: PrefixMode | null; locked: (feature: Feature) => boolean } {
  const { pathname } = useLocation()
  const { token } = useSettings()
  const prefix = modeFromPath(pathname)
  const mode = prefix ?? sessionMode(token)
  return { mode, prefix, locked: (feature) => isLocked(mode, feature) }
}
