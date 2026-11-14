// A router link that stays inside the current mode: from /demo/... a link to /story/2 goes to /demo/story/2.
import { Link, useLocation, type LinkProps } from 'react-router'
import { withBase } from '@/lib/mode'

/** Like react-router's Link, but `to` is an in-app path that gets the current mode's prefix. */
export function AppLink({ to, ...props }: Omit<LinkProps, 'to'> & { to: string }) {
  const { pathname } = useLocation()
  return <Link to={withBase(pathname, to)} {...props} />
}
