-- ============================================================================
-- Исправление ohi.get_list_theme_for_history: убрано избыточное условие
-- "a.rss_history_id IN (SELECT nrh.id FROM ohi.nsi_rss_history nrh)" - оно
-- всегда истинно, т.к. rss_history_id уже соединён с c.id из той же таблицы
-- (a.rss_history_id = c.id), и только добавляло лишнюю работу планировщику.
-- Результирующий набор строк не меняется.
-- ============================================================================

CREATE OR REPLACE VIEW ohi.get_list_theme_for_history
AS WITH reg AS (
         SELECT c.id,
            b.sh_name,
            b.id AS theme_id
           FROM ohi.rel_rss_themes_rss_history_rss a,
            ohi.nsi_rss_themes b,
            ohi.nsi_rss_history c
          WHERE a.rss_themes_id = b.id AND a.rss_history_id = c.id
        )
 SELECT reg.id,
    reg.sh_name,
    reg.theme_id
   FROM reg;
