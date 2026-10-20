import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import CssBaseline from '@mui/material/CssBaseline'
import LoadingBar from './components/LoadingBar'
import { ThemeProvider } from '@mui/material/styles'
import { CacheProvider } from '@emotion/react'
import createCache from '@emotion/cache'
import { prefixer } from 'stylis'
import rtlPlugin from '@mui/stylis-plugin-rtl'
import { AuthProvider, useAuth } from './auth'
import { buildTheme, type ThemeName } from './theme'
import { setTheme as apiSetTheme } from './api'
import { I18nProvider, useI18n, type Lang } from './i18n'
import { HOME_PAGE, pageTitle } from './menu'
import AppShell from './components/AppShell'
import LoginPage from './pages/LoginPage'
import { PAGES } from './pages/registry'
import ErrorBoundary from './components/ErrorBoundary'

const THEME_KEY = 'ohi_theme'

// Emotion-кэши стилей MUI: для иврита — с плагином, зеркалящим CSS (margin-left → margin-right и т.п.)
const cacheLtr = createCache({ key: 'mui' })
const cacheRtl = createCache({ key: 'muirtl', stylisPlugins: [prefixer, rtlPlugin] })

function useThemeName(): [ThemeName, () => void] {
  const { loggedIn, upr, setUpr } = useAuth()
  const [name, setName] = useState<ThemeName>(() => {
    const saved = localStorage.getItem(THEME_KEY)
    return saved === 'black' || saved === 'white' ? saved : 'white'
  })
  const toggle = useCallback(() => {
    const next: ThemeName = name === 'black' ? 'white' : 'black'
    setName(next)
    localStorage.setItem(THEME_KEY, next)
    if (loggedIn) {
      // синхронизируем тему на сервере (select_theme_form)
      apiSetTheme(next, upr?.select_language)
        .then((r) => r.ok && setUpr(r.upr))
        .catch(() => undefined)
    }
  }, [name, loggedIn, upr?.select_language, setUpr])
  return [name, toggle]
}

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { loggedIn, refresh } = useAuth()
  const location = useLocation()
  // Сессия может быть уже открыта сервером без формы входа (ссылка из чат-бота /one_new/<id>/ → cookie):
  // прежде чем отправить на вход, спрашиваем сервер (/api/v2/me).
  const [checking, setChecking] = useState(!loggedIn)
  const asked = useRef(false)
  useEffect(() => {
    if (loggedIn || asked.current) return
    asked.current = true
    refresh().finally(() => setChecking(false))
  }, [loggedIn, refresh])
  if (loggedIn) return children
  if (checking) return <LoadingBar loading />
  return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
}

/** Маршрут /:page/ — страница (форма); сессия — в cookie, user_id в адресах нет. */
function FormRoute() {
  const { page = '' } = useParams()
  const Page = PAGES[page]
  if (!Page) return <Navigate to={`/${HOME_PAGE}/`} replace />
  return (
    <Suspense fallback={<LoadingBar loading />}>
      <Page key={page} />
    </Suspense>
  )
}

function Shell() {
  const [themeName, toggleTheme] = useThemeName()
  const { upr } = useAuth()
  const { t, lang } = useI18n()
  const rtl = lang === 'he'
  const theme = useMemo(() => buildTheme(themeName, upr?.colors, rtl ? 'rtl' : 'ltr'), [themeName, upr?.colors, rtl])
  const location = useLocation()
  const page = location.pathname.split('/').filter(Boolean)[0] ?? ''

  return (
    <CacheProvider value={rtl ? cacheRtl : cacheLtr}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<LoginPage themeName={themeName} onToggleTheme={toggleTheme} />} />
          <Route
            path="/:page/*"
            element={
              <RequireAuth>
                <AppShell title={pageTitle(page, t, Boolean(upr?.admin))} themeName={themeName} onToggleTheme={toggleTheme}>
                  <ErrorBoundary>
                    <Routes>
                      <Route path="/" element={<FormRoute />} />
                    </Routes>
                  </ErrorBoundary>
                </AppShell>
              </RequireAuth>
            }
          />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </ErrorBoundary>
    </ThemeProvider>
    </CacheProvider>
  )
}

function HomeRedirect() {
  const { loggedIn } = useAuth()
  return <Navigate to={loggedIn ? `/${HOME_PAGE}/` : '/login'} replace />
}

/** Язык SPA синхронизируем с select_language на сервере (как select в старой форме). */
function LangSync({ children }: { children: React.ReactElement }) {
  const { loggedIn, upr, setUpr } = useAuth()
  const onChange = useCallback(
    (l: Lang) => {
      if (loggedIn) apiSetTheme(upr?.theme ?? 'white', l).then((r) => r.ok && setUpr(r.upr)).catch(() => undefined)
    },
    [loggedIn, upr?.theme, setUpr],
  )
  return <I18nProvider onChange={onChange}>{children}</I18nProvider>
}

/**
 * Ссылки на другие сайты — в новой вкладке (правило оформления): один обработчик на весь документ,
 * поэтому не нужно помнить про target="_blank" у каждой ссылки. Свои адреса (тот же origin) не трогаем.
 */
function useExternalLinksInNewTab() {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!a || a.hasAttribute('download') || (a.target && a.target !== '_self')) return
      let url: URL
      try {
        url = new URL(a.href, window.location.href)
      } catch {
        return
      }
      if (!/^https?:$/.test(url.protocol) || url.origin === window.location.origin) return
      e.preventDefault()
      window.open(url.href, '_blank', 'noopener,noreferrer')
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])
}

export default function App() {
  useExternalLinksInNewTab()
  return (
    <BrowserRouter>
      <AuthProvider>
        <LangSync>
          <Shell />
        </LangSync>
      </AuthProvider>
    </BrowserRouter>
  )
}
