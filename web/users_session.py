import time
import json
import os

users: None
list_users = ''


class Session:
    session = {}
    busy = False

    def __init__(self):
        super(object, self).__init__()
        try:
            if os.path.exists('static/session.json'):
                os.remove('static/session.json')
        except:
            pass

    def exist(self, user_id):
        result = user_id in self.session and 'rights' in self.session[user_id] \
               and self.session[user_id]['rights'] is not None
        return result

    def id_by_name(self, user_name):
        for key in self.session.keys():
            if 'user_name' in self.session[key] and self.session[key]['user_name'] == user_name:
                return key

    def clear(self, user_id):
        self.session[user_id] = {}

    def add_user(self, user_id):
        global list_users
        list_users = list_users + user_id + '; '
        self.clear(user_id)

    def add(self, user_id, key, value):
        self.session[user_id][key] = value

    def find_user(self, user_id, req):
        if user_id not in self.session:
            if 'user_name' in req.form:
                for key in self.session.keys():
                    if self.session[key]['user_name'] == req.form.get('user_name'):
                        return key
        return user_id

    def get(self, user_id, key):
        if user_id in self.session and key in self.session[user_id]:
            return self.session[user_id][key]

    def delete(self, user_id, key):
        if key and user_id in self.session and key in self.session[user_id]:
            return self.session[user_id].pop(key)

    def default(self, user_id, key, value):
        if user_id not in self.session:
            self.session[user_id] = {}
        if key not in self.session[user_id]:
            self.session[user_id][key] = value

    def to_string(self):
        return list_users + '\n' + str(self.session.keys())

    def save(self):
        while self.busy:
            time.sleep(0.1)
        self.busy = True
        try:
            f = open('static/session.json', 'w', encoding='utf-8')
            with f:
                f.write(json.dumps(self.session, indent=4, ensure_ascii=False, sort_keys=True))
        except Exception as er:
            print(f'{er}')
        self.busy = False

    def load(self):
        while self.busy:
            time.sleep(0.1)
        self.busy = True
        if os.path.exists('static/session.json'):
            f = open('static/session.json', 'r', encoding='utf-8')
            with f:
                data = f.read()
                if data:
                    try:
                        self.session = json.loads(data)
                    except Exception as er:
                        self.session = {}
        self.busy = False
