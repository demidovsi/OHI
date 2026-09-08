from flask import flash

from common import get
import search_words
import rss
import news


def prepare_form(user_id, request):
    unit = get(user_id, 'delete_source')
    if 'indexYes' in request.form:
        st = get(user_id, 'code')
        if st:
            if unit == 'theme':
                search_words.delete_theme(user_id, st)
            if unit == 'rss':
                rss.delete_rss(user_id, st)
            if unit == 'news':
                news.delete_new(user_id, st)
        else:
            flash('Отказ от подтверждения удаления (ни да, ни нет)', 'info')
