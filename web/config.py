import os
from dotenv import load_dotenv

load_dotenv()

OWN_PORT = int(os.environ.get('PORT', 8082))
OWN_HOST = '0.0.0.0'
URL = os.environ['URL']
SCHEMA = 'ohi'
kirill = os.environ['KIRILL']
select_language = 'ru'
languages = [
    {"key": "en", "name": "EN - English"},
    {"key": "ru", "name": "RU - Russian"},
    {"key": "he", "name": "HE - Hebrew"},
    {"key": "de", "name": "DE - German"},
    {"key": "fr", "name": "FR - France"},
    {"key": "es", "name": "ES - Spanish"},
    {"key": "zh-CN", "name": "zh-CN - Chinese (simplified)"},
]
