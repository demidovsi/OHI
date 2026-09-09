// AJAX-форма "Гости": обновляет только фрагменты страницы (верхняя панель,
// таблица, пагинация) и перерисовывает диаграмму, вместо полной перезагрузки
// страницы на каждое действие (смена вкладки/дат/поиск/пагинация).

// menu2.html объявляет свой var loadingIcon раньше (до того, как #loadingIcon
// этой формы появится в DOM) - переобъявляем здесь же (не внутри замыкания),
// чтобы найти реальный элемент формы.
var loadingIcon = document.querySelector('#loadingIcon');

(function () {
    document.body.style.display = 'block';

    const GTXT = window.GUESTS_TXT || [];

    const form = document.forms['guests'];
    if (!form) {
        return;
    }

    const apiUrl = form.dataset.apiUrl;
    const scroller = document.querySelector('#table_wrap');
    const scrollInput = document.querySelector('#scroll');
    const viewModeInput = document.querySelector('#view_mode');
    const flashWrap = document.querySelector('.container-flash');

    let chart = null;
    let abortController = null;
    let lastChartJson = null;
    let lastChartTitle = '';
    let lastViewMode = null;

    function showLoading() {
        if (loadingIcon) loadingIcon.style.display = 'block';
    }

    function hideLoading() {
        if (loadingIcon) loadingIcon.style.display = 'none';
    }

    function renderMessages(messages) {
        if (!flashWrap) return;
        flashWrap.innerHTML = '';
        (messages || []).forEach(function (entry) {
            const category = entry[0];
            const text = entry[1];
            const div = document.createElement('div');
            div.className = 'alert alert-' + category;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'close';
            btn.setAttribute('data-dismiss', 'alert');
            btn.innerHTML = '&times;';
            div.appendChild(btn);
            div.appendChild(document.createTextNode(text));
            flashWrap.appendChild(div);
        });
    }

    function renderChart(chartJson, chartTitle, viewMode) {
        lastChartJson = chartJson;
        lastChartTitle = chartTitle;
        lastViewMode = viewMode;

        const titleEl = document.querySelector('#chartTitle');
        const wrapEl = document.querySelector('#chartWrap');

        if (chart) {
            chart.destroy();
            chart = null;
        }

        let cfg = null;
        try { cfg = JSON.parse(chartJson || '{}'); } catch (e) { cfg = null; }

        if (!cfg || !cfg.labels || !cfg.labels.length) {
            if (titleEl) titleEl.style.display = 'none';
            if (wrapEl) wrapEl.style.display = 'none';
            return;
        }

        if (titleEl) {
            titleEl.textContent = chartTitle || '';
            titleEl.style.display = '';
        }
        if (wrapEl) wrapEl.style.display = '';

        const ctx = document.querySelector('#mainChart');
        if (!ctx) return;
        const TC = getComputedStyle(document.body).color;

        if (viewMode === 'guests') {
            chart = new Chart(ctx, {
                type: 'pie',
                data: { labels: cfg.labels, datasets: cfg.datasets },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true, position: 'right',
                            labels: { color: TC, font: { size: 10 }, boxWidth: 12 }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (c) {
                                    const total = c.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                                    const pct = total > 0 ? (c.parsed * 100 / total).toFixed(1) : 0;
                                    return c.label + ': ' + c.parsed + ' (' + pct + '%)';
                                }
                            }
                        }
                    }
                }
            });
        } else {
            chart = new Chart(ctx, {
                type: 'bar',
                data: { labels: cfg.labels, datasets: cfg.datasets },
                options: {
                    indexAxis: 'y',
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function (c) {
                                    return ' ' + c.parsed.x.toLocaleString('ru') + ' ' + GTXT[17];
                                }
                            }
                        }
                    },
                    scales: {
                        x: { ticks: { color: TC, font: { size: 11 } }, beginAtZero: true },
                        y: {
                            ticks: {
                                color: TC, font: { size: 12 },
                                callback: function (val) {
                                    const lbl = this.getLabelForValue(val);
                                    return lbl.length > 30 ? lbl.slice(0, 28) + '…' : lbl;
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    function applyResponse(json) {
        if (json.redirect) {
            window.location = json.redirect;
            return;
        }
        renderMessages(json.messages);
        document.querySelector('#top_wrap').innerHTML = json.top_html;
        document.querySelector('#table_wrap').innerHTML = json.table_html;
        document.querySelector('#pages_wrap').innerHTML = json.pages_html;

        renderChart(json.chart_json, json.chart_title, json.view_mode);

        scrollInput.value = json.scroll || 0;
        if (scroller) scroller.scrollTop = json.scroll || 0;

        hideLoading();
    }

    function doFetch(submitter) {
        showLoading();
        if (abortController) abortController.abort();
        abortController = new AbortController();
        const fd = new FormData(form, submitter || null);
        fetch(apiUrl, {
            method: 'POST',
            body: fd,
            signal: abortController.signal,
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        })
            .then(function (r) { return r.json(); })
            .then(applyResponse)
            .catch(function (err) {
                if (err.name !== 'AbortError') {
                    hideLoading();
                }
            });
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        doFetch(event.submitter);
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('#btn_guests')) {
            viewModeInput.value = 'guests';
            form.requestSubmit();
        } else if (event.target.closest('#btn_pages')) {
            viewModeInput.value = 'pages';
            form.requestSubmit();
        }
    });

    document.addEventListener('change', function (event) {
        if (event.target.matches('#date_from, #date_to, #page_number')) {
            form.requestSubmit();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.target.matches('#search, #page_number') && event.key === 'Enter') {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    if (scroller) {
        scroller.addEventListener('scroll', function () {
            scrollInput.value = scroller.scrollTop;
        });
        scroller.scrollTop = parseInt(scrollInput.value || '0', 10);
    }

    // Chart.js рисует на canvas - var(--color-x) там не резолвится, поэтому
    // цвета легенды/осей не подстраивались бы под тему при мгновенном
    // переключении (static/js/theme_switch.js), только при обычной AJAX-
    // перезагрузке данных. Пересоздаём график с теми же данными, но
    // актуальными цветами по событию theme-changed.
    window.addEventListener('theme-changed', function () {
        renderChart(lastChartJson, lastChartTitle, lastViewMode);
    });

    renderChart(window.GUESTS_INITIAL_CHART_JSON, window.GUESTS_INITIAL_CHART_TITLE, viewModeInput.value);
})();
