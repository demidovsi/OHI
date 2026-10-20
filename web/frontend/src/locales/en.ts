// EN dictionary: key = source Russian string as used in code (t('...')).
// Page groups keep their own file `en.<group>.ts` exporting `EN_<GROUP>`; every
// such file is merged automatically (import.meta.glob), so pages never edit this file.

const EN_COMMON: Record<string, string> = {
  // --- shell / menu ---
  'Меню': 'Menu',
  'Свернуть меню': 'Collapse menu',
  'Развернуть меню': 'Expand menu',
  'Переключить тему': 'Toggle theme',
  'Тема оформления': 'Theme',
  'Выйти': 'Sign out',
  'Язык': 'Language',
  'Выбор языка интерфейса': 'Interface language',
  'Аналитика': 'Analytics',
  'Сайт': 'Site',
  'Гости сайта': 'Site guests',
  'Log': 'Log',
  'Параметры сервисов': 'Service parameters',

  // --- login ---
  'Пользователь': 'User',
  'Пароль': 'Password',
  'Введите имя пользователя': 'Enter user name',
  'Введите пароль': 'Enter password',
  'Войти': 'Sign in',
  'Вход…': 'Signing in…',
  'Неверное имя пользователя или пароль': 'Wrong user name or password',
  'Ошибка входа': 'Sign-in error',

  // --- common ---
  'Ошибка интерфейса': 'Interface error',
  'Перезагрузить': 'Reload',
  'Нет данных': 'No data',
  'Строк': 'Rows',
  'Поиск': 'Search',
  'Сортировка': 'Sort by',
  'По возрастанию': 'Ascending',
  'По убыванию': 'Descending',
  'Обновить таблицу': 'Refresh table',
  'Фильтрация выводимых строк таблицы': 'Filter table rows',
  'Вывод с {first} по {last} ': 'Showing {first} to {last} ',
  '(Всего строк = {count})': '(Total rows = {count})',
  'Назад': 'Back',
  'Отмена': 'Cancel',
  'Закрыть': 'Close',
  'Сохранить': 'Save',
  'Удалить': 'Delete',
  'Да': 'Yes',
  'Нет': 'No',
  'Скачать': 'Download',
  'Загрузка…': 'Loading…',

  // --- day navigator (include/dates.html) ---
  'Предыдущие сутки': 'Previous day',
  'Следующие сутки': 'Next day',
  'Дата информации:': 'Date:',
  'Сегодня': 'Today',
  'Обновлять': 'Auto-refresh',
  'Режим автоматического обновления с заданным периодом': 'Automatic refresh with the given period',
  'Режим автоматического обновления ОТКЛЮЧЕН': 'Automatic refresh is OFF',

}

import { EN_SHARED_WEB } from '@shared-web/locales' // общие формы сайтов (shared_web/frontend)

const groups = import.meta.glob<Record<string, Record<string, string>>>('./en.*.ts', { eager: true })

export const EN: Record<string, string> = Object.assign(
  {},
  EN_SHARED_WEB,
  EN_COMMON,
  ...Object.values(groups).flatMap((m) => Object.values(m)),
)
