"""
Базовый класс для потоковой обработки задач по расписанию.
Реализует периодический запуск метода work() с конфигурируемыми параметрами,
логированием и обработкой ошибок.
"""
import asyncio
import threading
import time
import common as cd
from common import SRC


class TrafaretThread(threading.Thread):
    """
    Шаблонный поток с периодическим выполнением задачи.

    Подклассы должны переопределить:
      - work() — основная логика задачи (возвращает True при успехе)
      - initiation_parameters() — начальные параметры конфигурации (опционально)
    """
    # Значения по умолчанию (неизменяемые типы — безопасно на уровне класса)
    source = ''               # идентификатор источника (для логов)
    code_period = ''          # код параметра периода из конфигурации
    code_function = ''        # код функции для загрузки параметров
    description = ''          # описание потока
    token = ''                # токен авторизации
    lang = 'ru'               # язык по умолчанию
    time_begin = None         # время запуска потока
    from_time = None          # время последней активности
    next_time = 0             # время следующего запуска (unix timestamp)
    finish_text = ''          # текст результата для логирования
    law_id = ''               # идентификатор для логов
    page = None               # номер страницы для логов
    first_cycle = True        # флаг первого цикла
    t0 = None                 # время начала текущей итерации
    initial_delay = 0         # задержка первого запуска, секунд (для разнесения пиков)
    wait_for_error = 600      # пауза при ошибке, секунд (по умолчанию 10 мин)
    print_load = True         # выводить ли лог при загрузке
    in_work = None            # флаг: поток сейчас выполняет работу
    is_error = False          # признак ошибки при получении данных
    global_count = 0          # общее кол-во обработанных элементов
    status_code = 0           # HTTP-код последнего ответа сервера
    number = 0                # номер текущего элемента

    def __init__(self, source, code_function, code_period, description):
        threading.Thread.__init__(self)
        self.daemon = True
        self.source = source
        self.code_period = code_period
        self.code_function = code_function
        self.description = description
        # FIX: Изменяемые атрибуты инициализируются на уровне экземпляра,
        # чтобы избежать общего состояния между экземплярами
        # (list/dict на уровне класса разделяются между всеми экземплярами!)
        self.par = []
        self.rss = {}
        self.initiation_parameters()

    def make_next_time(self, value_minute, from_time):
        """Вычисляет время следующего запуска: from_time + value_minute минут."""
        self.from_time = from_time
        self.next_time = from_time + value_minute * 60

    def define_next_time(self):
        """Определяет next_time: если не задан — текущее время, иначе пересчитывает по периоду."""
        if self.next_time is None or self.next_time == 0:
            self.next_time = time.time()
        else:
            self.make_next_time(cd.get_value_config_param(self.code_period, self.par), self.from_time)

    def analysis_changing_parameters(self, answer):
        """
        Сравнивает текущие параметры с новыми из конфигурации.
        Логирует изменения и при необходимости пересчитывает время следующего запуска.
        """
        if self.first_cycle:
            self.par = answer
        st_difference, st_param_work = cd.get_difference_config_params(self.par, answer)
        self.par = answer
        if self.first_cycle and self.print_load:
            cd.write_log_db('🕶Параметры работы', SRC, cd.translate_from_base(st_param_work.strip()),
                            law_id=self.source, token=self.token)
        if st_difference != '' and not self.first_cycle:
            cd.write_log_db(
                '🔍Изменение параметров', SRC, st_difference.strip(), law_id=self.source, token=self.token)
            last_time = self.next_time
            self.define_next_time()
            if last_time != self.next_time:
                cd.write_log_db(
                    '❎Следующая активность', SRC,
                    'Старая планируемая активность в ' + time.asctime(time.gmtime(last_time)) + '\n' +
                    'Новая планируемая активность в ' + time.asctime(time.gmtime(self.next_time)),
                    law_id=self.source, token=self.token)
        self.first_cycle = False

    def initiation_parameters(self):
        """Переопределяется в подклассах для задания начальных параметров."""
        pass

    def work(self):
        """
        Основная логика задачи. Переопределяется в подклассах.
        Возвращает True при успешном выполнении, False — при ошибке.
        """
        self.in_work = True

    def get_duration(self):
        """Возвращает строку с длительностью работы потока с момента запуска."""
        return cd.get_duration(time.time() - self.time_begin)

    def make_login(self):
        """Выполняет авторизацию и сохраняет токен. Возвращает True при успехе."""
        ans, is_ok, self.token, lang = cd.login_admin()
        return is_ok

    @property
    def _async_loop(self):
        """Персистентный event loop потока: создаётся один раз и переиспользуется.
        Заменяет asyncio.run(), который создаёт/уничтожает loop при каждом вызове,
        что вызывает фрагментацию heap в долгоживущих потоках."""
        if not hasattr(self, '_event_loop') or self._event_loop.is_closed():
            self._event_loop = asyncio.new_event_loop()
        return self._event_loop

    def run(self):
        """
        Главный цикл потока. Каждые ~60 секунд:
        1. Загружает параметры конфигурации
        2. Проверяет, наступило ли время запуска
        3. Вызывает work() и планирует следующий запуск
        """
        self.make_login()
        if self.print_load:
            cd.write_log_db('✈LOAD', SRC, self.description, law_id=self.source, token=self.token)
        self.from_time = time.time()
        self.time_begin = time.time()
        self.next_time = time.time() + self.initial_delay
        while True:
            self.finish_text = ''
            self.law_id = ''
            self.page = None
            self.t0 = time.time()
            answer = cd.load_config_params(self.code_function)
            if answer is not None:
                self.analysis_changing_parameters(answer)  # анализ изменения параметров
                if time.time() >= self.next_time:  # подошло время работать
                    last_time = self.next_time
                    try:
                        if not self.work():
                            # При неудаче — следующая попытка через wait_for_error секунд
                            self.next_time = last_time + self.wait_for_error
                        else:
                            # Успех — планируем следующий запуск по штатному периоду
                            self.make_next_time(cd.get_value_config_param(self.code_period, self.par), self.next_time)
                            # Если пропустили несколько периодов — прокручиваем до будущего
                            while self.next_time < time.time():
                                self.from_time = self.next_time
                                self.define_next_time()
                            st_timeout = ('Тайм-аут ' +
                                  cd.get_duration(cd.get_value_config_param(self.code_period, self.par) * 60) +
                                  ' до ' + time.asctime(time.gmtime(self.next_time)))
                            st = self.law_id if self.law_id else ''
                            if st:
                                st = st + '\n' + self.source
                            else:
                                st = self.source
                            cd.write_log_db('🕒sleep', SRC, st_timeout + '\n' +self.finish_text,
                                            law_id=st, page=self.rss.get('id', self.page),
                                            td=time.time()-self.t0, token=self.token)
                    except Exception as er:
                        self.make_next_time(self.wait_for_error, self.next_time)
                        # Если пропустили несколько периодов — прокручиваем до будущего
                        while self.next_time < time.time():
                            self.from_time = self.next_time
                            self.define_next_time()
                        try:
                            cd.write_log_db(
                                '❌ Exception', SRC,
                                f"{er}; Повторим через {self.wait_for_error // 60} минут\nв " + time.asctime(time.gmtime(self.next_time)) +' \n'+
                                self.rss.get('sh_name', self.law_id),
                                law_id=self.source, page=self.rss.get('id', self.page),
                                td=time.time()-self.t0, token=self.token
                             )
                        except Exception as er:
                            print(f"{er}")
                    self.in_work = False
            # Выдерживаем интервал ~60 секунд между проверками
            time_out = 60 - (time.time() - self.t0)
            if time_out <= 0:
                time_out = 60
            time.sleep(time_out)
