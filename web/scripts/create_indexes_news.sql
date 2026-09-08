-- ============================================================================
-- Индексы для оптимизации чтения данных, используемого в news.py
-- (схема ohi: nsi_rss_history, nsi_rss_list, nsi_rss_themes,
--  rel_rss_themes_rss_history_rss, view v_nsi_rss_history / get_list_theme_for_history)
--
-- CREATE INDEX CONCURRENTLY нельзя выполнять внутри транзакционного блока
-- (BEGIN...COMMIT) и внутри мульти-стейтмент execute, который сам оборачивает
-- скрипт в транзакцию. Прогонять этот файл нужно через psql построчно/файлом,
-- а не через REST-эндпоинт v2/execute приложения.
-- ============================================================================

-- 1. Фильтр по дате (news.get_where, ветка 'one_day'):
--    public_date is not NULL and public_date>=... and public_date<...
--    or at_date_time>=... and at_date_time<...
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_public_date
    ON ohi.nsi_rss_history (public_date)
    WHERE public_date IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_at_date_time
    ON ohi.nsi_rss_history (at_date_time);

-- 2. Фильтр по источнику (news.get_where: rss={id}), обычно вместе с датой
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_rss_public_date
    ON ohi.nsi_rss_history (rss, public_date);

-- 3. Фильтр по теме: a.id in (select rss_history_id from rel_rss_themes_rss_history_rss
--    where rss_themes_id={theme}), а также join внутри view get_list_theme_for_history
--    (a.rss_themes_id=b.id and a.rss_history_id=c.id)
--    Индекс (rss_themes_id, rss_history_id) НЕ создаём - в таблице уже есть
--    rel_rss_themes_rss_history_rss_idx UNIQUE (rss_themes_id, rss_history_id),
--    покрывающий этот фильтр (index-only scan); отдельный обычный индекс
--    с тем же порядком колонок был бы чистым дублем.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rel_history_theme
    ON ohi.rel_rss_themes_rss_history_rss (rss_history_id, rss_themes_id);

-- 4. Текстовый поиск (common.get_where -> ilike '%term%') по колонкам
--    title_ru/en/he, description_ru/en/he (nsi_rss_history) и sh_name (nsi_rss_list).
--    Обычный B-tree бесполезен при ведущем '%', нужны триграммные индексы.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_title_ru_trgm
    ON ohi.nsi_rss_history USING gin (title_ru gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_title_en_trgm
    ON ohi.nsi_rss_history USING gin (title_en gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_title_he_trgm
    ON ohi.nsi_rss_history USING gin (title_he gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_description_ru_trgm
    ON ohi.nsi_rss_history USING gin (description_ru gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_description_en_trgm
    ON ohi.nsi_rss_history USING gin (description_en gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_description_he_trgm
    ON ohi.nsi_rss_history USING gin (description_he gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_list_sh_name_trgm
    ON ohi.nsi_rss_list USING gin (sh_name gin_trgm_ops);

-- 5. Сортировка по author/file (news.array_sort), когда используется отдельно
--    от фильтра по дате/источнику
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_author
    ON ohi.nsi_rss_history (author);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nsi_rss_history_file
    ON ohi.nsi_rss_history (file);

-- ============================================================================
-- Примечание (не индекс): в определении view ohi.get_list_theme_for_history
-- есть избыточное условие "a.rss_history_id IN (SELECT nrh.id FROM nsi_rss_history nrh)" -
-- оно всегда истинно, т.к. rss_history_id уже соединён с c.id из той же таблицы,
-- и только добавляет лишнюю работу планировщику. Индексы из п.3 его не лечат -
-- условие стоит убрать из тела view отдельным изменением.
-- ============================================================================
