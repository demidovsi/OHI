import json
import datetime
import numpy as np

import plotly.express as px
import pandas as pd
from flask import flash, redirect, render_template

import config
import common
from common import get, write_log, add

# Нижняя граница по умолчанию для графиков, когда пользователь не задал
# дату начала периода явно (см. filter_date) - не тянем всю историю сразу.
DEFAULT_MIN_DATE = '2024-12-01'

array_default = [
    {'key': 'switch', 'value': 'channels'},
    {'key': 'start_date', 'value': ''},
    {'key': 'end_date', 'value': ''},
    {'key': 'date_filter_type', 'value': 'custom'},
    {'key': 'relative_period', 'value': 7},
    {'key': 'list_channels', 'value': []},
    {'key': 'list_themes', 'value': []},
    {'key': 'selected_channel', 'value': ''},
    {'key': 'selected_theme', 'value': 0},
    {'key': 'selected_name_theme', 'value': ''},
    {'key': 'channel_type', 'value': 'message_count'},
    {'key': 'period_type', 'value': 'day'},
    {'key': 'change_switch', 'value': False},
]


def get_monday(date_str):
    date = pd.to_datetime(date_str)
    monday = date - pd.Timedelta(days=date.weekday())
    return monday.date()


def weekday_number(date_str):
    date = pd.to_datetime(date_str)
    return date.weekday()


def define_interval(request, answer):
    def adjust_dates(months):
        answer['start_date'] = (pd.to_datetime(start_date) + pd.DateOffset(months=months)).date()
        answer['end_date'] = (pd.to_datetime(end_date) + pd.DateOffset(months=months)).date()

    result = False
    start_date = answer.get('start_date')
    end_date = answer.get('end_date')
    relative_period = answer['relative_period']
    if answer['date_filter_type'] == 'custom':
        if start_date and end_date:
            relative_period = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        else:
            relative_period = 0

    if relative_period == 7:
        days = -relative_period if request.form.get('button_to_left') == '1' else relative_period
        if request.form.get('button_to_left') == '1' or request.form.get('button_to_right') == '1':
            answer['start_date'] = str(pd.to_datetime(start_date) + pd.Timedelta(days=days))
            answer['end_date'] = str(pd.to_datetime(end_date) + pd.Timedelta(days=days))
            result = True
    elif relative_period in [30, 90, 180, 365]:
        months = -relative_period // 30 if request.form.get('button_to_left') == '1' else relative_period // 30
        if request.form.get('button_to_left') == '1' or request.form.get('button_to_right') == '1':
            adjust_dates(months)
            result = True
    else:
        if request.form.get('button_to_left') == '1':
            if start_date:
                answer['start_date'] = str(pd.to_datetime(start_date) - pd.Timedelta(days=relative_period))
            if end_date:
                answer['end_date'] = str(pd.to_datetime(end_date) - pd.Timedelta(days=relative_period))
            result = True
        elif request.form.get('button_to_right') == '1':
            if start_date:
                answer['start_date'] = str(pd.to_datetime(start_date) + pd.Timedelta(days=relative_period))
            if end_date:
                answer['end_date'] = str(pd.to_datetime(end_date) + pd.Timedelta(days=relative_period))
            result = True

    answer['start_date'] = str(answer['start_date']).split(' ')[0] if answer['start_date'] else ''
    answer['end_date'] = str(answer['end_date']).split(' ')[0] if answer['end_date'] else ''
    return result

