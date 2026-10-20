"""Заглушка parlaments/shared/secret_params.py для копии формы «Параметры сервисов» (shared_web/functions.py).

Сервисы OHI (server/) читают параметры функций из БД открытым текстом и шифра `enc2:` не знают, поэтому в OHI
секретных кодов нет: значения показываются и сохраняются как есть — как было в прежней форме сайта.
"""


def is_secret_code(code):
    return False


def encrypt(plain, password=None):
    return plain


def decrypt(value, password=None):
    return value
