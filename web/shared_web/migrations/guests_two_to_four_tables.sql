-- Миграция учёта посетителей схемы сайта: с двух таблиц (nsi_guests, his_guests_page; вход — запись «Login (<пользователь>)» в
-- истории гостя) на четыре (добавляются nsi_emails и his_emails_hist; гость — пара «IP + пользователь»).
--
-- Порядок:
--   1. В modeler_web выбрать схему сайта и на форме «Классы» нажать кнопку Guests: в метаданные записываются класс emails и
--      параметр guests.email, затем создаются реальные таблицы nsi_emails, his_emails_hist и колонка nsi_guests.email
--      (существующие guests, country, city, page не пересоздаются).
--   2. Выполнить этот скрипт, предварительно указав схему в первой строке блока DECLARE (s text := '...').
--   3. Развернуть новую версию кода сайта (shared_web/visits.py пишет входы в nsi_emails и his_emails_hist).
-- Скрипт можно запускать повторно: уже перенесённые пользователи и входы пропускаются. Записи «Login (...)» в his_guests_page
-- остаются (новая форма «Гости сайта» их не читает); удалить можно последним оператором (закомментирован).

DO $migration$
DECLARE
    s text := 'sozd';   -- схема сайта
BEGIN
    -- 1. пользователи: по одной записи на имя из «Login (<имя>)»: первый и последний вход, число входов
    EXECUTE format($q$
        -- id в nsi_* не автоинкрементный (его назначает функция записи MDM как MAX(id)+1): новые id — следом за существующими
        INSERT INTO %1$I.nsi_emails (id, sh_name, first_date, last_date, "count")
        SELECT (SELECT COALESCE(MAX(id), 0) FROM %1$I.nsi_emails) + ROW_NUMBER() OVER (ORDER BY n.username),
               n.username, n.first_date, n.last_date, n.logins
        FROM (SELECT u.username, MIN(u.dt) AS first_date, MAX(u.dt) AS last_date, COUNT(*) AS logins
              FROM (SELECT SUBSTRING(h.value FROM 'Login \((.+)\)') AS username, h.dt
                    FROM %1$I.his_guests_page h WHERE h.value LIKE 'Login (%%') u
              WHERE u.username IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM %1$I.nsi_emails e WHERE e.sh_name = u.username)
              GROUP BY u.username) n
    $q$, s);

    -- 2. гость связывается с пользователем, который входил с него последним (у гостей, где пользователь ещё не задан)
    EXECUTE format($q$
        UPDATE %1$I.nsi_guests g SET email = e.id
        FROM (SELECT DISTINCT ON (h.guests_id) h.guests_id, SUBSTRING(h.value FROM 'Login \((.+)\)') AS username
              FROM %1$I.his_guests_page h WHERE h.value LIKE 'Login (%%'
              ORDER BY h.guests_id, h.dt DESC) l
        JOIN %1$I.nsi_emails e ON e.sh_name = l.username
        WHERE g.id = l.guests_id AND g.email IS NULL
    $q$, s);

    -- 3. история пользователя: каждый вход — строка «LOGIN; IP=<ip>; country=<страна>; city=<город>» (формат, который читает форма)
    EXECUTE format($q$
        INSERT INTO %1$I.his_emails_hist (emails_id, dt, value)
        SELECT e.id, h.dt, 'LOGIN; IP=' || g.sh_name || '; country=' || COALESCE(g.country, '') || '; city=' || COALESCE(g.city, '')
        FROM %1$I.his_guests_page h
        JOIN %1$I.nsi_guests g ON g.id = h.guests_id
        JOIN %1$I.nsi_emails e ON e.sh_name = SUBSTRING(h.value FROM 'Login \((.+)\)')
        WHERE h.value LIKE 'Login (%%'
        ON CONFLICT DO NOTHING
    $q$, s);
END
$migration$;

-- Необязательно, после проверки формы «Гости сайта» (замените схему):
-- DELETE FROM sozd.his_guests_page WHERE value LIKE 'Login (%';
