// Структура меню сайта.
// path — роут SPA (/<path>/) и имя формы API (/api/v2/form/<path>/).

export interface MenuItem {
  label: string
  path: string
  /** Пункт только для администратора (у группы — MenuGroup.adminOnly). */
  adminOnly?: boolean
}

export interface MenuGroup {
  label: string
  adminOnly?: boolean
  items: MenuItem[]
}

export const MENU: MenuGroup[] = [
  {
    label: 'Новости',
    items: [
      { label: 'Лента новостей', path: 'news_board' },
      { label: 'Аналитика', path: 'analyses' },
    ],
  },
  {
    label: 'Сайт',
    items: [
      { label: 'Новостные ленты', path: 'rss' },
      { label: 'Поисковые образы', path: 'search_words' },
      { label: 'Лог чата', path: 'chat_logs' },
      { label: 'Log', path: 'logs', adminOnly: true },
      { label: 'Гости сайта', path: 'guests', adminOnly: true },
      { label: 'Параметры сервисов', path: 'functions', adminOnly: true },
    ],
  },
]

/** Стартовая страница после логина и для «/». */
export const HOME_PAGE = 'news_board'

/** Группы меню, видимые пользователю (как в AppShell): пункты adminOnly — только администратору. */
export function visibleGroups(admin: boolean): MenuGroup[] {
  return MENU.filter((g) => (g.adminOnly ? admin : true))
    .map((g) => ({ ...g, items: g.items.filter((i) => admin || !i.adminOnly) }))
    .filter((g) => g.items.length > 0)
}

/**
 * Заголовок страницы в верхней строке — путь по меню: «Группа / Пункт» («Сайт / Log»);
 * для группы из одного пункта — её название. Страница вне меню — её имя.
 */
export function pageTitle(path: string, t: (s: string) => string, admin = false): string {
  for (const g of visibleGroups(admin)) {
    const it = g.items.find((i) => i.path === path)
    if (it) return g.items.length === 1 ? t(g.label) : `${t(g.label)} / ${t(it.label)}`
  }
  return t(path)
}
