// Мгновенное переключение цветовой темы - без submit формы и без
// перерисовки colors на сервере (порт того же механизма из проекта sozd_web,
// static/js/theme_switch.js). Подключается в base.html сразу после
// объявления choose_theme()/choose_language() и переопределяет choose_theme(),
// добавляя toggle_theme() для кнопки в include/select_language.html.
(function () {
    var THEME_KEY = 'ohi_web_theme';

    function applyTheme(theme) {
        document.body.dataset.theme = theme;
        // html - отдельно от body (фон html задаётся правилом
        // html[data-theme=...] в base.css, а не наследуется от
        // --color-background, объявленной только на body).
        document.documentElement.dataset.theme = theme;
        var hidden = document.querySelector('#select_theme_form');
        if (hidden) hidden.value = theme;
        updateToggleButton(theme);
    }

    function updateToggleButton(theme) {
        var btn = document.querySelector('#theme_toggle_btn');
        if (!btn) return;
        // Кнопка показывает эмодзи темы, В КОТОРУЮ переключит клик.
        btn.textContent = theme === 'black' ? '☀️' : '🌙';
    }

    function persistThemeServerSide(theme) {
        var userId = document.body.dataset.userId;
        if (!userId) return;
        var fd = new FormData();
        fd.append('select_theme_form', theme);
        // fire-and-forget (keepalive - чтобы запрос пережил уход со страницы),
        // синхронизирует upr['colors'] на сервере для следующего обычного
        // рендера (навигация, обновление страницы и т.п.).
        fetch('/api/set_theme/' + userId + '/', {method: 'POST', body: fd, keepalive: true}).catch(function () {});
    }

    window.choose_theme = function () {
        var hidden = document.querySelector('#select_theme_form');
        if (!hidden) return;
        applyTheme(hidden.value);
        localStorage.setItem(THEME_KEY, hidden.value);
        persistThemeServerSide(hidden.value);
        window.dispatchEvent(new CustomEvent('theme-changed', {detail: {theme: hidden.value}}));
    };

    window.toggle_theme = function () {
        var hidden = document.querySelector('#select_theme_form');
        if (!hidden) return;
        hidden.value = (hidden.value === 'black') ? 'white' : 'black';
        window.choose_theme();
    };

    var saved = localStorage.getItem(THEME_KEY);
    if (saved && saved !== document.body.dataset.theme) {
        applyTheme(saved);
    } else {
        updateToggleButton(document.body.dataset.theme);
    }
})();
