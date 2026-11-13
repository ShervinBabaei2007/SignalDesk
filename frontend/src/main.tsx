import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import App from '@/App'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { DashboardProvider } from '@/hooks/useDashboard'
import { SettingsProvider } from '@/hooks/useSettings'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem storageKey="signaldesk-theme">
      <SettingsProvider>
        <TooltipProvider delay={150}>
          <DashboardProvider>
            <App />
          </DashboardProvider>
          <Toaster position="bottom-center" />
        </TooltipProvider>
      </SettingsProvider>
    </ThemeProvider>
  </StrictMode>,
)
