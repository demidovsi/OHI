"""
Конфигурация сервера LLM.
Все секретные и окружение-зависимые параметры загружаются из .env.
"""
import os
from dotenv import load_dotenv

load_dotenv()

URL         = os.environ['LLM_URL']
schema_name = os.environ['LLM_SCHEMA']
app_lang    = os.getenv('LLM_LANG', 'ru')
kirill      = os.environ['LLM_KIRILL']
web         = os.environ['LLM_WEB']

# docker --env-file передаёт значения буквально, включая кавычки — убираем их
credential = os.getenv('CREDENTIAL', '').strip("'\"")
