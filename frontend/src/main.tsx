// App entry: mounts React with the theme, settings, library and dashboard providers.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import { RouterProvider } from 'react-router'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { DashboardProvider } from '@/hooks/useDashboard'
import { LibraryProvider } from '@/hooks/useLibrary'
import { SettingsProvider } from '@/hooks/useSettings'
import { router } from '@/router'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem storageKey="signaldesk-theme">
      <SettingsProvider>
        <TooltipProvider delay={150}>
          <LibraryProvider>
            <DashboardProvider>
              <RouterProvider router={router} />
            </DashboardProvider>
          </LibraryProvider>
          <Toaster position="bottom-center" />
        </TooltipProvider>
      </SettingsProvider>
    </ThemeProvider>
  </StrictMode>,
)
