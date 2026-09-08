import time
import threading
import queue
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TooManyRequests
import logging


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
        self.lock = threading.Lock()
        self.last_error_time = 0
        self.consecutive_errors = 0
        self.queue = queue.Queue()
        self.results = {}
        self._setup_logger()

    def _setup_logger(self):
        self.logger = logging.getLogger('TranslationManager')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def translate(self, text, target_lang, source_lang=None, request_id=None):
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

        with self.lock:
            # Проверка на необходимость глобального охлаждения
            if self.consecutive_errors >= 5:
                current_time = time.time()
                if current_time - self.last_error_time < self.cooldown_period:
                    wait_time = self.cooldown_period - (current_time - self.last_error_time)
                    self.logger.warning(f"Глобальное охлаждение: ожидание {wait_time:.1f} сек.")
                    time.sleep(wait_time)
                self.consecutive_errors = 0

            current_delay = self.initial_delay

            for attempt in range(self.max_retries):
                try:
                    if source_lang:
                        result = GoogleTranslator(source=source_lang, target=target_lang).translate(text)
                    else:
                        result = GoogleTranslator(target=target_lang).translate(text)

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

                except TooManyRequests:
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
                    self.logger.error(f"Ошибка перевода: {str(e)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(current_delay)
                        current_delay *= 2
                    else:
                        return False, text

        return False, text

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