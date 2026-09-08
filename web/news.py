import json

from flask import flash

import config
import cloud
import common

def load_list_rss(answer):
    """
        чтение списка сайтов с RSS
    """
    answer['list_rss'] = []
    url = 'v2/entity/values?app_code={schema}&object_code=rss_list&column_order=id desc'.format(schema=config.SCHEMA)
    ans, is_ok, status = common.send_rest(url, params={"columns": "id, sh_name, lang"})
    if not is_ok:
        flash(str(ans), 'warning')
        return False
    else:
        answer['list_rss'] = json.loads(ans)
        answer['list_rss'].insert(0, {'id': 0, 'sh_name': '', 'lang': ''})
        return True


def load_themes(answer):
    """
        чтение списка тем
    """
    answer['themes'] = []
    url = 'v2/entity/values?app_code={schema}&object_code=rss_themes'.format(schema=config.SCHEMA)
    ans, is_ok, status = common.send_rest(url)
    if not is_ok:
        flash(str(ans), 'warning')
        return False
    else:
        answer['themes'] = json.loads(ans)
        answer['themes'].insert(0, {'id': 0, 'sh_name': '', 'value': ''})
        return True


def delete_new(user_id, obj_id):
    cloud.delete_new(user_id, obj_id, True)
