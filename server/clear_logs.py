"""
Поток очистки старых записей журнала.

Периодически (по умолчанию раз в сутки) вызывает серверную функцию delete_logs,
которая удаляет записи старше заданного количества дней.
"""
import json
import trafaret_thread
import time
import common as cd
from common import SRC
import datetime
import config as cfg


class ClearLogs(trafaret_thread.TrafaretThread):
    """Поток периодической очистки логов старше count_days дней."""

    def __init__(self, source, code_function, code_period, description):
        super(ClearLogs, self).__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        super(ClearLogs, self).initiation_parameters()
        self.par.append({"code": "period", "value": 1440})
        self.par.append({"code": "count_days", "value": 7})

    def work(self):
        super(ClearLogs, self).work()
        try:
            count_days = cd.get_value_config_param("count_days", self.par)
            if count_days <= 0:
                cd.write_log_db('❌ERROR', SRC,
                                f"Ошибка в задании кол-ва дней хранения {count_days}; Повторим через минуту",
                                law_id=self.source, td=time.time() - self.t0)
                return False

            first_date = datetime.date.today() - datetime.timedelta(days=count_days)
            last_date = first_date.isoformat()

            if not self.make_login():
                cd.write_log_db('❌ERROR', SRC, "Ошибка login;\nПовторим через минуту",
                                law_id=self.source, td=time.time() - self.t0)
                return False

            answer, is_ok, status = cd.send_rest(
                "v1/function/{schema}/delete_logs?text='{text}'&view=0".format(
                    schema=cfg.schema_name, text=last_date), 'POST', token_user=self.token)
            if not is_ok:
                cd.write_log_db('❌ERROR', SRC, f"{answer}; Повторим через минуту",
                                law_id=self.source, td=time.time() - self.t0)
                return False

            answer = json.loads(answer)
            if 'count_before' not in answer:
                cd.write_log_db('❌ERROR', SRC,
                                f"Неожиданный ответ сервера: {answer}; Повторим через минуту",
                                law_id=self.source, td=time.time() - self.t0)
                return False

            start_count = answer['count_before']
            finish_count = answer.get('count_after', '?')
            self.finish_text = (f'Было строк {start_count}. Стало строк {finish_count}'
                                f'\nКол-во дней хранения={count_days}')
            return True

        except Exception as er:
            cd.write_log_db('❌Exception', SRC, f"{er};\nПовторим через минуту",
                            law_id=self.source, td=time.time() - self.t0)
            return False
