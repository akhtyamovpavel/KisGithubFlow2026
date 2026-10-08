# KisGithubFlow2026

Мини-маркетплейс объявлений с фотографиями, категориями, поиском и модерацией перед публикацией. Backend использует FastAPI, frontend разрабатывается на Vite.

## Запускаем backend

Используем Python 3.12 или новее и [uv](https://docs.astral.sh/uv/getting-started/installation/). Все команды выполняем из корня репозитория.

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

Настройки процесса имеют приоритет над `backend/.env`. Файл окружения ищется относительно каталога backend, независимо от рабочей директории. После изменения настроек перезапускаем сервер. Файлы `.env` и виртуальное окружение исключены из Git, секреты передаём через окружение.

Используем [настройки FastAPI](https://fastapi.tiangolo.com/advanced/settings/) и [CORSMiddleware](https://fastapi.tiangolo.com/tutorial/cors/). CORS разрешает запросы браузера с указанных адресов и не заменяет авторизацию API.

## Проверяем backend

```bash
uv run --project backend --frozen pytest backend/tests
uv run --project backend --frozen ruff check backend
```

Проверки охватывают `/health`, OpenAPI, разрешённые и запрещённые источники CORS, чтение настроек и приоритет переменных окружения.

## Работаем по GitHub Flow

Берём задачу из [плана MVP 1.0](https://github.com/akhtyamovpavel/KisGithubFlow2026/issues). Создаём ветку `feat/<номер-issue>-<english-name>` от актуального `main`. В PR указываем `Closes #<номер>` и результаты проверки. После ревью другим участником и успешного CI teamlead объединяет изменения с `main`.
