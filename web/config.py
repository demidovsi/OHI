import os
from dotenv import load_dotenv

load_dotenv()

# локальный запуск (python main_ohi_web.py); в Cloud Run — gunicorn на $PORT (Dockerfile)
OWN_PORT = int(os.environ.get('PORT', 8082))
OWN_HOST = os.environ.get('OHI_WEB_HOST', '127.0.0.1')
URL = os.environ['URL']
SCHEMA = 'ohi'
LOG_SRC = 'ohi_web'  # метка сайта в журнале (общие формы shared_web)
kirill = os.environ['KIRILL']
select_language = 'ru'
languages = [
    {"key": "en", "name": "EN - English"},
    {"key": "ru", "name": "RU - Russian"},
    {"key": "he", "name": "HE - Hebrew"},
]
