// Клиент JSON-API /api/v2 (см. api_v2.py на бэкенде).
//
// Контракт: тело запроса — form-encoded с теми же именами полей/кнопок, что
// и у старых HTML-форм. Ответ формы: { par, upr, messages, redirect }.

export type FlashMessage = [category: string, text: string]

export interface Colors {
  background: string
  color_combobox: string
  color_select: string
  blue: string
  green: string
  black: string
  black2: string
  lightgray: string
  red: string
  yellow: string
  dark_violet: string
  salmon: string
  select_background: string
  select_color: string
  light_blue: string
}

export interface Upr {
  user_name: string
  schema: string | null
  admin: boolean
  theme: 'white' | 'black'
  select_language: string
  version: string
  colors: Colors
  time_zone: number
  device: string
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Par = Record<string, any>

export interface FormResponse {
  par: Par
  upr: Upr | null
  messages: FlashMessage[]
  redirect: string | null
}

export interface LoginResponse {
  ok: boolean
  upr?: Upr
  redirect?: string
  messages: FlashMessage[]
}

export class ApiError extends Error {
  status: number
  messages: FlashMessage[]
  constructor(status: number, message: string, messages: FlashMessage[] = []) {
    super(message)
    this.status = status
    this.messages = messages
  }
}

const BASE = '/api/v2'

export type FormFields = Record<string, string | number | boolean | null | undefined>

export function toFormData(fields: FormFields): FormData {
  const fd = new FormData()
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null || v === false) continue
    fd.append(k, v === true ? '1' : String(v))
  }
  return fd
}

async function parse<T>(r: Response): Promise<T> {
  const text = await r.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    throw new ApiError(r.status, text.slice(0, 200))
  }
  if (!r.ok) {
    const d = (data ?? {}) as { error?: string; messages?: FlashMessage[] }
    throw new ApiError(r.status, d.error ?? r.statusText, d.messages ?? [])
  }
  return data as T
}

export async function login(userName: string, password: string, theme: string, language = 'ru') {
  // time_now в формате Date.prototype.toString() — бэкенд парсит "GMT+0300".
  const fd = toFormData({
    user_name: userName,
    password,
    time_now: new Date().toString(),
    theme,
    select_language: language,
  })
  const r = await fetch(`${BASE}/login`, { method: 'POST', body: fd })
  return parse<LoginResponse>(r)
}

export async function me() {
  const r = await fetch(`${BASE}/me`)
  return parse<{ ok: boolean; upr: Upr }>(r)
}

/** Выход: сессия на сервере (cookie и состояние форм) удаляется. */
export async function logout() {
  const r = await fetch(`${BASE}/logout`, { method: 'POST' })
  return parse<{ ok: boolean }>(r)
}

export async function setTheme(theme: string, language?: string) {
  const fd = toFormData({ select_theme_form: theme, select_language: language })
  const r = await fetch(`${BASE}/set_theme`, { method: 'POST', body: fd })
  return parse<{ ok: boolean; upr: Upr }>(r)
}

/**
 * Запрос формы.
 * GET (fields === undefined) — первая загрузка, как открытие страницы в старом UI.
 * POST с полями — действие пользователя (кнопка/фильтр/страница).
 */
export async function form(
  page: string,
  args: string[] = [],
  fields?: FormFields,
  signal?: AbortSignal,
): Promise<FormResponse> {
  const path = [page, ...args].map(encodeURIComponent).join('/')
  const url = `${BASE}/form/${path}/`
  const r = fields
    ? await fetch(url, { method: 'POST', body: toFormData(fields), signal })
    : await fetch(url, { signal })
  return parse<FormResponse>(r)
}

/**
 * Скачивание файла страницы page (файлы GCS) — обычный submit формы на /api/v2/form/<page>/, ответ — файл
 * (send_file). Открывается в новой вкладке, чтобы не уводить SPA.
 */
export function downloadFile(page: string, fields: FormFields) {
  const f = document.createElement('form')
  f.method = 'POST'
  f.action = `${BASE}/form/${encodeURIComponent(page)}/`
  f.target = '_blank'
  f.style.display = 'none'
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null || v === false) continue
    const i = document.createElement('input')
    i.type = 'hidden'
    i.name = k
    i.value = v === true ? '1' : String(v)
    f.appendChild(i)
  }
  document.body.appendChild(f)
  f.submit()
  f.remove()
}

/** Путь старого UI ('/inform/<uid>/<law>/') → роут SPA ('/inform/<uid>/<law>/'). */
export function legacyRedirectToRoute(redirect: string): string {
  if (redirect === '/login/' || redirect === '/') return '/login'
  return redirect.replace(/\/+$/, '/')
}
