"""
Байт-в-байт одинаковые утилиты, ранее продублированные в common.py web и server.
"""
import base64


def decode(key, enc):
    """Декодирует строку, закодированную encode(), используя XOR-подобный алгоритм с ключом."""
    dec = []
    enc = base64.urlsafe_b64decode(enc).decode()
    for i in range(len(enc)):
        key_c = key[i % len(key)]
        dec_c = chr((256 + ord(enc[i]) - ord(key_c)) % 256)
        dec.append(dec_c)
    return "".join(dec)


def encode(key, text):
    """Кодирует строку XOR-подобным алгоритмом с ключом и упаковывает в base64."""
    enc = []
    for i in range(len(text)):
        key_c = key[i % len(key)]
        enc_c = chr((ord(text[i]) + ord(key_c)) % 256)
        enc.append(enc_c)
    return base64.urlsafe_b64encode("".join(enc).encode()).decode()


def str1000(number, sep=' '):
    """
    Вывод целого значения числа с разделением по тысячам (три знака) через указанную строку (по умолчанию - пробел).
    :param number: значение целого числа,
    :param sep: - разделитель между тройками цифр,
    :return: возвращается строка, типа 123 456 789.
    """
    if number is None:
        return ''
    if isinstance(number, (int, str)):
        n = str(number)[::-1]
        return sep.join(n[i:i + 3] for i in range(0, len(n), 3))[::-1]
    return str(number)


def get_duration(td):
    """Форматирует длительность в секундах в строку вида '2 days 01:23:45'."""
    result = ''
    if td is None:
        return result
    if '<' in str(td):
        return str(td) + ' sec'
    tdr = int(td + 0.5)
    if tdr == 0:
        return '< 0.5 sec'
    if tdr >= 86400:
        result = str(tdr // 86400) + ' day'
        if tdr // 86400 != 1:
            result = result + 's'
        tdr = tdr % 86400
    if tdr // 3600:
        result = result + " {hour:02}:{minute:02}:{second:02}".format(
            hour=tdr // 3600, minute=tdr % 3600 // 60, second=tdr % 3600 % 60)
    else:
        result = result + " {minute:02}:{second:02}".format(minute=tdr % 3600 // 60, second=tdr % 3600 % 60)
    return result