def filter_date(request, answer, data):
    # Фильтрация по дате
    def calculate_period_start_end(relative_period, end):
        date_start = pd.to_datetime(end).date()
        if relative_period == 7:
            date_start = get_monday(end)
            # if weekday_number(end) == 0:
            #     start -= pd.Timedelta(days=relative_period)
            date_end = date_start + pd.Timedelta(days=7)
        else:
            months_offset = {30: 1, 90: 3, 180: 6, 365: 12}.get(relative_period, 0)
            if date_start.day > 1:
                date_start = date_start.replace(day=1) - pd.DateOffset(months=months_offset - 1)
            else:
                date_start -= pd.DateOffset(months=months_offset)
            date_end = date_start + pd.DateOffset(months=months_offset)
        return str(date_start).split(' ')[0], str(date_end).split(' ')[0]

    if len(data) == 0:
        return data
    need = define_interval(request, answer)
    if need:
        # Реальный сдвиг интервала уже произошёл (button_to_left/right в
        # define_interval) - фиксируем его как "устоявшийся". Иначе после
        # POST/Redirect/GET (main_ohi_web.py:analyses) последующий GET той же
        # страницы повторно вызовет filter_date БЕЗ button_to_left/right в
        # request.form, попадёт в ветку ниже (не change_switch) и пересчитает
        # относительный период заново от уже сдвинутой даты - отменяя только
        # что сделанный сдвиг.
        answer['change_switch'] = True
    if not need:
        if answer['date_filter_type'] == "relative" and answer['relative_period']:
            dt_start = answer['start_date'] if answer['start_date'] else datetime.date(2022, 1, 1)
            dt_end = answer['end_date'] if answer['end_date'] else datetime.date.today()
            # Пересчитываем "текущий период" только когда дат ещё нет вовсе
            # (первая загрузка формы, или сброшены явной сменой relative_period
            # выше) - НЕ по факту change_switch=False, т.к. это условие ложно
            # срабатывает на любой нейтральный "Применить" без реальных
            # изменений (change_switch сбрасывается в False в начале КАЖДОГО
            # POST) - пересчёт брал бы за опору уже вычисленную/сдвинутую
            # dt_end и уезжал бы ещё на один период вперёд при каждом клике.
            if answer['start_date'] == '' or answer['end_date'] == '':
                dt_start, dt_end = calculate_period_start_end(answer['relative_period'], dt_end)
                answer['change_switch'] = True
            answer['start_date'], answer['end_date'] = dt_start, dt_end
            answer['start_date'] = str(dt_start).split(' ')[0]  # Убираем время, оставляем только дату
            answer['end_date'] = str(dt_end).split(' ')[0]  # Убираем время, оставляем только дату
            need = True
        elif answer['start_date'] or answer['end_date']:
            need = True

    # Дата начала не задана явно ни одним из путей выше - не тянем на график
    # всю историю по умолчанию, а ограничиваем снизу DEFAULT_MIN_DATE (сама
    # answer['start_date'] не трогаем - иначе это значение "просочилось" бы
    # в поле "С даты" на форме, хотя пользователь его не выбирал).
    if answer['start_date'] == '':
        need = True
    effective_start = answer['start_date'] if answer['start_date'] else DEFAULT_MIN_DATE

    if need:
        filtered_channels = []
        for channel in data:
            if answer['end_date'] == '':
                if effective_start <= channel['date']:
                    filtered_channels.append(channel)
            else:
                if effective_start <= channel['date'] < str(answer['end_date']):
                    filtered_channels.append(channel)
        return filtered_channels
    return data


def load_messages(user_id, answer):
    inform = get(user_id, 'analyses_messages')
    if inform is None or len(inform) == 0:
        answer['min_date_channels'] = ''
        answer['max_date_channels'] = ''
        # Сутки считаем по локальному времени пользователя (time_zone в
        # минутах, local = UTC + time_zone - см. common.convert_time_to_timezone).
        #
        # Считаем тем же условием, что news.py.get_where для одного дня:
        # строка относится к суткам D, если public_date попадает в D ИЛИ
        # at_date_time попадает в D (news.py проверяет оба поля через OR).
        # Для разбивки по ВСЕМ суткам это разворачивается в UNION ALL двух
        # веток (по public_date и по at_date_time); вторая ветка исключает
        # случай, когда оба поля дают ОДНИ и те же сутки для одной строки -
        # иначе такая строка задвоилась бы внутри одного дня (чего не было бы
        # при OR). Если оба поля указывают на РАЗНЫЕ сутки - строка попадёт
        # в оба дня, ровно как её увидел бы пользователь, листая news.py
        # по датам.
        tz_minutes = get(user_id, 'time_zone') or 0
        tz_interval = "interval '{tz} minutes'".format(tz=tz_minutes)
        theme_filter = (" and id IN (select rss_history_id from {schema}.rel_rss_themes_rss_history_rss "
                        "where rss_themes_id = {theme_id})").format(
            schema=config.SCHEMA, theme_id=answer['selected_theme']
        ) if answer['selected_theme'] and answer['selected_theme'] != 0 else ''
        query = """
                WITH candidates AS (
                    SELECT rss, name_rss AS name_channel,
                           (public_date + {tz_interval})::date AS date
                    FROM {schema}.v_nsi_rss_history
                    WHERE public_date IS NOT NULL
                    {theme_filter}
                    UNION ALL
                    SELECT rss, name_rss AS name_channel,
                           (at_date_time + {tz_interval})::date AS date
                    FROM {schema}.v_nsi_rss_history
                    WHERE at_date_time IS NOT NULL
                      AND (public_date IS NULL
                           OR (public_date + {tz_interval})::date <> (at_date_time + {tz_interval})::date)
                    {theme_filter}
                )
                SELECT rss, name_channel, date, COUNT(*) AS message_count
                FROM candidates
                GROUP BY rss, name_channel, date
                ORDER BY date;
            """.format(schema=config.SCHEMA, tz_interval=tz_interval, theme_filter=theme_filter)
        ans, is_ok, status_code = common.send_rest('v2/execute', 'PUT', params={"script": query},
                                                   token_user=get(user_id, 'token'))
        if not is_ok:
            flash('Ошибка получения данных каналов: ' + str(ans), 'warning')
            return []
        inform = json.loads(ans)
        add(user_id, 'analyses_messages', inform)
    return inform


