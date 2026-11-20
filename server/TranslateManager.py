import time
import threading
import queue
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TooManyRequests
import json
import logging
import os

import requests
import deep_translator.google as _dt_google


class _RequestsWithTimeout:
    """requests для deep_translator: у его requests.get нет таймаута, зависший запрос держал замок переводчика
    (общий для всех потоков) бесконечно. Остальное — как в requests."""
    TIMEOUT = 20

    def __getattr__(self, name):
        return getattr(requests, name)

    def get(self, *args, **kwargs):
        kwargs.setdefault('timeout', self.TIMEOUT)
        return requests.get(*args, **kwargs)


_dt_google.requests = _RequestsWithTimeout()


# Иногда Google Translate вместо перевода отдаёт свою типовую HTML-страницу ошибки
# (Error 500/404 !!1 "That's an error... That's all we know."). deep_translator не
# считает это исключением и молча возвращает текст этой страницы как "перевод".
# Проверяем результат на эти маркеры, чтобы не записать его в БД как валидный текст.
_GOOGLE_ERROR_PAGE_MARKERS = (
    "that's an error",
    "that's all we know",
)


def _is_google_error_page(text):
    if not text:
        return False
    low = text.lower().replace('’', "'")  # curly quote → straight quote
    return any(m in low for m in _GOOGLE_ERROR_PAGE_MARKERS)


# Бэкенд перевода (env TRANSLATE_BACKEND):
#   'local' (по умолчанию) — свой LibreTranslate на сервере (server/docker-compose.libretranslate.yml, адрес TRANSLATE_LOCAL_URL):
#       бесплатно, без блокировок;
#   'free' — бесплатный Google Translate через deep_translator (с серверного IP блокируется: 429 / google.com/sorry);
#   'cloud' — официальный Google Cloud Translation API v2 от имени сервисного аккаунта (config.credential; в проекте GCP
#       включить Cloud Translation API, роль «Cloud Translation API User»; платный).
TRANSLATE_BACKEND = os.environ.get('TRANSLATE_BACKEND', 'local').lower()
CLOUD_URL = 'https://translation.googleapis.com/language/translate/v2'
CLOUD_TIMEOUT = 30
LOCAL_URL = os.environ.get('TRANSLATE_LOCAL_URL', 'http://172.17.0.1:5099/translate')  # docker0 хоста: контейнер ohi-server в bridge-сети
LOCAL_TIMEOUT = 120


