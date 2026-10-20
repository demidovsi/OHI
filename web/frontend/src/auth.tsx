import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from './api'
import type { Upr } from './api'

// Сессия пользователя — на сервере, в cookie браузера (Flask session); user_id в адресах нет.
// Тут храним только последний известный upr (для мгновенной отрисовки); «вошёл» — upr есть.
// Если сессия на сервере истекла, первый запрос формы вернёт 401 → logout() → страница входа.

const KEY = 'ohi_v2_auth'

interface AuthState {
  upr: Upr | null
}

interface AuthContextValue extends AuthState {
  loggedIn: boolean
  login: (userName: string, password: string, language?: string) => Promise<api.LoginResponse>
  logout: () => void
  setUpr: (upr: Upr | null) => void
  refresh: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function load(): AuthState {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw) as AuthState
  } catch {
    /* ignore */
  }
  return { upr: null }
}

function save(state: AuthState) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* ignore */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(load)

  useEffect(() => save(state), [state])

  const login = useCallback(async (userName: string, password: string, language = 'ru') => {
    // Тема, выбранная на форме входа (запоминается в localStorage), главнее темы прошлой сессии.
    const saved = localStorage.getItem('ohi_theme')
    const theme = saved === 'black' || saved === 'white' ? saved : state.upr?.theme ?? 'white'
    const res = await api.login(userName, password, theme, language)
    if (res.ok && res.upr) {
      setState({ upr: res.upr })
    }
    return res
  }, [state.upr?.theme])

  const logout = useCallback(() => {
    setState({ upr: null })
    api.logout().catch(() => undefined) // удалить сессию на сервере (cookie и состояние форм)
  }, [])

  const setUpr = useCallback((upr: Upr | null) => {
    setState((s) => (upr ? { upr } : s))
  }, [])

  const refresh = useCallback(async () => {
    try {
      const r = await api.me()
      if (r.ok) {
        setState({ upr: r.upr })
        return true
      }
    } catch {
      /* fallthrough */
    }
    setState({ upr: null })
    return false
  }, [])

  const value = useMemo(
    () => ({ ...state, loggedIn: state.upr != null, login, logout, setUpr, refresh }),
    [state, login, logout, setUpr, refresh],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