def load_list_channels(answer):
    url = f'v2/select/{config.SCHEMA}/nsi_rss_list'
    ans, is_ok, status_code = common.send_rest(url, params={"columns": "sh_name"})
    if not is_ok:
        flash('load_list_channels: ' +str(ans), 'warning')
    ans = json.loads(ans)
    answer['list_channels'] = ['']  # Инициализируем с пустой строкой
    for data in ans:
        answer['list_channels'].append(data['sh_name'].strip())
    if answer['selected_channel'] not in answer['list_channels']:
        answer['selected_channel'] = ''


def load_list_themes(answer):
    url = f'v2/select/{config.SCHEMA}/nsi_rss_themes'
    ans, is_ok, status_code = common.send_rest(url, params={"columns": "id, sh_name"})
    if not is_ok:
        flash('load_list_themes: ' +str(ans), 'warning')
    ans = json.loads(ans)
    answer['list_themes'] = []
    answer['list_themes'].append({'id': 0, 'sh_name': ''})  # Инициализируем с пустой строкой
    for data in ans:
        answer['list_themes'].append(data)


def plot_channels_bar(answer, df, user_id, period='day'):
    if len(df) == 0:
        return
    start_date = answer['start_date'] if answer['start_date'] else answer['min_date_channels']
    end_date = answer['end_date'] if answer['end_date'] else answer['max_date_channels']
    days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days

    df['date'] = pd.to_datetime(df['date'])

    if period == 'week':
        df['period'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time)
        group_label = 'По неделям'
    elif period == 'month':
        df['period'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time)
        group_label = 'По месяцам'
    else:
        df['period'] = df['date']
        group_label = 'По дням'

    grouped = df.groupby('period', as_index=False)['message_count'].sum()

    title = f"Активность сообщений {group_label.lower()} ({answer['messages_count']} или {answer['percent']} %)"
    title += " ( интервал " + common.days_phrase(days) + " )"
    fig = px.bar(
        grouped,
        x='period',
        y='message_count',
        title=title,
        height=600,
        template='plotly_dark' if get(user_id, 'theme') == 'black' else 'plotly_white',
        labels={'period': group_label, 'message_count': 'Количество сообщений'},
    )

    if len(df) < 7:
        if 'period' in df.columns:
            unique_periods = np.sort(df['period'].unique())
            if df['period'].dtype.name.startswith('period'):
                # Для pd. Period (например, при группировке по неделям/месяцам)
                ticktexts = [str(p.start_time.date()) if hasattr(p, 'start_time') else str(p) for p in unique_periods]
            elif np.issubdtype(df['period'].dtype, np.datetime64):
                ticktexts = [pd.to_datetime(p).strftime("%Y-%m-%d") for p in unique_periods]
            else:
                ticktexts = [str(p) for p in unique_periods]
            fig.update_xaxes(
                tickvals=unique_periods,
                ticktext=ticktexts,
                tickformat="%Y-%m-%d"
            )
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            unique_dates = np.sort(df["date"].unique())
            ticktexts = [d.strftime("%Y-%m-%d") for d in unique_dates]
            fig.update_xaxes(
                tickvals=unique_dates,
                ticktext=ticktexts,
                tickformat="%Y-%m-%d"
            )
    answer['chart'] = fig.to_html(full_html=False)


