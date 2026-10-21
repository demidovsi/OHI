import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import FormControl from '@mui/material/FormControl'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import type { ThemeName } from '../theme'
import { useAuth } from '../auth'
import type { FlashMessage, SiteInfo } from '../api'
import { ApiError, info as apiInfo, legacyRedirectToRoute } from '../api'
import { LANGS, isLang, useI18n } from '../i18n'
import { HOME_PAGE } from '../menu'

// Вход: имя, пароль, язык и тема оформления; внизу — сайт, версия, устройство, страна и город, текущее время с
// часовым поясом (как на входе sozd-web).
// Форма — по высоте окна (сама страница не прокручивается; при очень низком окне прокручивается
// карточка), отступы и выравнивание — логические (start/end), поэтому в RTL (иврит) зеркалятся.

const CLOCK_LOCALE: Record<string, string> = { ru: 'ru-RU', en: 'en-GB', he: 'he-IL' }

/** Текущее время браузера с часовым поясом (по нему сервер при входе берёт пояс пользователя). */
function useClock(lang: string) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const offset = -now.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const hh = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0')
  const mm = String(Math.abs(offset) % 60).padStart(2, '0')
  return `${now.toLocaleString(CLOCK_LOCALE[lang] ?? 'ru-RU')} (GMT${sign}${hh}:${mm})`
}

interface Props {
  themeName: ThemeName
  onToggleTheme: () => void
}

export default function LoginPage({ themeName, onToggleTheme }: Props) {
  const { login } = useAuth()
  const navigate = useNavigate()
  const { t, lang, setLang } = useI18n()
  const [userName, setUserName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<FlashMessage[]>([])
  const [site, setSite] = useState<SiteInfo | null>(null)
  const clock = useClock(lang)

  // страна и город приходят на языке формы — перезапрашиваем при смене языка
  useEffect(() => {
    apiInfo(lang).then(setSite).catch(() => undefined)
  }, [lang])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessages([])
    try {
      const res = await login(userName.trim(), password, lang)
      if (res.ok && res.upr) {
        // сервер возвращает страницу, с которой пришёл не вошедший пользователь, иначе — главную
        navigate(res.redirect ? legacyRedirectToRoute(res.redirect) : `/${HOME_PAGE}/`, { replace: true })
      } else {
        setMessages(res.messages.length ? res.messages : [['error', t('Неверное имя пользователя или пароль')]])
      }
    } catch (err) {
      const e2 = err as ApiError
      setMessages(e2.messages?.length ? e2.messages : [['error', e2.message || t('Ошибка входа')]])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ height: '100vh', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
      <Card sx={{ width: '100%', maxWidth: 400, maxHeight: '100%', overflow: 'auto' }} elevation={3}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography variant="h5" sx={{ mb: 0.5, fontWeight: 600, flexGrow: 1 }}>
              OHI
            </Typography>
            <Tooltip title={themeName === 'black' ? t('Светлая тема') : t('Тёмная тема')}>
              <IconButton size="small" onClick={onToggleTheme} aria-label={t('Тема оформления')}>
                {themeName === 'black' ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('Новости Израиля: ленты новостей и аналитика')}
          </Typography>
          <form onSubmit={onSubmit}>
            <Stack spacing={2}>
              {messages.map(([cat, text], i) => (
                <Alert key={i} severity={cat === 'warning' ? 'warning' : 'error'} sx={{ whiteSpace: 'pre-wrap' }}>
                  {text}
                </Alert>
              ))}
              <TextField
                label={t('Пользователь')}
                name="user_name"
                autoComplete="username"
                placeholder={t('Введите имя пользователя')}
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                autoFocus
                required
                // имя и пароль — латиница: направление ввода по тексту, а не по языку интерфейса
                slotProps={{ htmlInput: { dir: 'auto' } }}
              />
              <TextField
                label={t('Пароль')}
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder={t('Введите пароль')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                slotProps={{ htmlInput: { dir: 'auto' } }}
              />
              <FormControl>
                <InputLabel id="login_lang">{t('Язык')}</InputLabel>
                <Select
                  labelId="login_lang"
                  label={t('Язык')}
                  value={lang}
                  onChange={(e) => {
                    const v = e.target.value
                    if (isLang(v)) setLang(v)
                  }}
                >
                  {LANGS.map((l) => (
                    <MenuItem key={l.key} value={l.key}>
                      {l.key.toUpperCase()} - {l.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button type="submit" variant="contained" size="medium" disabled={busy}>
                {busy ? t('Вход…') : t('Войти')}
              </Button>
            </Stack>
          </form>
          <Box sx={{ mt: 3, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary" component="div">
              {site ? `${site.site} · ${t(site.device)} · [${site.version}]` : 'OHI-web'}
            </Typography>
            <Typography variant="caption" color="text.secondary" component="div">
              {[site?.country, site?.city].filter(Boolean).join(', ')}
            </Typography>
            <Typography variant="caption" color="text.secondary" component="div" dir="ltr">
              {clock}
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  )
}
