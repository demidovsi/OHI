import type { Theme } from '@mui/material/styles'

/**
 * Подсветка выбранной строки бокового меню — как в веб-интерфейсе GEO (.menu-item.active):
 * скруглённая (6px) строка с отступом от краёв, бирюзовая заливка (--row-selected) и полоса акцента 3px
 * у начала строки (inset box-shadow повторяет скругление). Цвета те же, что в GEO, а не primary сайта.
 * Для ListItemButton с selected; в RTL (иврит) полоса справа.
 */
const ACCENT = { dark: '#22b8cf', light: '#0e8fa3' }
const SELECTED = { dark: 'rgba(34, 184, 207, 0.24)', light: 'rgba(14, 143, 163, 0.18)' }

export const menuSelectedSx = {
  borderRadius: '6px',
  mx: 1,
  width: 'auto',
  '&.Mui-selected, &.Mui-selected:hover': {
    bgcolor: (th: Theme) => SELECTED[th.palette.mode],
    color: 'text.primary',
    boxShadow: (th: Theme) => `inset ${th.direction === 'rtl' ? '-' : ''}3px 0 0 ${ACCENT[th.palette.mode]}`,
  },
}
