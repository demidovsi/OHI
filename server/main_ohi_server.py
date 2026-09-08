"""
Главный модуль сервера мониторинга СМИ (OHI-server).

Запускает потоки для опроса RSS-лент, парсинга WordPress-сайтов,
мониторинга ТВ-канала 9, kremlin.ru и вспомогательные потоки (чистка логов, перевод).
Периодически проверяет БД на появление новых RSS-источников и создаёт для них потоки.
"""
import os
import sys
import time
import json
import signal

import common
from common import SRC
import config
import rss_search
import rss_translate
import rss_wordnews
import tv9co_il
import kremlin_ru
import word_press_parser
import rss_complete
import clear_logs

common.current_path = os.path.abspath(os.curdir)
version = 'version 3.46 от 8 сентября 2026 г.'
t0 = 0


def log_shutdown(reason):
    """Записывает в лог факт остановки сервиса с указанием причины и времени работы."""
    try:
        duration = common.get_duration(time.time() - t0) if t0 else '—'
        common.write_log_db(
            '🛑Shutdown', SRC,
            f'Остановка сервера LLM: {reason}\n{version}\nВремя работы: {duration}',
            td=time.time() - t0 if t0 else 0)
    except Exception:
        pass  # при аварийном завершении write_log_db может быть недоступен


def _sigterm_handler(signum, _frame):
    """Обработчик сигнала SIGTERM (завершение от ОС / supervisor / Docker)."""
    sig_name = signal.Signals(signum).name
    log_shutdown(f'получен сигнал {sig_name} ({signum})')
    sys.exit(0)


# Регистрация обработчика SIGTERM (SIGINT обрабатывается через KeyboardInterrupt)
signal.signal(signal.SIGTERM, _sigterm_handler)


def load_list_rss():
    """Загружает список активных (не остановленных) RSS-сайтов из БД."""
    url = (f"v2/entity/values?app_code={config.schema_name}"
           f"&object_code=rss_list&column_order=id desc"
           f"&where=(stop is null or not stop)")
    ans, is_ok, status = common.send_rest(url)
    if not is_ok:
        # FIX: было "\load_list_rss" — \l не является escape-последовательностью
        common.write_log_db(
            '❌error', SRC,
            f"load_list_rss\nСервер LLM\nОшибка {ans} для {url}"
            )
        return []
    else:
        return json.loads(ans)


def check_work(threads: list):
    """
    Проверка работоспособности потоков и запись статуса в лог.
    Выводит информацию об активных, ошибочных и остановленных потоках.
    """
    count_work = 0
    parts = []
    error = 0
    for elem in threads:
        if elem is None:
            continue
        # Защита от обращения к пустому rss до первого вызова work()
        # (между start() и завершением work() self.rss может быть {})
        if not elem.rss:
            continue
        if elem.in_work:
            count_work += 1
        if elem.is_error:
            error += 1
        is_stopped = elem.rss.get('stop', False)
        if elem.in_work or elem.is_error or is_stopped:
            st = '❌' if elem.is_error else '✅'
            st = '⛔' + st if is_stopped else st
            st_count = str(elem.global_count) if elem.global_count > 0 and not elem.is_error else ''
            if elem.number > 0:
                st_count = str(elem.number) + '/' + st_count if st_count != '' else str(elem.number)
            st_count = 'er=' + str(elem.status_code) if elem.status_code != 0 else st_count
            st_duration = common.get_duration(time.time() - elem.t0) if not is_stopped else 'stop'
            parts.append(st + st_duration + '; ID=' + str(elem.rss['id']) + ' [' + elem.rss['sh_name'] + '] ' +
                         st_count)
    if common.count_tg_err:
        parts.append('\t❗Ошибок в TG: ' + str(common.count_tg_err))
    st_work = '\n'.join(parts)
    common.write_log_db('info', SRC,f'Сервер LLM\nАктивных потоков: {count_work} из {len(threads)}, ошибок: {error}\n{st_work}',
                        page=count_work, td=time.time() - t0, law_id='tg=' + str(common.count_tg_ok))


