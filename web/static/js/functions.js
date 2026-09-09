// AJAX-форма "Параметры функций": обновляет только таблицу и список функций
// в диалоге "Новый параметр", вместо полной перезагрузки страницы на каждое
// действие (сохранение/удаление строки, создание функции/параметра, refresh).

// menu2.html объявляет свой var loadingIcon раньше (до того, как #loadingIcon
// этой формы появится в DOM) - переобъявляем здесь же (не внутри замыкания),
// чтобы найти реальный элемент формы.
var loadingIcon = document.querySelector('#loadingIcon');

(function () {
    document.body.style.display = 'block';

    const TXT = window.FUNCTIONS_TXT || [];

    const form = document.forms['functions'];
    if (!form) {
        return;
    }

    const apiUrl = form.dataset.apiUrl;
    const scroller = document.querySelector('.bottom');
    const scrollInput = document.querySelector('#scroll');
    const table = document.querySelector('#lawsTable');
    const flashWrap = document.querySelector('.container-flash');

    const dlgNewFunction = document.querySelector('#dlg_new_function');
    const dlgNewParameter = document.querySelector('#dlg_new_parameter');
    const nameFunctionInput = document.querySelector('#name_function');
    const descriptionFunctionInput = document.querySelector('#description_function');
    const btnCreateFunction = document.querySelector('#btn_create_function');
    const dlgSelectFunction = document.querySelector('#dlg_select_function');
    const dlgCodeParameter = document.querySelector('#dlg_code_parameter');
    const dlgCommentParameter = document.querySelector('#dlg_comment_parameter');
    const dlgIsNumberParameter = document.querySelector('#dlg_is_number_parameter');
    const btnSaveParameter = document.querySelector('#btn_save_parameter');

    let existingIdents = new Set(window.FUNCTIONS_EXISTING_IDENTS || []);
    let abortController = null;

    function showLoading() {
        if (loadingIcon) loadingIcon.style.display = 'block';
    }

    function hideLoading() {
        if (loadingIcon) loadingIcon.style.display = 'none';
    }

    // ── Отслеживание несохранённых правок в таблице (делегирование, переживает замену #table_body) ──

    function isInputChanged(input) {
        if (input.type === 'checkbox') {
            return (input.checked ? '1' : '0') !== input.dataset.original;
        }
        return input.value !== input.dataset.original;
    }

    // 'input[data-original]' и 'textarea[data-original]' вместе - sh_name
    // (Комментарий, functions_table.html) - <textarea> (перенос длинного
    // текста на несколько строк), но отслеживание изменений/восстановления
    // должно работать одинаково для обоих.
    var editableSelector = 'input[data-original], textarea[data-original]';

    function hasUnsavedChanges() {
        var changed = false;
        table.querySelectorAll(editableSelector).forEach(function (input) {
            if (isInputChanged(input)) changed = true;
        });
        return changed;
    }

    function updateRowActions(row) {
        if (!row) return;
        var changed = false;
        row.querySelectorAll(editableSelector).forEach(function (input) {
            if (isInputChanged(input)) changed = true;
        });
        var saveBtn = row.querySelector('.row-save');
        var restoreBtn = row.querySelector('.row-restore');
        if (saveBtn) saveBtn.style.display = changed ? '' : 'none';
        if (restoreBtn) restoreBtn.style.display = changed ? '' : 'none';
        updateGlobalActions();
    }

    function updateGlobalActions() {
        var anyChanged = hasUnsavedChanges();
        document.querySelector('#save_all').style.display = anyChanged ? '' : 'none';
        document.querySelector('#refresh_all').style.display = anyChanged ? '' : 'none';
    }

    // Поле "Значение" (.val-input) - <input type="number"> для числовых
    // параметров, <textarea> для текстовых. Это разные DOM-элементы (не
    // просто смена .type у одного input), поэтому при переключении чекбокса
    // "Число" элемент приходится пересоздавать, перенося name/value/
    // data-original/style.
    function setValueInputType(row, isNumber) {
        var oldEl = row.querySelector('.val-input');
        if (!oldEl) return;
        var wantsTextarea = !isNumber;
        var isTextarea = oldEl.tagName === 'TEXTAREA';
        var title = isNumber ? TXT[24] : TXT[25];
        if (isTextarea === wantsTextarea) {
            // Уже нужный тип элемента - для input ещё поправить сам type.
            if (!wantsTextarea) oldEl.type = 'number';
            oldEl.title = title;
            return;
        }
        var newEl = document.createElement(wantsTextarea ? 'textarea' : 'input');
        newEl.className = oldEl.className;
        newEl.name = oldEl.name;
        newEl.style.cssText = oldEl.style.cssText;
        newEl.dataset.original = oldEl.dataset.original;
        newEl.title = title;
        newEl.value = oldEl.value;
        if (!wantsTextarea) {
            newEl.type = 'number';
            newEl.setAttribute('onkeydown', "return event.key != 'Enter';");
        }
        oldEl.replaceWith(newEl);
    }

    function restoreRowInputs(row) {
        // Сначала все значения (включая .checked чекбокса), и только потом
        // тип поля "Значение" по уже восстановленному чекбоксу - НЕ полагаясь
        // на порядок обхода (setValueInputType читает .value старого
        // элемента - валиден только если чекбокс успел восстановиться раньше).
        row.querySelectorAll(editableSelector).forEach(function (input) {
            if (input.type === 'checkbox') {
                input.checked = input.dataset.original === '1';
            } else {
                input.value = input.dataset.original;
            }
        });
        var checkbox = row.querySelector('input[type="checkbox"][data-original]');
        if (checkbox) setValueInputType(row, checkbox.checked);
    }

    window.restoreRow = function (btn) {
        var row = btn.closest('tr[data-row-id]');
        if (!row) return;
        restoreRowInputs(row);
        updateRowActions(row);
    };

    window.restoreAll = function () {
        table.querySelectorAll('tbody tr[data-row-id]').forEach(function (row) {
            restoreRowInputs(row);
            var saveBtn = row.querySelector('.row-save');
            var restoreBtn = row.querySelector('.row-restore');
            if (saveBtn) saveBtn.style.display = 'none';
            if (restoreBtn) restoreBtn.style.display = 'none';
        });
        updateGlobalActions();
    };

    table.addEventListener('input', function (event) {
        if (event.target.matches('input[data-original]:not([type="checkbox"]), textarea[data-original]')) {
            updateRowActions(event.target.closest('tr[data-row-id]'));
        }
    });

    table.addEventListener('change', function (event) {
        var input = event.target;
        if (!input.matches('input[type="checkbox"][data-original]')) return;
        var row = input.closest('tr[data-row-id]');
        var valInput = row.querySelector('.val-input');
        if (valInput) {
            if (input.checked && valInput.value !== '' && isNaN(Number(valInput.value))) {
                alert(TXT[51] + valInput.value + TXT[52]);
                input.checked = false;
                return;
            }
            setValueInputType(row, input.checked);
        }
        updateRowActions(row);
    });

    // ── Диалог "Новая функция" ──

    document.querySelector('#btn_open_new_function').addEventListener('click', function () {
        dlgNewFunction.showModal();
    });
    document.querySelector('#btn_cancel_new_function').addEventListener('click', function () {
        dlgNewFunction.close();
    });

    function updateCreateFunctionButton() {
        var val = nameFunctionInput.value.trim();
        var exists = existingIdents.has(val);
        var enabled = val !== '' && !exists;
        btnCreateFunction.disabled = !enabled;
        btnCreateFunction.style.opacity = enabled ? '1' : '0.4';
        nameFunctionInput.style.color = exists ? 'red' : '';
    }
    nameFunctionInput.addEventListener('input', updateCreateFunctionButton);
    // Кнопка "Сохранить" в разметке всегда disabled по умолчанию - верно
    // для обычного пустого поля, но name_function хранится в сессии
    // (array_default в functions.py) и может прийти уже заполненным при
    // обычной перезагрузке страницы (ушёл не сохранив, вернулся) - тогда
    // без этого вызова кнопка осталась бы залипшей disabled, пока
    // пользователь не тронет поле вручную.
    updateCreateFunctionButton();

    // ── Диалог "Новый параметр" ──

    document.querySelector('#btn_open_new_parameter').addEventListener('click', function () {
        dlgNewParameter.showModal();
    });
    document.querySelector('#btn_cancel_new_parameter').addEventListener('click', function () {
        dlgNewParameter.close();
    });

    function updateSaveParameterButton() {
        var enabled = dlgCodeParameter.value.trim() !== '' && dlgSelectFunction.value !== '0';
        btnSaveParameter.disabled = !enabled;
        btnSaveParameter.style.opacity = enabled ? '1' : '0.4';
    }
    dlgCodeParameter.addEventListener('input', updateSaveParameterButton);
    dlgSelectFunction.addEventListener('change', updateSaveParameterButton);

    function resetNewParameterDialog() {
        dlgCodeParameter.value = '';
        dlgCommentParameter.value = '';
        dlgIsNumberParameter.checked = false;
        dlgSelectFunction.value = '0';
        updateSaveParameterButton();
    }

    // ── Флеш-сообщения (та же разметка, что и .container-flash в base.html) ──

    function renderMessages(messages) {
        if (!flashWrap) return;
        flashWrap.innerHTML = '';
        (messages || []).forEach(function (entry) {
            var category = entry[0];
            var text = entry[1];
            var div = document.createElement('div');
            div.className = 'alert alert-' + category;
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'close';
            btn.setAttribute('data-dismiss', 'alert');
            btn.innerHTML = '&times;';
            div.appendChild(btn);
            div.appendChild(document.createTextNode(text));
            flashWrap.appendChild(div);
        });
    }

    // ── AJAX submit ──

    function applyResponse(json, submitterName) {
        if (json.redirect) {
            window.location = json.redirect;
            return;
        }

        document.querySelector('#table_body').innerHTML = json.table_html;
        dlgSelectFunction.innerHTML = json.options_html;
        existingIdents = new Set(json.existing_idents || []);

        var hadWarning = (json.messages || []).some(function (m) { return m[0] === 'warning'; });
        renderMessages(json.messages);

        if (submitterName === 'create_function' && !hadWarning) {
            dlgNewFunction.close();
        }
        nameFunctionInput.value = json.name_function || '';
        descriptionFunctionInput.value = json.description_function || '';
        updateCreateFunctionButton();

        if (submitterName === 'create_parameter' && !hadWarning) {
            dlgNewParameter.close();
            resetNewParameterDialog();
        } else {
            updateSaveParameterButton();
        }

        updateGlobalActions();

        scrollInput.value = json.scroll || 0;
        if (scroller) scroller.scrollTop = json.scroll || 0;

        hideLoading();
    }

    function doFetch(submitter) {
        showLoading();
        if (abortController) abortController.abort();
        abortController = new AbortController();
        const fd = new FormData(form, submitter || null);
        const submitterName = submitter ? submitter.name : null;
        fetch(apiUrl, {
            method: 'POST',
            body: fd,
            signal: abortController.signal,
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        })
            .then(function (r) { return r.json(); })
            .then(function (json) { applyResponse(json, submitterName); })
            .catch(function (err) {
                if (err.name !== 'AbortError') {
                    hideLoading();
                }
            });
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        var submitterName = event.submitter ? event.submitter.name : '';
        if (submitterName === 'refresh' && hasUnsavedChanges()) {
            if (!confirm(TXT[53])) {
                return;
            }
        }
        // Подтверждение удаления - раньше было в разметке (onclick="return
        // confirm('...')" в functions_table.html), с переведённым текстом
        // внутри так рискованно: Jinja экранирует апостроф в '&#39;', браузер
        // при разборе HTML-атрибута декодирует его обратно в ' ДО того, как
        // JS разберёт строку - переведённый текст с апострофом (например
        // английское "it's") преждевременно закрыл бы строковый литерал.
        // Здесь же - обычная конкатенация JS-строк, без этого риска.
        if (submitterName.indexOf('delete_function_') === 0) {
            if (!confirm(TXT[45] + '?')) return;
        } else if (submitterName.indexOf('delete_parameter_') === 0) {
            var id = submitterName.slice('delete_parameter_'.length);
            var code = event.submitter.dataset.code || '';
            if (!confirm(TXT[49] + id + TXT[54] + code + ']?')) return;
        }
        doFetch(event.submitter);
    });

    document.querySelector('#refresh_all').addEventListener('click', function () {
        window.restoreAll();
    });

    if (scroller) {
        scroller.addEventListener('scroll', function () {
            scrollInput.value = scroller.scrollTop;
        });
        scroller.scrollTop = parseInt(scrollInput.value || '0', 10);
    }
})();
