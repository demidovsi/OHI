// Общий компонент обоих сайтов (shared_web/frontend).
import { useEffect, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import { useTheme } from '@mui/material/styles'
import Typography from '@mui/material/Typography'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import type { FormFields, Par } from '@app/api'
import { useT } from '@app/i18n'
import DateField from '@shared-web/components/DateField'

// Аналог include/dates.html: «Дата информации» с кнопками влево/вправо/Сегодня
// и чекбоксом «Обновлять» (автообновление). Имена полей — left, right,
// current_day, dt_start, st_date, do_update — как в старом шаблоне.
interface Props {
  par: Par
  onSubmit: (fields: FormFields) => void
  /** Поля формы, которые надо слать вместе с любым действием. */
  base: FormFields
  /** Сколько секунд осталось до автообновления (для подсказки галочки «Обновлять»). */
  refreshIn?: number | null
}

/** Чекбокс do_update — для текущих суток на любой странице (автообновление перечитывает открытую страницу). */
export function showDoUpdate(par: Par): boolean {
  return Boolean(par.is_today)
}

/**
 * Автообновление формы раз в periodMs при включённом par.do_update (paused — пауза, например
 * пока открыт диалог). Возвращает, сколько секунд осталось до обновления (null — выключено).
 */
export function useAutoRefresh(par: Par | null, refresh: () => void, paused = false, periodMs = 30 * 1000) {
  const [left, setLeft] = useState<number | null>(null)
  const refreshRef = useRef(refresh)
  useEffect(() => {
    refreshRef.current = refresh
  })
  useEffect(() => {
    if (!par?.do_update || !showDoUpdate(par) || paused) {
      setLeft(null)
      return
    }
    const due = Date.now() + periodMs
    const tick = () => setLeft(Math.max(0, Math.ceil((due - Date.now()) / 1000)))
    tick()
    const iv = setInterval(tick, 1000)
    const to = setTimeout(() => refreshRef.current(), periodMs)
    return () => {
      clearInterval(iv)
      clearTimeout(to)
    }
  }, [par, paused, periodMs])
  return left
}

export default function DayNavigator({ par, onSubmit, base, refreshIn }: Props) {
  // RTL (иврит, kns-web): «назад» — стрелка вправо (в начале строки справа), «вперёд» — влево
  const rtl = useTheme().direction === 'rtl'
  const PrevIcon = rtl ? ChevronRightIcon : ChevronLeftIcon
  const NextIcon = rtl ? ChevronLeftIcon : ChevronRightIcon
  const t = useT()
  const fields = (extra: FormFields): FormFields => ({ ...base, ...extra })

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
      <IconButton size="small" title={t('Предыдущие сутки')} onClick={() => onSubmit(fields({ left: -1 }))}>
        <PrevIcon />
      </IconButton>
      <Typography variant="body2" color="text.secondary">
        {t('Дата информации:')}
      </Typography>
      <DateField
        value={par.st_date}
        required
        onCommit={(v) => onSubmit(fields({ dt_start: v, st_date: v }))}
        width={160}
      />
      <IconButton size="small" title={t('Следующие сутки')} onClick={() => onSubmit(fields({ right: 1 }))}>
        <NextIcon />
      </IconButton>
      {!par.is_today && (
        <Button size="small" onClick={() => onSubmit(fields({ current_day: 'current_day' }))}>
          {t('Сегодня')}
        </Button>
      )}
      {showDoUpdate(par) && (
        // подсказка MUI (а не title браузера): перерисовывается, пока видна, — секунды идут вживую
        <Tooltip
          title={
            par.do_update
              ? refreshIn != null
                ? t('Автообновление через {n} с', { n: refreshIn })
                : t('Режим автоматического обновления с заданным периодом')
              : t('Режим автоматического обновления ОТКЛЮЧЕН')
          }
        >
        <FormControlLabel
          sx={{ ml: 1 }}
          control={
            <Checkbox
              size="small"
              checked={Boolean(par.do_update)}
              onChange={(e) => onSubmit(fields({ do_update: e.target.checked ? 'Обновлять' : undefined }))}
            />
          }
          label={<Typography variant="body2">{t('Обновлять')}</Typography>}
        />
        </Tooltip>
      )}
    </Box>
  )
}
