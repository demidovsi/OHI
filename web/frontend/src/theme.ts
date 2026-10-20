import { createTheme } from '@mui/material/styles'
import type { Colors } from './api'

export type ThemeName = 'white' | 'black'

// Соответствие старой палитры colors.py → MUI. Семантика цветов в старом UI:
// blue — ссылки/заголовки, green — вторичные действия, red — акценты/предупреждения,
// yellow — язык, select_background — выделенная строка.
/** direction 'rtl' — иврит: зеркальная раскладка (вместе с RTL-кэшем Emotion в App.tsx). */
export function buildTheme(name: ThemeName, _colors?: Colors, direction: 'ltr' | 'rtl' = 'ltr') {
  const dark = name === 'black'
  return createTheme({
    direction,
    palette: {
      mode: dark ? 'dark' : 'light',
      primary: { main: dark ? '#90caf9' : '#1565c0' },
      secondary: { main: dark ? '#81c784' : '#2e7d32' },
      error: { main: dark ? '#f5deb3' : '#d32f2f' },
      background: dark
        ? { default: '#121212', paper: '#1e1e1e' }
        : { default: '#fafafa', paper: '#ffffff' },
      // Не берём цвета из серверной палитры (colors.py): там именованные CSS-цвета
      // ('DarkSlateGray'), которые MUI alpha() не парсит → белый экран.
      action: {
        selected: dark ? 'rgba(47, 79, 79, 0.6)' : 'rgba(211, 211, 211, 0.6)',
      },
    },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily: 'Roboto, "Helvetica Neue", Arial, sans-serif',
      fontSize: 13,
    },
    components: {
      // Полосы прокрутки всех областей (таблицы, панели, списки, диалоги) — единый стиль,
      // как в проекте BTC-5m (docs/WEB.md «Полосы прокрутки»): толщина 10px, полный набор
      // правил (дорожка, ползунок, наведение, угол). В светлой теме дорожка и ползунок
      // поменяны местами относительно тёмной: светлая дорожка, голубой ползунок.
      MuiCssBaseline: {
        styleOverrides: {
          // Встроенные элементы браузера (значок календаря в type=date/month, часы в type=time,
          // выпадающие списки) — в цветах темы: без этого в тёмной теме значки тёмные на тёмном.
          ':root': { colorScheme: dark ? 'dark' : 'light' },
          '*': {
            // Firefox: толщину задать нельзя, только цвета (ползунок, дорожка)
            scrollbarColor: dark ? '#555a66 #23262e' : '#8fbbe6 #d1d5db',
          },
          '*::-webkit-scrollbar': { width: 10, height: 10 },
          '*::-webkit-scrollbar-track': { background: dark ? '#23262e' : '#d1d5db' },
          '*::-webkit-scrollbar-thumb': { background: dark ? '#555a66' : '#8fbbe6', borderRadius: 3 },
          '*::-webkit-scrollbar-thumb:hover': { background: dark ? '#7a8090' : '#6fa3d8' },
          '*::-webkit-scrollbar-corner': { background: dark ? '#23262e' : '#d1d5db' },
        },
      },
      MuiTableCell: {
        styleOverrides: { root: { padding: '6px 10px' } },
      },
      MuiButton: {
        defaultProps: { size: 'small' },
      },
      MuiTextField: {
        defaultProps: { size: 'small' },
      },
      // Лейблы всегда «приподняты»: у type=date/number/month браузер рисует
      // плейсхолдер сам, и неприподнятый лейбл накладывается на него.
      MuiInputLabel: {
        defaultProps: { shrink: true },
      },
      MuiOutlinedInput: {
        defaultProps: { notched: true },
        styleOverrides: {
          // Автозаполненное поле заливается до самой рамки (браузер — background, MUI в тёмной
          // теме — синий box-shadow #266798), и приподнятый лейбл на рамке наполовину ложится на
          // заливку. Убираем box-shadow MUI, фон браузера «замораживаем» долгим transition.
          input: {
            '&:-webkit-autofill': {
              WebkitBoxShadow: 'none',
              boxShadow: 'none',
              transition: 'background-color 600000s 0s, color 600000s 0s',
              WebkitTextFillColor: dark ? '#fff' : 'rgba(0, 0, 0, 0.87)',
              caretColor: 'inherit',
            },
          },
        },
      },
      MuiFormControl: {
        defaultProps: { size: 'small' },
      },
    },
  })
}