class CloudTranslateError(Exception):
    """Ошибка Cloud Translation API; retryable — имеет смысл повторить (429, 5xx)."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def _cloud_lang(code):
    return 'he' if code == 'iw' else code  # v2 принимает и iw, и he; he — актуальный код


def _std_lang(code):
    """Единый код языка: иврит — 'he' (в коде встречается и 'iw')."""
    return 'he' if code == 'iw' else code


class TranslationManager:
    """
    Класс для управления переводами текстов из нескольких потоков с обработкой ограничений API.
    Использует блокировку для безопасного доступа к переводчику и экспоненциальную задержку
    при ошибках превышения лимита запросов.
    """

    def __init__(self, max_retries=3, initial_delay=2, cooldown_period=60):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.cooldown_period = cooldown_period
        self.lock = threading.Lock()  # на сам запрос к Google и results
        self._state_lock = threading.Lock()  # на проверку охлаждения (без ожидания под ним)
        self.last_error_time = 0
        self.consecutive_errors = 0
        self.queue = queue.Queue()
        self.results = {}
        self._tls = threading.local()  # причина последнего сбоя перевода и признак низкого приоритета потока
        self._high_active = 0          # сколько обычных (приоритетных) переводов выполняется или ждёт замка
        self._prio_lock = threading.Lock()
        self._setup_logger()

    def _setup_logger(self):
        self.logger = logging.getLogger('TranslationManager')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _cloud_session(self):
        """HTTP-сессия с авторизацией сервисного аккаунта (создаётся один раз, токен обновляется сам)."""
        session = getattr(self, '_session', None)
        if session is None:
            import config
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(config.credential), scopes=['https://www.googleapis.com/auth/cloud-translation'])
            session = self._session = AuthorizedSession(credentials)
        return session

    def _cloud_translate(self, text, target_lang, source_lang=None):
        """Перевод через Cloud Translation API v2 (format=text: без HTML-экранирования результата)."""
        body = {'q': text, 'target': _cloud_lang(target_lang), 'format': 'text'}
        if source_lang:
            body['source'] = _cloud_lang(source_lang)
        resp = self._cloud_session().post(CLOUD_URL, json=body, timeout=CLOUD_TIMEOUT)
        if resp.status_code != 200:
            try:
                msg = resp.json()['error']['message']
            except Exception:
                msg = resp.text[:200]
            raise CloudTranslateError(f'Cloud Translation HTTP {resp.status_code}: {msg}',
                                      retryable=resp.status_code == 429 or resp.status_code >= 500)
        return resp.json()['data']['translations'][0]['translatedText']

    def _local_translate(self, text, target_lang, source_lang=None):
        """Перевод через свой LibreTranslate; язык исходного текста — явный (auto хуже на коротких заголовках)."""
        body = {'q': text, 'source': _std_lang(source_lang) if source_lang else 'auto',
                'target': _std_lang(target_lang), 'format': 'text'}
        resp = requests.post(LOCAL_URL, json=body, timeout=(5, LOCAL_TIMEOUT))  # (соединение, ответ): недоступный переводчик — отказ за 5 с
        if resp.status_code != 200:
            raise CloudTranslateError(f'LibreTranslate HTTP {resp.status_code}: {resp.text[:150]}',
                                      retryable=resp.status_code >= 500)
        return resp.json()['translatedText']

    def last_error(self):
        """Причина последнего неудачного перевода в текущем потоке (тип исключения и начало сообщения) или ''."""
        return getattr(self._tls, 'error', '')

    def set_low_priority(self, low=True):
        """Поток-фон (перевод накопленных новостей): его запросы уступают переводам свежих новостей."""
        self._tls.low = low

    def translate(self, text, target_lang, source_lang=None, request_id=None):
        """Перевод с приоритетом: фоновый поток (set_low_priority) перед каждым запросом ждёт, пока не освободятся
        все обычные переводы (до 10 мин), поэтому свежие новости не стоят в очереди за накопленными."""
        if getattr(self._tls, 'low', False):
            deadline = time.time() + 600
            while self._high_active > 0 and time.time() < deadline:
                time.sleep(0.2)
            return self._translate(text, target_lang, source_lang, request_id)
        with self._prio_lock:
            self._high_active += 1
        try:
            return self._translate(text, target_lang, source_lang, request_id)
        finally:
            with self._prio_lock:
                self._high_active -= 1

    def _translate(self, text, target_lang, source_lang=None, request_id=None):
        """
        Переводит текст на указанный язык с обработкой ошибок

        :param text: текст для перевода
        :param target_lang: целевой язык
        :param source_lang: исходный язык (опционально)
        :param request_id: идентификатор запроса (опционально)
        :return: (успех, результат) - кортеж из флага успеха и результата перевода
        """
        if not text or text.strip() == '':
            return True, ''

        self._tls.error = ''
        if source_lang and _std_lang(source_lang) == _std_lang(target_lang):
            return True, text  # язык исходного текста совпадает с целевым — переводить нечего
        self._cooldown_wait()
        current_delay = self.initial_delay

        for attempt in range(self.max_retries):
            try:
                # Замок — только на сам запрос к Google (запросы идут по одному, чтобы не ловить 429).
                # Паузы повторов и охлаждение — вне замка: прежде они стояли под замком и останавливали
                # переводы во всех потоках сразу.
                with self.lock:
                    if TRANSLATE_BACKEND == 'local':
                        result = self._local_translate(text, target_lang, source_lang)
                    elif TRANSLATE_BACKEND == 'free':
                        if source_lang:
                            # deep_translator знает иврит только как 'iw'
                            src = 'iw' if _std_lang(source_lang) == 'he' else source_lang
                            result = GoogleTranslator(source=src, target=target_lang).translate(text)
                        else:
                            result = GoogleTranslator(target=target_lang).translate(text)
                    else:
                        result = self._cloud_translate(text, target_lang, source_lang)

                # GoogleTranslator.translate() может вернуть None для некоторых входных текстов
                if result is None:
                    result = text

                # Google иногда отдаёт свою страницу ошибки вместо перевода (см. комментарий
                # к _is_google_error_page) — deep_translator не бросает исключение в этом случае,
                # поэтому проверяем результат сами и обрабатываем как временную ошибку.
                if _is_google_error_page(result):
                    raise RuntimeError('Google Translate вернул страницу ошибки вместо перевода')

                # Сброс счетчика ошибок при успехе
                self.consecutive_errors = 0
                return True, result

            except TooManyRequests as e:
                self._tls.error = f'TooManyRequests (Google отклонил запрос: 429/sorry, блокировка по частоте или IP): {str(e)[:80]}'
                self.consecutive_errors += 1
                self.last_error_time = time.time()

                self.logger.warning(
                    f"TooManyRequests при переводе на {target_lang}. "
                    f"Попытка {attempt + 1}/{self.max_retries}, ожидание {current_delay} сек."
                )

                if attempt < self.max_retries - 1:
                    time.sleep(current_delay)
                    current_delay *= 2  # Экспоненциальная задержка
                else:
                    self.logger.error(f"Превышено максимальное количество попыток перевода на {target_lang}")
                    return False, text

            except Exception as e:
                self._tls.error = f'{type(e).__name__}: {str(e)[:150]}'
                self.logger.error(f"Ошибка перевода: {str(e)}")
                # 403/400 и т.п. (API не включён, нет прав, неверный язык) повторять бессмысленно
                if isinstance(e, CloudTranslateError) and not e.retryable:
                    return False, text
                if attempt < self.max_retries - 1:
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    return False, text

        return False, text

    def _cooldown_wait(self):
        """Глобальное охлаждение после серии ошибок TooManyRequests: пауза (вне замка запросов), затем сброс счётчика."""
        with self._state_lock:
            if self.consecutive_errors < 5:
                return
            wait_time = self.cooldown_period - (time.time() - self.last_error_time)
        if wait_time > 0:
            self.logger.warning(f"Глобальное охлаждение: ожидание {wait_time:.1f} сек.")
            time.sleep(wait_time)
        with self._state_lock:
            self.consecutive_errors = 0

    def make_translate(self, text, source_lang=None):
        """
        Выполняет перевод текста на русский, английский и иврит

        :param text: исходный текст
        :param source_lang: исходный язык (опционально)
        :return: (error, ru_text, en_text, he_text)
        """
        error = False

        # Определяем перевод в зависимости от исходного языка
        if source_lang == 'ru':
            ru_text = text
            ok_en, en_text = self.translate(text, 'en', source_lang)
            ok_he, he_text = self.translate(text, 'iw', source_lang)  # 'iw' для иврита в Google API
            error = not (ok_en and ok_he)
        elif source_lang == 'en':
            en_text = text
            ok_ru, ru_text = self.translate(text, 'ru', source_lang)
            ok_he, he_text = self.translate(text, 'iw', source_lang)
            error = not (ok_ru and ok_he)
        elif source_lang == 'he' or source_lang == 'iw':
            he_text = text
            ok_ru, ru_text = self.translate(text, 'ru', 'iw')
            ok_en, en_text = self.translate(text, 'en', 'iw')
            error = not (ok_ru and ok_en)
        else:
            # Если язык не указан, определяем его автоматически
            ok_ru, ru_text = self.translate(text, 'ru')
            ok_en, en_text = self.translate(text, 'en')
            ok_he, he_text = self.translate(text, 'iw')
            error = not (ok_ru and ok_en and ok_he)

        return error, ru_text, en_text, he_text

    def async_translate(self, text, target_lang, callback=None, request_id=None):
        """
        Асинхронный перевод текста с вызовом callback по завершении

        :param text: текст для перевода
        :param target_lang: целевой язык
        :param callback: функция обратного вызова (опционально)
        :param request_id: идентификатор запроса (опционально)
        """

        def worker():
            success, result = self.translate(text, target_lang)
            if callback:
                callback(success, result, request_id)
            else:
                with self.lock:
                    self.results[request_id] = (success, result)

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        return request_id or id(thread)