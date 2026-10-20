// HE dictionary: key = source Russian string as used in code (t('...')).
// Covers the shell, menu, login and shared controls; page texts without a Hebrew
// entry fall back to Russian, as in the legacy UI (its templates are Russian).
// Page groups may add `he.<group>.ts` files exporting `HE_<GROUP>`; they are merged automatically.

const HE_COMMON: Record<string, string> = {
  'Меню': 'תפריט',
  'Свернуть меню': 'כווץ תפריט',
  'Развернуть меню': 'הרחב תפריט',
  'Переключить тему': 'החלף ערכת נושא',
  'Тема оформления': 'ערכת נושא',
  'Выйти': 'יציאה',
  'Язык': 'שפה',
  'Выбор языка интерфейса': 'שפת הממשק',
  'Аналитика': 'ניתוח',
  'Сайт': 'אתר',
  'Гости сайта': 'מבקרי האתר',
  'Log': 'יומן',
  'Параметры сервисов': 'פרמטרי שירותים',
  'Пользователь': 'משתמש',
  'Пароль': 'סיסמה',
  'Введите имя пользователя': 'הזן שם משתמש',
  'Введите пароль': 'הזן סיסמה',
  'Войти': 'כניסה',
  'Вход…': 'נכנס…',
  'Неверное имя пользователя или пароль': 'שם משתמש או סיסמה שגויים',
  'Ошибка входа': 'שגיאת כניסה',
  'Ошибка интерфейса': 'שגיאת ממשק',
  'Перезагрузить': 'טען מחדש',
  'Нет данных': 'אין נתונים',
  'Строк': 'שורות',
  'Поиск': 'חיפוש',
  'Сортировка': 'מיון',
  'По возрастанию': 'בסדר עולה',
  'По убыванию': 'בסדר יורד',
  'Обновить таблицу': 'רענן טבלה',
  'Вывод с {first} по {last} ': 'מוצגות {first} עד {last} ',
  '(Всего строк = {count})': '(סה"כ שורות = {count})',
  'Назад': 'חזרה',
  'Отмена': 'ביטול',
  'Закрыть': 'סגור',
  'Сохранить': 'שמור',
  'Удалить': 'מחק',
  'Да': 'כן',
  'Нет': 'לא',
  'Скачать': 'הורדה',
  'Предыдущие сутки': 'היום הקודם',
  'Следующие сутки': 'היום הבא',
  'Дата информации:': 'תאריך:',
  'Сегодня': 'היום',
  'Обновлять': 'רענון אוטומטי',
}

import { HE_SHARED_WEB } from '@shared-web/locales' // общие формы сайтов (shared_web/frontend)

const groups = import.meta.glob<Record<string, Record<string, string>>>('./he.*.ts', { eager: true })

export const HE: Record<string, string> = Object.assign(
  {},
  HE_SHARED_WEB,
  HE_COMMON,
  ...Object.values(groups).flatMap((m) => Object.values(m)),
)