def plot_participation_bar(answer, df, user_id, period='day'):
    if len(df) == 0:
        return
    start_date = answer['start_date'] if answer['start_date'] else answer['min_date_channels']
    end_date = answer['end_date'] if answer['end_date'] else answer['max_date_channels']
    days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days

    df['date'] = pd.to_datetime(df['date'])

    if period == 'week':
        df['period'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time)
        group_label = 'По неделям'
    elif period == 'month':
        df['period'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time)
        group_label = 'По месяцам'
    else:
        df['period'] = df['date']
        group_label = 'По дням'

    df = df.groupby('period', as_index=False)[['count', 'message_count']].sum()
    has_theme = bool(answer['selected_theme']) and answer['selected_theme'] != 0

    if has_theme:
        # message_count (nsi_log_rss_history, отфильтрован по теме через url)
        # - подмножество count (все сырые сообщения канала за день,
        # nsi_rss_history), поэтому доля = message_count/count, а не наоборот -
        # иначе почти всегда получалось бы >100% (count обычно >= message_count)
        df["percent"] = np.where(df["count"] > 0,
                                 (df["message_count"] / df["count"] * 100.0).round(1),
                             np.nan)
        grouped = df.groupby('period', as_index=False)['percent'].sum()
        y_col, y_label = 'percent', '% сообщений с темами'
        title = f"Участие каналов в темах сообщений {group_label.lower()} ({answer['messages_count']} или {answer['percent']} %)"
    else:
        # Без выбранной темы message_count (nsi_log_rss_history) не является
        # подмножеством count - это независимый счётчик, у их отношения нет
        # верхней границы в 100%, поэтому без темы показываем абсолютные
        # значения, а не бессмысленный "процент"
        grouped = df.groupby('period', as_index=False)['message_count'].sum()
        y_col, y_label = 'message_count', 'Количество сообщений'
        title = f"Участие каналов в темах сообщений {group_label.lower()} ({answer['messages_count']})"
    title += " ( интервал " + common.days_phrase(days) + " )"
    fig = px.bar(
        grouped,
        x='period',
        y=y_col,
        title=title,
        height=600,
        template='plotly_dark' if get(user_id, 'theme') == 'black' else 'plotly_white',
        labels={'period': group_label, y_col: y_label},
    )

    if len(df) < 7:
        if 'period' in df.columns:
            unique_periods = np.sort(df['period'].unique())
            if df['period'].dtype.name.startswith('period'):
                # Для pd. Period (например, при группировке по неделям/месяцам)
                ticktexts = [str(p.start_time.date()) if hasattr(p, 'start_time') else str(p) for p in unique_periods]
            elif np.issubdtype(df['period'].dtype, np.datetime64):
                ticktexts = [pd.to_datetime(p).strftime("%Y-%m-%d") for p in unique_periods]
            else:
                ticktexts = [str(p) for p in unique_periods]
            fig.update_xaxes(
                tickvals=unique_periods,
                ticktext=ticktexts,
                tickformat="%Y-%m-%d"
            )
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            unique_dates = np.sort(df["date"].unique())
            ticktexts = [d.strftime("%Y-%m-%d") for d in unique_dates]
            fig.update_xaxes(
                tickvals=unique_dates,
                ticktext=ticktexts,
                tickformat="%Y-%m-%d"
            )
    answer['chart'] = fig.to_html(full_html=False)


