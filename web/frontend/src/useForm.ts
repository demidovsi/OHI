import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as api from './api'
import type { FlashMessage, FormFields, Par } from './api'
import { useAuth } from './auth'

/**
 * Состояние одной серверной формы.
 *
 * Первая загрузка — GET (как открытие страницы в старом UI). Любое действие
 * пользователя — POST с полным набором полей формы + имя нажатой кнопки,
 * ровно как FormData старой HTML-формы. Сервер сам хранит состояние фильтров
 * между запросами (сессия в cookie, common.py), поэтому клиент отправляет только то, что
 * изменилось, плюс базовые поля.
 */
export function useForm(page: string, args: string[] = []) {
  const { loggedIn, setUpr, logout } = useAuth()
  const navigate = useNavigate()
  const [par, setPar] = useState<Par | null>(null)
  const [messages, setMessages] = useState<FlashMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const argsKey = args.join('/')

  const run = useCallback(
    async (fields?: FormFields) => {
      if (!loggedIn) {
        navigate('/login', { replace: true })
        return
      }
      abortRef.current?.abort()
      const ctl = new AbortController()
      abortRef.current = ctl
      setLoading(true)
      setError(null)
      try {
        const res = await api.form(page, argsKey ? argsKey.split('/') : [], fields, ctl.signal)
        if (ctl.signal.aborted) return
        if (res.upr) setUpr(res.upr)
        setMessages(res.messages)
        if (res.redirect) {
          const route = api.legacyRedirectToRoute(res.redirect)
          if (route === '/login') logout()
          navigate(route)
          return
        }
        setPar(res.par)
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
        const err = e as api.ApiError
        if (err.status === 401) {
          logout()
          navigate('/login', { replace: true })
          return
        }
        setError(err.message)
      } finally {
        if (!ctl.signal.aborted) setLoading(false)
      }
    },
    [page, argsKey, loggedIn, navigate, setUpr, logout],
  )

  useEffect(() => {
    run()
    return () => abortRef.current?.abort()
  }, [run])

  const submit = useCallback((fields: FormFields) => run(fields), [run])
  const dismiss = useCallback((i: number) => setMessages((m) => m.filter((_, j) => j !== i)), [])

  return { par, messages, loading, error, submit, reload: () => run(), dismiss }
}