if __name__ == '__main__':
    t0 = time.time()
    common.write_log_db(
        '🔥Startup', SRC,
        f'Старт Сервера LLM: сервиса контроля СМИ\nhost RestAPI: {config.URL};\n{version}\nschema: ' + config.schema_name)
    list_threads = []

    # Шаг разнесения первого запуска RSS-потоков: каждый следующий поток
    # ждёт на RSS_JITTER_STEP секунд дольше, чем предыдущий.
    # 40 потоков × 20 сек = 800 сек ≈ 13 мин равномерного spread.
    RSS_JITTER_STEP = 60

    try:
        # Запуск вспомогательных потоков с разнесением по времени.
        # Шаг 60 сек: ClearLogs стартует сразу, TranslateRSS — через 60 сек,
        # CompleteRSS — через 120 сек, чтобы не конкурировать за ресурсы.
        _aux_delay = 0
        for _aux in [
            clear_logs.ClearLogs('ClearLogs', 'ClearLogs', 'period', 'Поток "Чистка LOG"'),
            rss_translate.TranslateRSS('TranslateRSS', 'TranslateRSS', 'period', 'Поток "Трансляция статей новостей"'),
            rss_complete.CompleteRSS('CompleteRSS', 'CompleteRSS', 'period', 'Поток "Добавление полных текстов новостей" загружен'),
        ]:
            _aux.initial_delay = _aux_delay
            _aux.start()
            _aux_delay += 60

        list_rss = load_list_rss()  # Загрузка списка RSS-сайтов из БД
        # FIX: Вместо линейного поиска по list_rss_init (O(n²)) используем set ID-шников (O(1))
        seen_rss_ids = set()
        time_cycle = time.time()

        # Главный цикл: создание потоков для новых RSS и мониторинг существующих
        while True:
            for rss in list_rss:
                if rss['id'] not in seen_rss_ids:
                    # Новый RSS-источник — создаём поток
                    seen_rss_ids.add(rss['id'])
                    elem = None
                    if rss['type_rss'] == 'rss':
                        elem = rss_search.SearchRSS(
                            'SearchRSS', 'SearchRSS', 'period',
                            'Поток "Поиск тем в новостных лентах"', rss['id'])
                    elif rss['type_rss'] == 'tv9co_il':
                        elem = tv9co_il.TV9coIl(
                            'tv9co_il', 'tv9co_il', 'period',
                            'Поток "Поиск тем в новостях 9-го ТВ канала Израиля"', rss['id'])
                    elif rss['type_rss'] == 'worldnews':
                        elem = rss_wordnews.WordNewsRSS(
                            'WorldNews', 'WorldNews', 'period',
                            'Поток "Поиск тем в топ-новостях WorldNews API"', rss['id'])
                    elif rss['type_rss'] == 'kremlin_ru':
                        elem = kremlin_ru.KremlinRu(
                            'kremlin_ru', 'kremlin_ru', 'period',
                            'Поток "Поиск тем в новостях kremlin.ru"', rss['id'])
                    elif rss['type_rss'] == 'WordPress':
                        elem = word_press_parser.WordPressParser(
                            'WordPress', 'SearchRSS', 'period',
                            'Поток "Поиск тем в новостных лентах с WordPress"', rss['id'])
                    if elem:
                        # Разносим первый запуск: каждый новый поток ждёт дольше на RSS_JITTER_STEP.
                        # Для потоков, добавленных после старта (не при инициализации),
                        # initial_delay=0 — они запускаются немедленно.
                        if not list_threads:
                            elem.initial_delay = 0
                        else:
                            elem.initial_delay = len(list_threads) * RSS_JITTER_STEP
                        elem.start()
                        # FIX: append только если elem создан (раньше None попадали в список)
                        list_threads.append(elem)
                    time.sleep(1)  # Минимальная пауза, чтобы не перегружать API при старте

            # Каждые 10 минут — проверка работоспособности потоков
            if time.time() - time_cycle >= 600.0:
                check_work(list_threads)
                # Удаляем завершённые потоки, чтобы они не удерживали память
                list_threads = [t for t in list_threads if t.is_alive()]
                time_cycle = time.time()
            time.sleep(30)  # Пауза между проверками новых сайтов
            list_rss = load_list_rss()  # Перезагрузка списка (могли добавить новые)
            # Синхронизируем seen_rss_ids с актуальным списком БД:
            # убираем ID удалённых источников, чтобы они могли быть пересозданы при возврате.
            # ВАЖНО: синхронизируем только если список непустой — при ошибке API load_list_rss()
            # возвращает [], что обнулило бы seen_rss_ids и породило дублирующие потоки.
            if list_rss:
                seen_rss_ids &= {r['id'] for r in list_rss}

    except KeyboardInterrupt:
        # Ctrl+C или SIGINT
        log_shutdown('прервано пользователем (Ctrl+C)')
    except SystemExit:
        # sys.exit() из signal_handler — уже залогировано
        pass
    except Exception as e:
        # Необработанное исключение в главном цикле
        log_shutdown(f'необработанное исключение: {e}')
        raise
