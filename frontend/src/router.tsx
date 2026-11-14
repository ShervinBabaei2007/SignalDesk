// Route table: landing, dashboard, article reader and story page, plus a not-found page.
import { Link, createBrowserRouter, useParams, type LoaderFunctionArgs, type RouteObject } from 'react-router'
import { Dashboard, RootLayout } from '@/App'
import { Button } from '@/components/ui/button'
import { Landing } from '@/components/app/Landing'
import { ModeGate } from '@/components/app/ModeGate'
import { Reader } from '@/components/app/Reader'
import { StoryPage } from '@/components/app/StoryPage'
import { getToken, sessionMode } from '@/lib/api'
import { hasEntered } from '@/lib/entry'
import { entryLoader } from '@/lib/entryLoader'
import { registerRouter } from '@/lib/nav'

/** Reject non-numeric ids with a 404 before the page renders. */
function idLoader({ params }: LoaderFunctionArgs): number {
  if (!/^\d+$/.test(params.id ?? '')) throw new Response('Not found', { status: 404 })
  return Number(params.id)
}

/** The numeric `:id` URL param, already validated by `idLoader`. */
function useNumericIdParam(): number {
  return Number(useParams().id)
}

/** The article reader for the id in the URL. */
function ArticleRoute() {
  return <Reader id={useNumericIdParam()} />
}

/** The story page for the cluster id in the URL. */
function StoryRoute() {
  return <StoryPage id={useNumericIdParam()} />
}

/** Shown for unknown URLs and invalid ids. */
function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="mt-1 text-sm text-muted-foreground">That page doesn’t exist.</p>
      <Button className="mt-4" render={<Link to="/" />}>Back to the dashboard</Button>
    </div>
  )
}

/** The pages every mode shows: the dashboard, an article, a story, and a not-found page. */
function pages(): RouteObject[] {
  return [
    { index: true, element: <Dashboard /> },
    { path: 'article/:id', loader: idLoader, element: <ArticleRoute /> },
    { path: 'story/:id', loader: idLoader, element: <StoryRoute /> },
    { path: '*', element: <NotFound /> },
  ]
}

/** The shared layout around a set of pages. */
function layout(loader?: (args: LoaderFunctionArgs) => Response | null): RouteObject {
  return { element: <RootLayout />, errorElement: <RootLayout><NotFound /></RootLayout>, children: pages(), loader }
}

/** Browser router for the whole app: the landing page, the /demo and /workspace modes, and plain browsing. */
export const router = createBrowserRouter([
  { path: '/welcome', element: <Landing /> },
  { path: '/demo', element: <ModeGate mode="demo" />, children: [layout()] },
  { path: '/workspace', element: <ModeGate mode="workspace" />, children: [layout()] },
  layout(({ request }) => {
    // The hash is only meaningful for the page being opened; during a redirect `location` is still the old URL.
    const { pathname } = new URL(request.url)
    const hash = pathname === location.pathname ? location.hash : ''
    return entryLoader(pathname, hash, hasEntered(), sessionMode(getToken()))
  }),
])
registerRouter(router)
