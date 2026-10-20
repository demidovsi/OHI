// Раскладка страниц по высоте окна браузера (правило оформления, как в проекте BTC-5m):
// сама форма не прокручивается — все поля с данными кончаются по высоте экрана,
// прокручиваются только таблицы и панели с данными внутри формы.
//
// Цепочка: AppShell (100vh, overflow hidden) → область контента (flex-колонка) →
// корень страницы PAGE_SX → прокручиваемая часть FILL_SX (или ROW_SX → колонки COLUMN_SX).
// Элементы, не помеченные FILL_SX (фильтры, тулбары, пагинация), сохраняют свою высоту.

/** Корень страницы: занимает всю высоту области контента, дети — сверху вниз. */
export const PAGE_SX = { flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column' } as const

/** Прокручиваемая часть (TableContainer, Paper с текстом): забирает остаток высоты. */
export const FILL_SX = { flex: '1 1 0', minHeight: 120, overflow: 'auto' } as const

/** Ряд панелей (бок о бок), забирающий остаток высоты; на узком экране панели идут столбиком. */
export const ROW_SX = {
  flex: '1 1 0',
  minHeight: 0,
  display: 'flex',
  flexDirection: { xs: 'column', md: 'row' },
  gap: 1.5,
} as const

/** Колонка внутри ROW_SX / вложенная flex-колонка, забирающая остаток высоты. */
export const COLUMN_SX = { flex: '1 1 0', minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' } as const

/** Панель с многострочным полем ввода, забирающая всю высоту своей колонки (SplitPane). */
export const FILL_TEXT_PANEL = { flex: '1 1 0', minHeight: 0, p: 1.5, display: 'flex', flexDirection: 'column' } as const

/** Многострочный TextField на всю оставшуюся высоту панели; текст прокручивается внутри поля. */
export const FILL_TEXT_FIELD = {
  flex: '1 1 0',
  minHeight: 0,
  '& .MuiInputBase-root': { height: '100%', alignItems: 'flex-start' },
  '& textarea': { height: '100% !important', overflow: 'auto !important' },
} as const

/**
 * Кнопка-статус законопроекта в таблицах: текст переносится в 2–3 строки, поэтому колонка
 * статуса не растягивается по самому длинному статусу.
 */
export const STATUS_CHIP_SX = {
  height: 'auto',
  maxWidth: 150,
  py: 0.25,
  '& .MuiChip-label': { whiteSpace: 'normal', textAlign: 'center', lineHeight: 1.2, display: 'block' },
} as const