def plot_channels_line(answer, df, user_id):
    if len(df) > 0:
        # графики
        df["date"] = pd.to_datetime(df["date"])
        start_date = answer['start_date'] if answer['start_date'] else answer['min_date_channels']
        end_date = answer['end_date'] if answer['end_date'] else answer['max_date_channels']
        days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        title = "Активность сообщений в каналах по дням ({count} или {percent} %)".format(count=answer['messages_count'],
                                                                                          percent=answer['percent'])
        title += " ( интервал " + common.days_phrase(days) + " )"
        df['legend_name'] = df.groupby('name_channel')['message_count'].transform('sum')
        df['legend_name'] = df['name_channel'] + ' (' + df['legend_name'].astype(str) + ')'

        fig = px.line(
            df,
            x="date",
            y="message_count",
            color="legend_name",  # Каждая линия — отдельный канал
            markers=True,
            template='plotly_dark' if get(user_id, 'theme') == 'black' else 'plotly_white',
            title=title,
            labels={
                "date": "Дата",
                "message_count": "Количество сообщений",
                "legend_name": "Канал"
            }
        )

        # Отключаем соединение между точками с пропущенными значениями
        # for trace in fig.data:
        #     trace.connectgaps = False

        fig.update_layout(
            xaxis_title="Дата",
            yaxis_title="Сообщений",
            hovermode="x unified",
            legend_title="Канал",
            yaxis_range=[0, None],  # Установка начала оси Y с нуля
            height=600,  # высота в пикселях
            width=1400,  # ширина в пикселях (по желанию)
            autosize=False  # отключаем автоматический размер
        )

        if len(df) < 7:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            unique_dates = np.sort(df["date"].unique())
            ticktexts = [d.strftime("%Y-%m-%d") for d in unique_dates]
            fig.update_xaxes(
                tickvals=unique_dates,
                ticktext=ticktexts,
                tickformat="%Y-%m-%d"
            )

        answer['chart'] = fig.to_html(full_html=False)


def plot_participation_line(answer, df, user_id):
    if len(df) > 0:
        # графики
        df["date"] = pd.to_datetime(df["date"])
        start_date = answer['start_date'] if answer['start_date'] else answer['min_date_channels']
        end_date = answer['end_date'] if answer['end_date'] else answer['max_date_channels']
        days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        has_theme = bool(answer['selected_theme']) and answer['selected_theme'] != 0
        if has_theme:
            title = "Участие каналов в темах сообщений по дням ({count} или {percent} %)".format(
                count=answer['messages_count'], percent=answer['percent'])
        else:
            title = "Участие каналов в темах сообщений по дням ({count})".format(count=answer['messages_count'])
        title += " ( интервал " + common.days_phrase(days) + " )"
        df['legend_name'] = df.groupby('name_channel')['message_count'].transform('sum')
        df['legend_name'] = df['name_channel'] + ' (' + df['legend_name'].astype(str) + ')'

        if has_theme:
            # message_count - подмножество count (см. plot_participation_bar), доля
            # = message_count/count, иначе почти всегда получалось бы >100%
            df["percent"] = np.where(df["count"] > 0,
                                     df["message_count"] / df["count"] * 100.0,
                                     np.nan)
            y_col, y_axis_title = "percent", "% сообщений"
        else:
            # Без темы message_count не подмножество count - отношение
            # ничем не ограничено сверху, показываем абсолютные значения
            y_col, y_axis_title = "message_count", "Сообщений"

        fig = px.line(
            df,
            x="date",
            y=y_col,
            color="legend_name",  # Каждая линия — отдельный канал
            markers=True,
            template='plotly_dark' if get(user_id, 'theme') == 'black' else 'plotly_white',
            title=title,
            labels={
                "date": "Дата",
                "message_count": "Количество сообщений",
                "percent": "% сообщений",
                "legend_name": "Канал"
            }
        )

        # Отключаем соединение между точками с пропущенными значениями
        # for trace in fig.data:
        #     trace.connectgaps = False

        fig.update_layout(
            xaxis_title="Дата",
            yaxis_title=y_axis_title,
            hovermode="x unified",
            legend_title="Канал",
            yaxis_range=[0, None],  # Установка начала оси Y с нуля
            height=600,  # высота в пикселях
            width=1400,  # ширина в пикселях (по желанию)
            autosize=False  # отключаем автоматический размер
        )

        if len(df) < 7:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            unique_dates = np.sort(df["date"].unique())
            ticktexts = [d.strftime("%Y-%m-%d") for d in unique_dates]
            fig.update_xaxes(
                tickvals=unique_dates,
                ticktext=ticktexts,
                tickformat="%Y-%m-%d"
            )

        answer['chart'] = fig.to_html(full_html=False)


