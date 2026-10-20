import { useState, type ReactNode } from 'react'
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Collapse from '@mui/material/Collapse'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import Button from '@mui/material/Button'
import List from '@mui/material/List'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Toolbar from '@mui/material/Toolbar'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import MenuIcon from '@mui/icons-material/Menu'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import LogoutIcon from '@mui/icons-material/Logout'
import ExpandLess from '@mui/icons-material/ExpandLess'
import ExpandMore from '@mui/icons-material/ExpandMore'
import UnfoldLessIcon from '@mui/icons-material/UnfoldLess'
import UnfoldMoreIcon from '@mui/icons-material/UnfoldMore'
import { MENU, visibleGroups } from '../menu'
import { useAuth } from '../auth'
import { LANGS, useI18n } from '../i18n'

/** Надстрочная пометка «adm» у строк меню, которые видит только администратор. */
function AdmMark() {
  return (
    <Box component="sup" sx={{ color: 'warning.main', fontSize: '0.65em', fontWeight: 700, ml: 0.5, lineHeight: 0 }}>
      adm
    </Box>
  )
}

const DRAWER_WIDTH = 280 // ширина меню по умолчанию; меняется сплиттером на правом краю меню
const MENU_WIDTH_KEY = 'ohi_split_menu' // тот же префикс, что у SplitPane
const MENU_OPEN_KEY = 'ohi_menu_open' // раскрытые группы меню
const MENU_MIN = 180
const MENU_MAX = 480

function readMenuWidth() {
  try {
    const v = parseFloat(localStorage.getItem(MENU_WIDTH_KEY) ?? '')
    return v >= MENU_MIN && v <= MENU_MAX ? v : DRAWER_WIDTH
  } catch {
    return DRAWER_WIDTH
  }
}
const DRAWER_KEY = 'ohi_drawer_open'

interface Props {
  title: string
  themeName: 'white' | 'black'
  onToggleTheme: () => void
  children: ReactNode
}

