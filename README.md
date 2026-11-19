# Настольные игры

Локальный сайт: каталог 26 самых популярных настольных игр (без нард), 17 из них можно играть прямо на сайте (включая дженгу), и помощник за столом для остальных.
Интерфейс на русском и английском, светлая и тёмная тема.

## Запуск

```
pip install -r requirements.txt
python app.py
```

Локально откройте http://127.0.0.1:5000

База SQLite (`games.db`) создаётся и заполняется при первом запуске. Старая база обновляется автоматически: убираются непопулярные игры из прежнего каталога, избранное, оценки и свои игры сохраняются. Убранные игры можно добавить обратно через форму «Добавить игру». Чтобы вернуть исходный каталог, остановите сервер и удалите `games.db`.

## Развёртывание на сервере

Нужен Linux-сервер с открытыми портами 80 и 443 и доменом, указывающим на него.

**Вариант 1: Docker Compose (проще всего)**

```
scp boardgames.zip user@server:~ && ssh user@server
unzip boardgames.zip && cd boardgames
docker compose up -d --build
```

Сайт запустится на порту 8080 (`PORT=80 docker compose up -d` для другого порта). База лежит в томе `boardgames-data` и переживает перезапуски и обновления. Обновление: распаковать новую версию и снова `docker compose up -d --build`.

**Вариант 2: systemd + nginx без Docker**

```
sudo mkdir -p /opt/boardgames && sudo cp -r . /opt/boardgames && cd /opt/boardgames
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo cp deploy/boardgames.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now boardgames
sudo cp deploy/nginx-systemd.conf /etc/nginx/sites-available/boardgames   # замените example.com
sudo ln -s /etc/nginx/sites-available/boardgames /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx
```

**HTTPS:** `sudo certbot --nginx -d ваш-домен`. Для варианта с Docker используйте `deploy/nginx.conf` как прокси на порт 8080.

Проверка работы: `curl http://localhost:8080/health` вернёт `{"status":"ok"}`.
Резервная копия: скопируйте файл `games.db` (в Docker: `docker compose cp web:/data/games.db .`).

Переменные окружения: `DB_PATH` (путь к базе), `PORT` (порт Docker Compose), `BIND` и `WEB_CONCURRENCY` (адрес и число процессов gunicorn).

## Что внутри

- Каталог: поиск, фильтры (жанр, число игроков, длительность, избранное, «можно сыграть здесь»), сортировка, добавление, редактирование и удаление игр, избранное и оценки 1–5.
- Играть, для двоих (с компьютером на 3 уровнях или вдвоём): шахматы, го 9×9, шашки, реверси, четыре в ряд, крестики-нолики.
- Играть, компанией: шпион (темы слов и своя тема), элиас, кодовые имена, мафия, рисуем и угадываем, змеи и лестницы, лудо, дженга (башня с физикой устойчивости, можно с компьютерами).
- Играть, против компьютера: мастермайнд, морской бой, домино.
- Помощник за столом: для игр, которым нужны физические компоненты, открываются правила, кубики, монетка, случайный первый игрок, таймер и счёт.
- Инструменты: таймер и счётчик очков.

## Современные стандарты

- Мобильная вёрстка включается автоматически по ширине экрана и типу устройства: нижняя панель вкладок, диалоги-шторки, крупные зоны нажатия, отступы под вырезы экрана.
- Дизайн: шрифты Unbounded и Onest лежат в `static/fonts` (работают без интернета), светлая и тёмная темы, адаптивная вёрстка, цветные карточки по жанрам.
- Приложение устанавливается как PWA (манифест, иконки) и открывается офлайн благодаря service worker.
- Доступность: ссылка «К содержимому», `aria-current`, видимый фокус, уважение `prefers-reduced-motion`.
- Безопасность: заголовки CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.

## Структура

- `app.py` — Flask и API (`/api/games`, `/health`), `seed.py` — стартовый каталог
- `wsgi.py`, `gunicorn.conf.py`, `Dockerfile`, `docker-compose.yml`, `deploy/` — запуск на сервере
- `static/` — фронтенд на HTML, CSS и JS без сборки
- `static/js/games/` — игры, `static/js/ai.js` — компьютерный соперник, `static/js/words.js` — слова для шпиона, элиаса и других
