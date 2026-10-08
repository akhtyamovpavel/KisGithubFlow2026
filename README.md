# KisGithubFlow2026

Мини-маркетплейс объявлений с фотографиями, категориями, поиском и модерацией перед публикацией. Backend использует FastAPI, frontend разрабатывается на Vite.

## Запускаем frontend

Для frontend используем Node.js 22 и npm. Команды выполняем из каталога `frontend`:

```bash
npm ci
npm run dev
```

Vite запускает интерфейс по адресу <http://localhost:5173>. Базовый адрес backend задаёт переменная `VITE_API_URL`. Если переменная не задана, frontend обращается к `http://localhost:8000`. Для локальной настройки создаём `frontend/.env.local`:

```dotenv
VITE_API_URL=http://localhost:8000
```

Сборка frontend:

```bash
npm run build
```

## Запускаем backend

Используем Python 3.12 или новее и [uv](https://docs.astral.sh/uv/getting-started/installation/). Команды выполняем из корня репозитория.

Устанавливаем зависимости из lock-файла:

```bash
uv sync --project backend --frozen
```

Запускаем сервер с автоматической перезагрузкой:

```bash
uv run --project backend --frozen uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Проверяем сервис по адресу <http://127.0.0.1:8000/health>. Ответ `{"status":"ok"}` означает, что приложение отвечает на HTTP-запросы. Документация OpenAPI доступна на <http://127.0.0.1:8000/docs>, схема на <http://127.0.0.1:8000/openapi.json>.

## Настраиваем окружение

Копируем пример настроек:

```bash
cp backend/.env.example backend/.env
```

Переменная `MARKETPLACE_APP_NAME` задаёт название API. Переменная `MARKETPLACE_CORS_ORIGINS` содержит JSON-массив разрешённых адресов frontend. По умолчанию разрешены `http://localhost:5173` и `http://127.0.0.1:5173`. При изменении порта Vite добавляем полный адрес с портом в список.

Переменная `MARKETPLACE_DATABASE_URL` задаёт адрес базы данных. По умолчанию используется SQLite в `backend/marketplace.db`. Создаём схему и применяем обновления командой `uv run --project backend --frozen alembic -c backend/alembic.ini upgrade head`. Версию схемы смотрим командой `uv run --project backend --frozen alembic -c backend/alembic.ini current`.

После применения миграций загружаем начальные категории командой `uv run --project backend --frozen --directory backend python -m app.seed_categories`. Команду можно запускать повторно: существующие категории не дублируются. Активные категории API возвращает по адресу `/categories` в алфавитном порядке. Объявления с отсутствующей категорией блокирует внешний ключ базы данных.

Настройки процесса имеют приоритет над `backend/.env`. Файл окружения ищется относительно каталога backend, независимо от рабочей директории. После изменения настроек перезапускаем сервер. Файлы `.env` и виртуальное окружение исключены из Git, секреты передаём через окружение.

## Регистрируемся и входим

Для подписи access-токенов задаём `MARKETPLACE_AUTH_SECRET_KEY`. Создаём значение командой `openssl rand -hex 32` и сохраняем его в `backend/.env`; секрет должен содержать не меньше 32 символов. Время жизни токена задаёт `MARKETPLACE_AUTH_ACCESS_TOKEN_TTL_MINUTES`, по умолчанию 30 минут.

Отправляем `POST /auth/register` с полями `email`, `display_name` и `password`. Пароль должен содержать от 12 до 128 символов. Публичная регистрация всегда создаёт пользователя с ролью `user`; повторный email возвращает HTTP 409. Пароль хранится как хеш Argon2id.

Входим через `POST /auth/login` с полями `email` и `password`. Ответ содержит bearer access-токен. Запрос `GET /auth/me` требует заголовок `Authorization: Bearer <токен>` и возвращает текущего пользователя. Неверный, просроченный или отсутствующий токен возвращает HTTP 401. Зависимость `ModeratorUser` закрывает операции для роли `moderator` и возвращает HTTP 403 для обычного пользователя.

Первого модератора создаём отдельной командой. Заполняем в `backend/.env` переменные `MARKETPLACE_MODERATOR_EMAIL`, `MARKETPLACE_MODERATOR_DISPLAY_NAME` и `MARKETPLACE_MODERATOR_PASSWORD`, затем запускаем `uv run --project backend --frozen --directory backend python -m app.create_moderator`. Пароль команды проходит ту же проверку длины и сохраняется в виде хеша.

Используем [настройки FastAPI](https://fastapi.tiangolo.com/advanced/settings/) и [CORSMiddleware](https://fastapi.tiangolo.com/tutorial/cors/). CORS разрешает запросы браузера с указанных адресов и не заменяет авторизацию API.

## Проверяем backend

```bash
uv run --project backend --frozen pytest backend/tests
uv run --project backend --frozen ruff check backend
```

Проверки охватывают `/health`, OpenAPI, разрешённые и запрещённые источники CORS, чтение настроек и приоритет переменных окружения.

## Работаем по GitHub Flow

Берём задачу из [плана MVP 1.0](https://github.com/akhtyamovpavel/KisGithubFlow2026/issues). Создаём ветку `feat/<номер-issue>-<english-name>` от актуального `main`. В PR указываем `Closes #<номер>` и результаты проверки. После ревью другим участником и успешного CI teamlead объединяет изменения с `main`.