export default function AppShell({ title, themeName, onToggleTheme, children }: Props) {
  const theme = useTheme()
  const isDesktop = useMediaQuery(theme.breakpoints.up('md'))
  const [mobileOpen, setMobileOpen] = useState(false)
  const [langAnchor, setLangAnchor] = useState<HTMLElement | null>(null)
  const rtl = theme.direction === 'rtl'
  const [menuWidth, setMenuWidth] = useState<number>(readMenuWidth)
  const [resizing, setResizing] = useState(false)

  /** Сплиттер меню: перетаскивание правого края (мышь/касание), ширина запоминается. */
  const startMenuResize = (startX: number, touch: boolean) => {
    const startW = menuWidth
    let w = startW
    const move = (x: number) => {
      // RTL (иврит): меню справа — край тянут влево, чтобы расширить
      w = Math.min(MENU_MAX, Math.max(MENU_MIN, startW + (rtl ? startX - x : x - startX)))
      setMenuWidth(w)
    }
    const onMouseMove = (e: MouseEvent) => move(e.clientX)
    const onTouchMove = (e: TouchEvent) => {
      move(e.touches[0].clientX)
      e.preventDefault()
    }
    const stop = () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', stop)
      document.removeEventListener('touchmove', onTouchMove)
      document.removeEventListener('touchend', stop)
      document.removeEventListener('touchcancel', stop)
      document.body.style.userSelect = ''
      setResizing(false)
      try {
        localStorage.setItem(MENU_WIDTH_KEY, String(Math.round(w)))
      } catch {
        /* ignore */
      }
    }
    document.body.style.userSelect = 'none'
    setResizing(true)
    if (touch) {
      document.addEventListener('touchmove', onTouchMove, { passive: false })
      document.addEventListener('touchend', stop)
      document.addEventListener('touchcancel', stop)
    } else {
      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', stop)
    }
  }
  const [desktopOpen, setDesktopOpen] = useState<boolean>(() => {
    try {
      return localStorage.getItem(DRAWER_KEY) !== '0'
    } catch {
      return true
    }
  })
  const toggleDesktop = () => {
    setDesktopOpen((v) => {
      try {
        localStorage.setItem(DRAWER_KEY, v ? '0' : '1')
      } catch {
        /* ignore */
      }
      return !v
    })
  }
  const { upr, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()
  const currentPage = location.pathname.split('/').filter(Boolean)[0] ?? ''

  // Раскрытые группы меню запоминаются (localStorage); группа текущей страницы всегда раскрыта.
  const [open, setOpenState] = useState<Record<string, boolean>>(() => {
    let saved: Record<string, boolean> = {}
    try {
      saved = JSON.parse(localStorage.getItem(MENU_OPEN_KEY) ?? '{}') as Record<string, boolean>
    } catch {
      /* ignore */
    }
    const init: Record<string, boolean> = {}
    for (const g of MENU) init[g.label] = Boolean(saved[g.label]) || g.items.some((i) => i.path === currentPage)
    return init
  })
  const setOpen = (update: (o: Record<string, boolean>) => Record<string, boolean>) => {
    setOpenState((o) => {
      const next = update(o)
      try {
        localStorage.setItem(MENU_OPEN_KEY, JSON.stringify(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }
  /** Свернуть / развернуть все группы меню. */
  const setAllOpen = (value: boolean) => setOpen(() => Object.fromEntries(MENU.map((g) => [g.label, value])))

  const groups = visibleGroups(Boolean(upr?.admin))

  const drawer = (
    // меню прокручивается само; на десктопе справа от него — колонка сплиттера (6px), не поверх меню
    <Box sx={{ width: isDesktop ? menuWidth - 6 : DRAWER_WIDTH, height: '100%', overflowY: 'auto', overflowX: 'hidden' }} role="navigation">
      {/* место под верхней панелью (AppBar перекрывает начало меню) */}
      <Toolbar variant="dense" />
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', px: 1, py: 0.25 }}>
        <Tooltip title={t('Свернуть всё меню')}>
          <IconButton size="small" onClick={() => setAllOpen(false)} aria-label={t('Свернуть всё меню')}>
            <UnfoldLessIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title={t('Развернуть всё меню')}>
          <IconButton size="small" onClick={() => setAllOpen(true)} aria-label={t('Развернуть всё меню')}>
            <UnfoldMoreIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      <Divider />
      <List dense>
        {groups.map((g) => {
          const single = g.items.length === 1
          if (single) {
            const it = g.items[0]
            return (
              <ListItemButton
                key={g.label}
                component={RouterLink}
                to={`/${it.path}/`}
                selected={currentPage === it.path}
                onClick={() => setMobileOpen(false)}
              >
                <ListItemText primary={<>{t(g.label)}{(g.adminOnly || it.adminOnly) && <AdmMark />}</>} />
              </ListItemButton>
            )
          }
          return (
            <Box key={g.label}>
              <ListItemButton onClick={() => setOpen((o) => ({ ...o, [g.label]: !o[g.label] }))}>
                <ListItemText primary={<>{t(g.label)}{g.adminOnly && <AdmMark />}</>} slotProps={{ primary: { sx: { fontWeight: 600 } } }} />
                {open[g.label] ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
              </ListItemButton>
              <Collapse in={open[g.label]} timeout="auto" unmountOnExit>
                <List dense disablePadding>
                  {g.items.map((it) => (
                    <ListItemButton
                      key={it.path}
                      sx={{ pl: 4 }}
                      component={RouterLink}
                      to={`/${it.path}/`}
                      selected={currentPage === it.path}
                      onClick={() => setMobileOpen(false)}
                    >
                      <ListItemText primary={<>{t(it.label)}{(g.adminOnly || it.adminOnly) && <AdmMark />}</>} />
                    </ListItemButton>
                  ))}
                </List>
              </Collapse>
            </Box>
          )
        })}
      </List>
    </Box>
  )

  return (
    // Окно не прокручивается: высота — ровно экран, прокрутка — внутри таблиц и панелей страниц
    // (см. components/layout.ts). overflow: auto у области контента — страховка для очень
    // маленьких окон, где не помещаются даже фильтры.
    <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }} color="default" elevation={1}>
        <Toolbar variant="dense">
          <Tooltip title={isDesktop ? (desktopOpen ? t('Свернуть меню') : t('Развернуть меню')) : t('Меню')}>
            <IconButton edge="start" onClick={() => (isDesktop ? toggleDesktop() : setMobileOpen(true))} sx={{ mr: 1 }} aria-label={t('Меню')}>
              <MenuIcon />
            </IconButton>
          </Tooltip>
          <Typography variant="subtitle1" noWrap sx={{ flexGrow: 1, fontWeight: 600 }}>
            {title}
          </Typography>
          <Tooltip title={upr?.version ?? ''}>
            <Typography variant="body2" sx={{ mr: 2, opacity: 0.8 }} noWrap>
              {upr?.user_name}
            </Typography>
          </Tooltip>
          <Tooltip title={t('Выбор языка интерфейса')}>
            <Button
              size="small"
              color="inherit"
              onClick={(e) => setLangAnchor(e.currentTarget)}
              sx={{ minWidth: 40, fontWeight: 700, mr: 0.5 }}
              aria-label={t('Язык')}
            >
              {lang.toUpperCase()}
            </Button>
          </Tooltip>
          <Menu anchorEl={langAnchor} open={Boolean(langAnchor)} onClose={() => setLangAnchor(null)}>
            {LANGS.map((l) => (
              <MenuItem
                key={l.key}
                selected={l.key === lang}
                onClick={() => {
                  setLangAnchor(null)
                  if (l.key !== lang) setLang(l.key)
                }}
              >
                {l.key.toUpperCase()} - {l.name}
              </MenuItem>
            ))}
          </Menu>
          <Tooltip title={t('Переключить тему')}>
            <IconButton onClick={onToggleTheme} aria-label={t('Тема оформления')}>
              {themeName === 'black' ? <LightModeIcon /> : <DarkModeIcon />}
            </IconButton>
          </Tooltip>
          <Tooltip title={t('Выйти')}>
            <IconButton
              onClick={() => {
                logout()
                navigate('/login')
              }}
              aria-label={t('Выйти')}
            >
              <LogoutIcon />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      {isDesktop ? (
        <Drawer
          variant="persistent"
          open={desktopOpen}
          sx={{
            width: desktopOpen ? menuWidth : 0,
            flexShrink: 0,
            // при перетаскивании сплиттера — без анимации, иначе край отстаёт от мыши
            transition: resizing ? 'none' : (t) => t.transitions.create('width', { duration: t.transitions.duration.shorter }),
            '& .MuiDrawer-paper': { width: menuWidth, overflow: 'hidden', flexDirection: 'row' },
          }}
        >
          {drawer}
          <Box
            role="separator"
            aria-orientation="vertical"
            title={t('Перетащите, чтобы изменить размер; двойной щелчок — по умолчанию')}
            onMouseDown={(e) => {
              e.preventDefault()
              startMenuResize(e.clientX, false)
            }}
            onTouchStart={(e) => startMenuResize(e.touches[0].clientX, true)}
            onDoubleClick={() => {
              setMenuWidth(DRAWER_WIDTH)
              try {
                localStorage.removeItem(MENU_WIDTH_KEY)
              } catch {
                /* ignore */
              }
            }}
            sx={{
              position: 'relative',
              flex: '0 0 6px',
              height: '100%',
              cursor: 'col-resize',
              touchAction: 'none',
              '&::after': {
                content: '""',
                position: 'absolute',
                top: 0,
                bottom: 0,
                ...(rtl ? { left: '2px' } : { right: '2px' }),
                width: '2px',
                borderRadius: '1px',
                background: resizing ? (theme.palette.mode === 'dark' ? '#6b7280' : '#9aa0ad') : 'transparent',
              },
              '&:hover::after': { background: theme.palette.mode === 'dark' ? '#6b7280' : '#9aa0ad' },
            }}
          />
        </Drawer>
      ) : (
        <Drawer variant="temporary" open={mobileOpen} onClose={() => setMobileOpen(false)}>
          {drawer}
        </Drawer>
      )}

      <Box component="main" sx={{ flexGrow: 1, p: 2, minWidth: 0, height: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Toolbar variant="dense" sx={{ flexShrink: 0 }} />
        <Box sx={{ flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
          {children}
        </Box>
      </Box>
    </Box>
  )
}