def load_participation(user_id, answer):
    inform = get(user_id, 'analyses_participation')
    if inform is None or len(inform) == 0:
        # "Участие" считаем целиком из nsi_rss_history (реальные сообщения) -
        # nsi_log_rss_history сюда не годится: проверено, что это отдельный,
        # существенно более широкий лог URL (943к строк против 169к сообщений
        # по всей истории), 4 из 5 его записей вообще не становятся
        # сообщением - никакого "% участия в теме" из него не получить.
        #
        # Сутки - по локальному времени пользователя, тем же условием OR по
        # public_date/at_date_time, что и load_messages (совпадает с news.py).
        tz_minutes = get(user_id, 'time_zone') or 0
        tz_interval = "interval '{tz} minutes'".format(tz=tz_minutes)
        theme_id = answer['selected_theme']
        if theme_id and theme_id != 0:
            message_count_expr = (
                "COUNT(*) FILTER (WHERE id IN ("
                "select rss_history_id from {schema}.rel_rss_themes_rss_history_rss "
                "where rss_themes_id = {theme_id})) AS message_count"
            ).format(schema=config.SCHEMA, theme_id=theme_id)
        else:
            message_count_expr = "COUNT(*) AS message_count"
        query = """
                    WITH candidates AS (
                        SELECT rss, name_rss AS name_channel, id,
                               (public_date + {tz_interval})::date AS date
                        FROM {schema}.v_nsi_rss_history
                        WHERE public_date IS NOT NULL
                        UNION ALL
                        SELECT rss, name_rss AS name_channel, id,
                               (at_date_time + {tz_interval})::date AS date
                        FROM {schema}.v_nsi_rss_history
                        WHERE at_date_time IS NOT NULL
                          AND (public_date IS NULL
                               OR (public_date + {tz_interval})::date <> (at_date_time + {tz_interval})::date)
                    )
                    SELECT rss, name_channel, date, COUNT(*) AS count, {message_count_expr}
                    FROM candidates
                    GROUP BY rss, name_channel, date
                    ORDER BY date;
                """.format(schema=config.SCHEMA, tz_interval=tz_interval, message_count_expr=message_count_expr)
        ans, is_ok, status_code = common.send_rest('v2/execute', 'PUT', params={"script": query},
                                                   token_user=get(user_id, 'token'))
        if not is_ok:
            flash('Ошибка получения данных каналов: ' + str(ans), 'warning')
            return []
        inform = json.loads(ans)
        add(user_id, 'analyses_participation', inform)
    return inform


def get_data_participation(user_id, request, answer):
    inform = load_participation(user_id, answer)
    channels = list(inform)  # копии строк не нужны - downstream код их не мутирует
    answer['total_messages_count'] = sum(channel['message_count'] for channel in channels)
    answer['min_date_channels'] = channels[0]['date'] if channels else ''
    answer['max_date_channels'] = channels[-1]['date'] if channels else ''
    # Фильтрация по дате
    channels = filter_date(request, answer, channels)

    df = pd.DataFrame(channels, columns=['date', 'name_channel', 'message_count', 'count'])

    if answer['channel_type'] == 'message_count' and len(df) > 0:
        # Суммируем количество сообщений по каналам
        result = (
            df.groupby(['date', 'name_channel'], as_index=False)[['count', 'message_count']]
            .sum()
            .to_dict('records')
        )
        df = pd.DataFrame(result)
    else:
        # Фильтрация по каналу
        if answer['selected_channel'] not in ['', 'Все каналы']:
            df = df[df['name_channel'] == answer['selected_channel']]

    answer['messages_count'] = df['message_count'].sum() if len(df) > 0 else 0
    answer['percent'] = round(100.0 * answer['messages_count'] / answer['total_messages_count'] if answer['total_messages_count'] > 0 else 0, 1)

    # ПОДГОТОВИТЬ ГРАФИКИ
    if answer['channel_type'] == 'message_channels':
        plot_participation_line(answer, df, user_id)
    else:
        plot_participation_bar(answer, df, user_id, answer['period_type'])
    return df


