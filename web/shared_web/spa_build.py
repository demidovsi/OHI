"""Сборка SPA сайта при локальном запуске (PyCharm: Run → start_<сайт>.py; python start_<сайт>.py).

Flask раздаёт собранный интерфейс frontend/dist. Чтобы локально не помнить про `npm run build`, точка входа
сайта перед app.run() вызывает `ensure_built(папка сайта)`: если сборки нет или исходники новее неё
(frontend/src, общие страницы shared_web/frontend, index.html, package.json, vite.config.ts) — запускается
`npm run build` (при отсутствии node_modules — сначала `npm ci`). В Cloud Run не вызывается: SPA собирает
первая стадия Dockerfile.

Отключить: переменная окружения SPA_BUILD=0 (например, когда фронтенд открыт через `npm run dev`).
"""
import os
import shutil
import subprocess

SHARED_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
_SKIP_DIRS = {'node_modules', 'dist', '.vite'}


def _newest_mtime(path: str) -> float:
    if os.path.isfile(path):
        return os.path.getmtime(path)
    newest = 0.0
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            newest = max(newest, os.path.getmtime(os.path.join(base, name)))
    return newest


def ensure_built(app_dir: str) -> None:
    """Пересобрать <app_dir>/frontend/dist, если он устарел. Ошибки сборки — предупреждение, сайт стартует."""
    if os.environ.get('SPA_BUILD', '1') == '0':
        return
    frontend = os.path.join(app_dir, 'frontend')
    index = os.path.join(frontend, 'dist', 'index.html')
    sources = [os.path.join(frontend, name) for name in ('src', 'index.html', 'package.json', 'vite.config.ts')]
    sources.append(SHARED_FRONTEND)
    built = os.path.getmtime(index) if os.path.isfile(index) else 0.0
    if built and built >= max(_newest_mtime(p) for p in sources if os.path.exists(p)):
        return
    npm = shutil.which('npm')
    if not npm:
        print('WARNING: npm не найден (нужен Node 20.19+) — интерфейс frontend/dist не пересобран', flush=True)
        return
    steps = [] if os.path.isdir(os.path.join(frontend, 'node_modules')) else [[npm, 'ci', '--no-audit', '--no-fund']]
    steps.append([npm, 'run', 'build'])
    for cmd in steps:
        print(f"SPA: {' '.join(cmd[1:])} ({frontend})", flush=True)
        if subprocess.run(cmd, cwd=frontend).returncode:
            print('WARNING: сборка SPA не удалась — сайт отдаёт прежний frontend/dist', flush=True)
            return
