// "Новости (дашборд)" - максимум операций на фронтенде: сервер отдаёт одни
// сутки данных целиком (со всеми языковыми вариантами заголовка/описания
// сразу), а дальше поиск, фильтры по каналу/теме/языку и сортировка работают
// в браузере без единого лишнего запроса к серверу. Единственное, что уходит
// на сервер повторно - смена даты (другие сутки) и удаление новости.

var loadingIcon = document.querySelector('#loadingIcon');

(function () {
    document.body.style.display = 'block';

    var TXT = window.NEWS_BOARD_TXT || [];

    // Язык вывода ТЕКСТА новостей (#nb_lang) - независим от языка интерфейса
    // (select_language в topbar, NEWS_BOARD_LANG). Раньше state.lang всегда
    // брался из NEWS_BOARD_LANG - смена языка интерфейса (перезагружает
    // страницу) незаметно сбрасывала и выбор языка новостей на тот же язык.
    // Запоминаем выбор отдельно в localStorage, чтобы он переживал такую
    // перезагрузку; NEWS_BOARD_LANG остаётся значением по умолчанию только
    // для самого первого визита, когда в localStorage ещё ничего нет.
    var LANG_KEY = 'ohi_news_board_lang';
    function getSavedLang() {
        try { return localStorage.getItem(LANG_KEY); } catch (e) { return null; }
    }
    function saveLang(lang) {
        try { localStorage.setItem(LANG_KEY, lang); } catch (e) {}
    }

    // Выбранная (закреплённая) новость - id запоминается в localStorage и
    // выделяется фоном ВСЕГДА, при любом render() (не разово, как раньше:
    // прямой classList.add на конкретном узле терялся при следующей же
    // перерисовке - смена фильтра/поиска/сортировки просто перестраивает
    // tbody.innerHTML заново через rowHtml()).
    var SELECTED_KEY = 'ohi_news_board_selected_id';
    function getSavedSelected() {
        try { return localStorage.getItem(SELECTED_KEY); } catch (e) { return null; }
    }
    function setSelected(id) {
        state.selectedId = id != null ? String(id) : null;
        try {
            if (state.selectedId) localStorage.setItem(SELECTED_KEY, state.selectedId);
            else localStorage.removeItem(SELECTED_KEY);
        } catch (e) {}
    }

    var state = {
        rows: [],           // сырые данные текущих суток (как пришли с сервера)
        lang: getSavedLang() || window.NEWS_BOARD_LANG || 'ru',
        selectedId: getSavedSelected(),
        search: '',
        channel: '',
        theme: '',
        sortKey: 'sort_time',
        sortDir: -1,        // -1 = по убыванию (новые сверху), 1 = по возрастанию
        expanded: {}        // id -> true, если описание развёрнуто пользователем
    };

    var tbody = document.querySelector('#nb_tbody');
    var emptyEl = document.querySelector('#nb_empty');
    var summaryEl = document.querySelector('#nb_summary');
    var dateInput = document.querySelector('#nb_date');
    var searchInput = document.querySelector('#nb_search');
    var channelSelect = document.querySelector('#nb_channel');
    var themeSelect = document.querySelector('#nb_theme');
    var langSelect = document.querySelector('#nb_lang');
    var flashWrap = document.querySelector('#nb_flash');

    langSelect.value = state.lang;

    function showLoading() { if (loadingIcon) loadingIcon.style.display = 'block'; }
    function hideLoading() { if (loadingIcon) loadingIcon.style.display = 'none'; }

    function escapeHtml(s) {
        return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // UTC -> локальное время браузера. at_date_time/public_date приходят из
    // БД в UTC без явного суффикса - Date без 'Z' на конце JS трактовал бы их
    // как уже локальные (неверно), поэтому 'Z' добавляется явно.
    function toLocalDate(isoString) {
        if (!isoString) return null;
        var iso = isoString.indexOf('Z') === -1 && isoString.indexOf('+') === -1 ? isoString + 'Z' : isoString;
        var d = new Date(iso);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatDateTime(d) {
        if (!d) return '—';
        var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
        return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear() + ' '
             + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    }

    function prepareRows(rawRows) {
        return (rawRows || []).map(function (r) {
            var d = toLocalDate(r.at_date_time || r.public_date);
            r._sortTime = d ? d.getTime() : 0;
            r._dateText = formatDateTime(d);
            r._themesList = (r.themes || '').split(',').map(function (t) { return t.trim(); }).filter(Boolean);
            r._haystack = [
                r.title_ru, r.title_en, r.title_he,
                r.description_ru, r.description_en, r.description_he,
                r.author, r.name_rss, r.themes, r.id
            ].join('   ').toLowerCase();
            return r;
        });
    }

    function renderMessages(messages) {
        if (!flashWrap) return;
        flashWrap.innerHTML = '';
        (messages || []).forEach(function (entry) {
            var div = document.createElement('div');
            div.className = 'alert alert-' + entry[0] + ' alert-dismissible fade show';
            div.innerHTML = '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' + escapeHtml(entry[1]);
            flashWrap.appendChild(div);
        });
    }

    function currentFiltered() {
        var q = state.search.trim().toLowerCase();
        var list = state.rows.filter(function (r) {
            if (state.channel && r.name_rss !== state.channel) return false;
            if (state.theme && r._themesList.indexOf(state.theme) === -1) return false;
            if (q && r._haystack.indexOf(q) === -1) return false;
            return true;
        });
        var key = state.sortKey;
        var dir = state.sortDir;
        list.sort(function (a, b) {
            var av, bv;
            if (key === 'sort_time') { av = a._sortTime; bv = b._sortTime; }
            else if (key === 'title') { av = (a['title_' + state.lang] || '').toLowerCase(); bv = (b['title_' + state.lang] || '').toLowerCase(); }
            else if (key === 'themes') { av = (a.themes || '').toLowerCase(); bv = (b.themes || '').toLowerCase(); }
            else { av = (a[key] || '').toString().toLowerCase(); bv = (b[key] || '').toString().toLowerCase(); }
            if (av < bv) return -1 * dir;
            if (av > bv) return 1 * dir;
            return 0;
        });
        return list;
    }

    function rowHtml(r) {
        var title = escapeHtml(r['title_' + state.lang] || r.title_ru || '');
        var desc = escapeHtml(r['description_' + state.lang] || r.description_ru || '');
        var themesHtml = r._themesList.map(function (t) {
            return '<span class="nb-theme-badge">' + escapeHtml(t) + '</span>';
        }).join('');
        var expanded = state.expanded[r.id] ? ' nb-expanded' : '';
        var deleteBtn = window.NEWS_BOARD_ADMIN
            ? '<td><button type="button" class="nb-delete-btn" data-id="' + r.id + '" title="' + TXT[36] + '">🗑️</button></td>'
            : '';
        var selected = state.selectedId && String(r.id) === state.selectedId ? ' nb-row-return' : '';
        return (
            '<tr data-id="' + r.id + '" class="' + selected + '">' +
            '<td class="nb-row-datetime">' + r._dateText + '<br><span class="nb-row-id">#' + r.id + '</span></td>' +
            '<td>' + escapeHtml(r.name_rss || '') + (r.author ? '<br><span style="opacity:.7;font-size:.85em;">' + escapeHtml(r.author) + '</span>' : '') + '</td>' +
            '<td>' +
                '<a href="' + articleHref(r.id) + '" class="nb-row-title" data-id="' + r.id + '">' + (title || TXT[37]) + '</a>' +
                '<div class="nb-row-desc' + expanded + '" data-id="' + r.id + '">' + desc + '</div>' +
            '</td>' +
            '<td>' + themesHtml + '</td>' +
            '<td><span class="nb-lang-badge">' + escapeHtml(r.lang || '') + '</span></td>' +
            deleteBtn +
            '</tr>'
        );
    }

    function render() {
        var list = currentFiltered();
        if (list.length === 0) {
            tbody.innerHTML = '';
            emptyEl.hidden = false;
        } else {
            emptyEl.hidden = true;
            tbody.innerHTML = list.map(rowHtml).join('');
        }
        summaryEl.textContent = TXT[38] + ' ' + list.length + ' ' + TXT[39] + ' ' + state.rows.length;
        updateSortIndicators();
    }

    function updateSortIndicators() {
        document.querySelectorAll('.nb-sortable').forEach(function (th) {
            var key = th.dataset.sort;
            var existing = th.querySelector('.nb-sort-arrow');
            if (existing) existing.remove();
            if (key === state.sortKey) {
                var span = document.createElement('span');
                span.className = 'nb-sort-arrow';
                span.textContent = state.sortDir === 1 ? '▲' : '▼';
                th.appendChild(span);
            }
        });
    }

    function setRows(rawRows) {
        state.rows = prepareRows(rawRows);
        state.expanded = {};
        render();
    }

    function articleHref(id) {
        // back_to=news_board - используется только если статья открыта в
        // отдельной вкладке (Ctrl/средний клик) в обход модалки: new.py
        // читает параметр и добавляет ?select_id=... в кнопку "Назад",
        // чтобы applyReturnHighlight() ниже подсветил нужную строку, когда
        // та вкладка (при обычном клике сюда вообще не переходим - см.
        // openArticleModal и обработчик клика по .nb-row-title).
        return window.NEWS_BOARD_ARTICLE_URL.replace(/0\/?$/, id + '/') + '?back_to=news_board';
    }

    function articleApiUrl(id) {
        return window.NEWS_BOARD_ARTICLE_API_URL.replace(/0\/?$/, id + '/');
    }

    function buildDataUrl(dateStr) {
        var url = window.NEWS_BOARD_DATA_URL;
        return url + (url.indexOf('?') === -1 ? '?' : '&') + 'date=' + encodeURIComponent(dateStr);
    }

    var abortController = null;
    function loadDate(dateStr, onDone) {
        showLoading();
        if (abortController) abortController.abort();
        abortController = new AbortController();
        fetch(buildDataUrl(dateStr), {signal: abortController.signal, headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (r) { return r.json(); })
            .then(function (json) {
                if (json.redirect) { window.location = json.redirect; return; }
                renderMessages(json.messages);
                dateInput.value = dateStr;
                setRows(json.rows);
                hideLoading();
                if (onDone) onDone();
            })
            .catch(function (err) {
                if (err.name !== 'AbortError') hideLoading();
            });
    }

    function shiftDate(days) {
        var parts = dateInput.value.split('-').map(Number);
        var d = new Date(parts[0], parts[1] - 1, parts[2]);
        d.setDate(d.getDate() + days);
        var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
        var newDate = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
        loadDate(newDate);
    }

    // ── события ──

    document.querySelector('#nb_prev').addEventListener('click', function () { shiftDate(-1); });
    document.querySelector('#nb_next').addEventListener('click', function () { shiftDate(1); });
    document.querySelector('#nb_today').addEventListener('click', function () {
        var d = new Date();
        var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
        loadDate(d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()));
    });
    document.querySelector('#nb_refresh').addEventListener('click', function () { loadDate(dateInput.value); });
    dateInput.addEventListener('change', function () { loadDate(dateInput.value); });

    // Выделяет строку (постоянно, через state.selectedId + render) и
    // прокручивает к ней - общий финальный шаг и для кнопки "Перейти по ID"
    // ниже, и для возврата из статьи (applyReturnHighlight), и для закрытия
    // модалки.
    function selectAndScroll(id) {
        setSelected(id);
        render();
        var row = tbody.querySelector('tr[data-id="' + id + '"]');
        if (row) row.scrollIntoView({block: 'center', behavior: 'smooth'});
    }

    // Находит дату новости по id (сервер) и позиционируется на неё - при
    // необходимости подгружая нужные сутки. silent=true - для автоматического
    // позиционирования на ранее выбранную новость при заходе на страницу
    // (не беспокоим alert'ом, если её вдруг больше нет).
    function gotoNewsId(idStr, silent) {
        showLoading();
        fetch(window.NEWS_BOARD_FIND_URL.replace(/0$/, idStr), {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (r) { return r.json(); })
            .then(function (json) {
                hideLoading();
                if (json.redirect) { window.location = json.redirect; return; }
                if (!json.found) { if (!silent) alert(TXT[46]); return; }
                if (dateInput.value === json.date) {
                    selectAndScroll(idStr);
                } else {
                    loadDate(json.date, function () { selectAndScroll(idStr); });
                }
            })
            .catch(function () { hideLoading(); });
    }

    document.querySelector('#nb_goto').addEventListener('click', function () {
        var idStr = prompt(TXT[44]);
        if (!idStr) return;
        idStr = idStr.trim();
        if (!/^\d+$/.test(idStr)) { alert(TXT[45]); return; }
        gotoNewsId(idStr, false);
    });

    var searchTimer = null;
    searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        var val = searchInput.value;
        searchTimer = setTimeout(function () { state.search = val; render(); }, 150);
    });

    channelSelect.addEventListener('change', function () { state.channel = channelSelect.value; render(); });
    themeSelect.addEventListener('change', function () { state.theme = themeSelect.value; render(); });
    langSelect.addEventListener('change', function () { state.lang = langSelect.value; saveLang(state.lang); render(); });

    document.querySelectorAll('.nb-sortable').forEach(function (th) {
        th.addEventListener('click', function () {
            var key = th.dataset.sort;
            if (state.sortKey === key) {
                state.sortDir = -state.sortDir;
            } else {
                state.sortKey = key;
                state.sortDir = key === 'sort_time' ? -1 : 1;
            }
            render();
        });
    });

    tbody.addEventListener('click', function (event) {
        var titleEl = event.target.closest('.nb-row-title');
        if (titleEl) {
            // Обычный левый клик открывает статью в модалке (см. ниже) без
            // перехода со страницы - фильтры/поиск/скролл/дата остаются как
            // были. Ctrl/Shift/средний клик (event.metaKey - Cmd на Mac) не
            // трогаем - href на .nb-row-title остаётся настоящей ссылкой,
            // так что браузер сам откроет статью в новой вкладке/окне.
            if (event.ctrlKey || event.metaKey || event.shiftKey) return;
            event.preventDefault();
            openArticleModal(titleEl.dataset.id);
            return;
        }
        var descEl = event.target.closest('.nb-row-desc');
        if (descEl) {
            var id = descEl.dataset.id;
            state.expanded[id] = !state.expanded[id];
            descEl.classList.toggle('nb-expanded', !!state.expanded[id]);
            return;
        }
        var delBtn = event.target.closest('.nb-delete-btn');
        if (delBtn) {
            var newsId = delBtn.dataset.id;
            if (!confirm(TXT[40] + newsId + '?')) return;
            showLoading();
            fetch(window.NEWS_BOARD_DELETE_URL.replace(/0$/, newsId), {
                method: 'POST', headers: {'X-Requested-With': 'XMLHttpRequest'}
            }).then(function (r) { return r.json(); }).then(function (json) {
                hideLoading();
                if (json.redirect) { window.location = json.redirect; return; }
                if (json.error) { alert(TXT[41] + json.error); return; }
                state.rows = state.rows.filter(function (r) { return String(r.id) !== String(newsId); });
                render();
            }).catch(function () { hideLoading(); });
        }
    });

    // ── модальное окно новости (замена перехода на страницу /new/) ──
    // main_ohi_web.py:api_new_board оборачивает ту же new.py:prepare_form,
    // что и страница /new/, в JSON - вся логика (перевод через ChatGPT,
    // сохранение, восстановление несохранённых правок, дозагрузка статьи с
    // сайта) работает без переписывания, здесь только тонкий UI поверх неё.
    var modalEl = document.querySelector('#nbm_modal');
    var nbModal = window.bootstrap ? new bootstrap.Modal(modalEl) : null;
    // theme_switch.js обновляет эмодзи только у тулбарной #theme_toggle_btn -
    // у кнопки темы в модалке свой id, синхронизируем её отдельно.
    window.addEventListener('theme-changed', function (e) {
        var btn = document.querySelector('#nbm_theme_toggle_btn');
        if (btn) btn.textContent = e.detail.theme === 'black' ? '☀️' : '🌙';
    });
    var nbmLoading = document.querySelector('#nbm_loading');
    var nbmContent = document.querySelector('#nbm_content');
    var nbmId = document.querySelector('#nbm_id');
    var nbmSelectLang = document.querySelector('#nbm_select_lang');
    var nbmTranslateRu = document.querySelector('#nbm_translate_ru');
    var nbmTranslateEn = document.querySelector('#nbm_translate_en');
    var nbmTranslateHe = document.querySelector('#nbm_translate_he');
    var nbmNeedArticle = document.querySelector('#nbm_need_article');
    var nbmNameRss = document.querySelector('#nbm_name_rss');
    var nbmPublicDate = document.querySelector('#nbm_public_date');
    var nbmNameTheme = document.querySelector('#nbm_name_theme');
    var nbmTitle = document.querySelector('#nbm_title');
    var nbmDescription = document.querySelector('#nbm_description');
    var nbmUrl = document.querySelector('#nbm_url');
    var nbmMetaImg = document.querySelector('#nbm_meta_img');
    var nbmAuthorWrap = document.querySelector('#nbm_author_wrap');
    var nbmAuthor = document.querySelector('#nbm_author');
    var nbmFile = document.querySelector('#nbm_file');
    var nbmLang = document.querySelector('#nbm_lang');
    var nbmLoadFile = document.querySelector('#nbm_load_file');
    var nbmFull = document.querySelector('#nbm_full');
    var nbmRefresh = document.querySelector('#nbm_refresh');
    var nbmSave = document.querySelector('#nbm_save');

    var currentArticleId = null;
    var currentInit = {title: '', description: '', full: ''};

    function calcModalChange() {
        if (!window.NEWS_BOARD_ADMIN) return;
        var changed = nbmTitle.value.trim() !== currentInit.title.trim()
            || nbmDescription.value.trim() !== currentInit.description.trim()
            || nbmFull.value.trim() !== currentInit.full.trim();
        nbmRefresh.hidden = !changed;
        nbmSave.hidden = !changed;
    }

    // Отражает изменения (перевод/сохранение/дозагрузку) обратно в уже
    // загруженную таблицу - без этого пришлось бы перезапрашивать весь день,
    // чтобы увидеть свежий заголовок/описание после правки в модалке.
    function patchRowFromUnit(id, unit) {
        var row = state.rows.find(function (r) { return String(r.id) === String(id); });
        if (!row) return;
        ['ru', 'en', 'he'].forEach(function (l) {
            if (unit['title_' + l] !== undefined) row['title_' + l] = unit['title_' + l];
            if (unit['description_' + l] !== undefined) row['description_' + l] = unit['description_' + l];
        });
        row._haystack = [
            row.title_ru, row.title_en, row.title_he,
            row.description_ru, row.description_en, row.description_he,
            row.author, row.name_rss, row.themes, row.id
        ].join('   ').toLowerCase();
        render();
    }

    function fillArticleModal(data) {
        if (data.redirect) { window.location = data.redirect; return; }
        renderMessages(data.messages);
        currentArticleId = data.new_id;
        var unit = data.unit || {};
        var admin = !!data.admin;
        nbmId.textContent = '#' + unit.id;
        nbmSelectLang.innerHTML = (data.languages || []).map(function (l) {
            return '<option value="' + l + '"' + (l === data.select_lang ? ' selected' : '') + '>' + l + '</option>';
        }).join('');
        nbmTranslateRu.hidden = !(admin && unit.lang !== 'ru');
        nbmTranslateEn.hidden = !(admin && unit.lang !== 'en');
        nbmTranslateHe.hidden = !(admin && unit.lang !== 'he');
        nbmNeedArticle.hidden = !admin;
        nbmNameRss.textContent = unit.name_rss || '';
        nbmPublicDate.textContent = unit.public_date || '';
        nbmNameTheme.textContent = unit.name_theme || '';
        // Ручное растягивание (resize:vertical) браузер запоминает как
        // inline-стиль height прямо на <textarea> - без сброса поле
        // оставалось растянутым/суженным от ПРЕДЫДУЩЕЙ открытой новости
        // вместо стартовых 2/4 строк для новой.
        nbmTitle.style.height = '';
        nbmDescription.style.height = '';
        nbmTitle.value = unit.title || '';
        nbmDescription.value = unit.description || '';
        // Поле "Описание" выводится всегда, даже если оно пустое - иначе
        // в него было бы невозможно вставить текст вручную (админ), раз
        // поля с пустым описанием попросту не видно.
        nbmDescription.style.display = '';
        nbmFull.value = unit.full || '';
        nbmTitle.readOnly = !admin;
        nbmDescription.readOnly = !admin;
        nbmFull.readOnly = !admin;
        nbmUrl.href = unit.url || '#';
        if (unit.meta_img) { nbmMetaImg.src = unit.meta_img; nbmMetaImg.hidden = false; } else { nbmMetaImg.removeAttribute('src'); nbmMetaImg.hidden = true; }
        if (unit.author) { nbmAuthor.textContent = unit.author; nbmAuthorWrap.hidden = false; } else { nbmAuthorWrap.hidden = true; }
        nbmFile.textContent = unit.file != null ? unit.file : '';
        nbmLang.textContent = unit.lang || '';
        currentInit.title = unit.title_init != null ? unit.title_init : (unit.title || '');
        currentInit.description = unit.description_init != null ? unit.description_init : (unit.description || '');
        currentInit.full = unit.full_init != null ? unit.full_init : (unit.full || '');
        calcModalChange();
        nbmLoading.hidden = true;
        nbmContent.hidden = false;
        patchRowFromUnit(currentArticleId, unit);
    }

    function postArticleAction(extraFields) {
        showLoading();
        var body = new URLSearchParams();
        body.set('select_lang', nbmSelectLang.value);
        body.set('title', nbmTitle.value);
        body.set('description', nbmDescription.value);
        body.set('full', nbmFull.value);
        Object.keys(extraFields || {}).forEach(function (k) { body.set(k, extraFields[k]); });
        fetch(articleApiUrl(currentArticleId), {
            method: 'POST', body: body, headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).then(function (r) { return r.json(); }).then(function (json) {
            hideLoading();
            fillArticleModal(json);
        }).catch(function () { hideLoading(); });
    }

    function openArticleModal(id) {
        if (!nbModal) return;
        currentArticleId = id;
        nbmContent.hidden = true;
        nbmLoading.hidden = false;
        nbModal.show();
        fetch(articleApiUrl(id), {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (r) { return r.json(); })
            .then(fillArticleModal);
    }

    nbmSelectLang.addEventListener('change', function () { postArticleAction({}); });
    nbmTranslateRu.addEventListener('click', function () { postArticleAction({translate_ru: '1'}); });
    nbmTranslateEn.addEventListener('click', function () { postArticleAction({translate_en: '1'}); });
    nbmTranslateHe.addEventListener('click', function () { postArticleAction({translate_he: '1'}); });
    nbmNeedArticle.addEventListener('click', function () { postArticleAction({need_article: '1'}); });
    nbmLoadFile.addEventListener('click', function () { postArticleAction({load_file: '1'}); });
    nbmRefresh.addEventListener('click', function () { postArticleAction({refresh: '1'}); });
    nbmSave.addEventListener('click', function () { postArticleAction({save: '1'}); });
    [nbmTitle, nbmDescription, nbmFull].forEach(function (el) {
        el.addEventListener('input', calcModalChange);
    });

    // При закрытии модалки (без перехода со страницы) подсвечиваем и
    // прокручиваем к строке, из которой была открыта статья - так
    // пользователь сразу видит, где остановился (важно и для open_id, см.
    // applyOpenIdParam ниже - там таблица могла показывать не тот день, и
    // строка до подгрузки данных вообще не существовала в DOM).
    modalEl.addEventListener('hidden.bs.modal', function () {
        if (!currentArticleId) return;
        selectAndScroll(currentArticleId);
        currentArticleId = null;
    });

    // Подсветка новости при возврате из статьи, открытой в ОТДЕЛЬНОЙ вкладке
    // (Ctrl/средний клик в обход модалки) - new.py дописывает ?select_id=...
    // в кнопку "Назад" при back_to=news_board. Строку ищем с несколькими
    // попытками - на момент вызова render() ещё мог не успеть отрисоваться
    // tbody (маловероятно, но дёшево подстраховаться).
    function applyReturnHighlight() {
        var params = new URLSearchParams(window.location.search);
        var id = params.get('select_id');
        if (!id) return;
        params.delete('select_id');
        var query = params.toString();
        window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : ''));

        var tryHighlight = function (attemptsLeft) {
            var row = tbody.querySelector('tr[data-id="' + id + '"]');
            if (row) {
                selectAndScroll(id);
            } else if (attemptsLeft > 0) {
                setTimeout(function () { tryHighlight(attemptsLeft - 1); }, 150);
            }
        };
        tryHighlight(10);
    }

    // Открытие статьи модально сразу при заходе на страницу (?open_id=...) -
    // используется одноразовой ссылкой /one_new/<new_id>/ (main_ohi_web.py),
    // например из уведомления в чат-боте: вместо перехода на отдельную
    // страницу /new/ новость открывается тем же модальным окном, что и по
    // клику в списке, без потери фильтров/даты news_board.
    function applyOpenIdParam() {
        var params = new URLSearchParams(window.location.search);
        var id = params.get('open_id');
        if (!id) return;
        params.delete('open_id');
        var query = params.toString();
        window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : ''));

        // Таблица по умолчанию показывает сегодняшние сутки - новость из
        // ссылки может быть за любой день. Без подгрузки нужной даты строки
        // для неё вообще не будет в DOM, и после закрытия модалки
        // (selectAndScroll в hidden.bs.modal) позиционироваться было бы не
        // на что - тот же приём, что и в "Перейти к новости по ID" (gotoNewsId).
        var open = function () { setSelected(id); openArticleModal(id); };
        fetch(window.NEWS_BOARD_FIND_URL.replace(/0$/, id), {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (r) { return r.json(); })
            .then(function (json) {
                if (json.redirect) { window.location = json.redirect; return; }
                if (!json.found || dateInput.value === json.date) { open(); return; }
                loadDate(json.date, open);
            })
            .catch(open);
    }

    // Позиционирование на ранее выбранную новость (state.selectedId,
    // запомнена в localStorage) при обычном заходе на страницу - без этого
    // подсветка (rowHtml) была видна только если нужная новость случайно
    // попадала в сутки первой загрузки. Не вызывается вовсе, если открытие
    // страницы и так уже что-то позиционирует (select_id/open_id в URL) -
    // см. флаги ниже: applyReturnHighlight/applyOpenIdParam удаляют свой
    // параметр из URL СРАЗУ (до завершения своей, местами асинхронной,
    // работы), так что проверять window.location.search здесь было бы уже
    // поздно - к этому моменту параметра там не найти.
    function applySelectedOnLoad() {
        if (!state.selectedId) return;
        var row = tbody.querySelector('tr[data-id="' + state.selectedId + '"]');
        if (row) {
            row.scrollIntoView({block: 'center', behavior: 'smooth'});
        } else {
            gotoNewsId(state.selectedId, true);
        }
    }

    // ── старт ──
    var startParams = new URLSearchParams(window.location.search);
    var hadSelectId = !!startParams.get('select_id');
    var hadOpenId = !!startParams.get('open_id');
    setRows(window.NEWS_BOARD_INITIAL || []);
    applyReturnHighlight();
    applyOpenIdParam();
    if (!hadSelectId && !hadOpenId) applySelectedOnLoad();
})();