def get_data_channels(user_id, request, answer):
    inform = load_messages(user_id, answer)
    channels = list(inform)  # копии строк не нужны - downstream код их не мутирует
    answer['total_messages_count'] = sum(channel['message_count'] for channel in channels)
    answer['min_date_channels'] = channels[0]['date'] if channels else ''
    answer['max_date_channels'] = channels[-1]['date'] if channels else ''
    # Фильтрация по дате
    channels = filter_date(request, answer, channels)
    df = pd.DataFrame(channels)
    if answer['channel_type'] == 'message_count' and len(df) > 0:
        # Суммируем количество сообщений по каналам
        result = (
            df.groupby('date', as_index=False)['message_count']
            .sum()
            .to_dict('records')
        )
        df = pd.DataFrame(result)
    else:
        # Фильтрация по каналу
        if answer['selected_channel'] not in ['', 'Все каналы']:
            df = df[df['name_channel'] == answer['selected_channel']]

    answer['messages_count'] = df['message_count'].sum() if len(df) > 0 else 0
    answer['percent'] = round(100.0 * answer['messages_count'] / answer['total_messages_count'] if answer['total_messages_count'] > 0 else 0, 1)

    # ПОДГОТОВИТЬ ГРАФИКИ
    if answer['channel_type'] == 'message_channels':
        plot_channels_line(answer, df, user_id)
    else:
        plot_channels_bar(answer, df, user_id, answer['period_type'])
    return df


def get_name_theme(answer):
    answer['selected_name_theme'] = ''
    if answer['selected_theme'] and answer['selected_theme'] != 0 and 'list_themes' in answer:
        for theme in answer['list_themes']:
            if theme['id'] == answer['selected_theme']:
                answer['selected_name_theme'] = theme['sh_name']
                break


def prepare_form(user_id, request):
    answer = dict()
    st = common.init_form(user_id, request, '/analyses/')
    if st:
        answer['redirect'] = st
        return answer
    try:
        common.default_form(user_id, array_default, answer, 'analyses_')
        if request.method == 'POST':
            common.choose_language(user_id, request)
            answer['change_switch'] = False
            if 'refresh' in request.form:
                add(user_id, 'analyses_messages', [])
                add(user_id, 'analyses_participation', [])
                answer['change_switch'] = True
            if 'selected_channel' in request.form and answer['selected_channel'] != request.form.get('selected_channel'):
                answer['selected_channel'] = request.form.get('selected_channel').strip()
            if 'selected_theme' in request.form and answer['selected_theme'] != int(request.form.get('selected_theme')):
                answer['selected_theme'] = int(request.form.get('selected_theme'))
                get_name_theme(answer)
                add(user_id, 'analyses_messages', [])
                add(user_id, 'analyses_participation', [])
            if "channels" in request.form and answer['switch'] != 'channels':
                answer['switch'] = 'channels'
                answer['change_switch'] = True
            if "participation" in request.form and answer['switch'] != 'participation':
                answer['switch'] = 'participation'
                answer['change_switch'] = True
            if answer['date_filter_type'] != request.form.get("date_filter_type", "custom"):
                answer['change_switch'] = True
                answer['date_filter_type'] = request.form.get("date_filter_type", "custom")
            if 'channel_type' in request.form and answer['channel_type'] != request.form.get("channel_type"):
                answer['change_switch'] = True
                answer['channel_type'] = request.form.get("channel_type")
            answer['period_type'] = request.form.get("period_type", "day")
            if answer['date_filter_type'] == 'custom' or request.form.get("start_date"):
                answer['start_date'] = request.form.get("start_date")
            if answer['date_filter_type'] == 'custom' or request.form.get("end_date"):
                answer['end_date'] = request.form.get("end_date")
            if 'relative_period' in request.form and answer['relative_period'] != int(request.form.get("relative_period")):
                answer['relative_period'] = int(request.form.get("relative_period"))
                answer['start_date'] = ''  # Сброс даты при смене периода
                answer['end_date'] = ''  # Сброс даты при смене периода
        else:
            load_list_channels(answer)
            load_list_themes(answer)
            write_log('Анализ сообщений', user_id, request)

        if answer['switch'] == 'channels':
            get_data_channels(user_id, request, answer)
        if answer['switch'] == 'participation':
            get_data_participation(user_id, request, answer)
    except Exception as err:
        add(user_id, 'analyses_messages', [])
        add(user_id, 'analyses_participation', [])
        answer['selected_theme'] = 0
        answer['selected_channel'] = ''
        answer['start_date'] = ''
        answer['end_date'] = ''
        answer['date_filter_type'] = 'custom'
        flash(f'{err}', 'warning')
    common.save_form(user_id, array_default, answer, 'analyses_')
    return answer
