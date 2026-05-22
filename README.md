# Changelog API

`Changelog API` это сервис на `FastAPI` + `ClickHouse` для хранения снапшотов задач из MS Project, расчета дельт между версиями плана и ведения журнала изменений.

Сервис рассчитан на сценарий, где внешний клиент:
- отправляет снапшот задач проекта;
- получает изменения между версиями;
- сохраняет классифицированный журнал изменений;
- сохраняет стратегические отклонения от baseline.

## Возможности

- хранение снапшотов проекта с автоматическим версионированием;
- расчет `added / removed / changed` между версиями;
- хранение журнала изменений `change_log`;
- обновление статуса записи через `ReplacingMergeTree`;
- хранение стратегических отклонений `strategic_control`;
- хранение метаданных проекта `project_meta`;
- справочник кодов классификатора;
- аутентификация через заголовок `X-Api-Key`.

## Стек

- `FastAPI`
- `Uvicorn`
- `ClickHouse`
- `Docker Compose`
- `Pytest`

## Структура проекта

```text
changelog-api/
├── .github/
│   └── workflows/
│       └── deploy.yml
├── api/
│   ├── app/
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── logic.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── repository.py
│   ├── tests/
│   │   └── test_api.py
│   ├── Dockerfile
│   └── requirements.txt
├── clickhouse-config/
│   └── memory_config.xml
├── clickhouse-init/
│   └── 01_create_tables.sql
├── .env.example
├── docker-compose.yml
└── README.md
```

## API

Базовый путь:

```text
/api/v1
```

Эндпоинты:

- `GET /api/v1/health`
- `POST /api/v1/snapshot`
- `GET /api/v1/snapshot/{project_name}/latest`
- `GET /api/v1/snapshot/{project_name}/{version}`
- `GET /api/v1/deltas/{project_name}/{v_from}/{v_to}`
- `POST /api/v1/changelog`
- `PATCH /api/v1/changelog/{project_name}/{log_id}/status`
- `GET /api/v1/changelog/{project_name}`
- `POST /api/v1/strategic`
- `GET /api/v1/strategic/{project_name}`
- `GET /api/v1/meta/{project_name}`
- `GET /api/v1/classifier`

Все эндпоинты, кроме `health`, требуют заголовок:

```text
X-Api-Key: your-api-key
```

## База данных

При первом запуске создаются таблицы:

- `snapshots`
- `strategic_control`
- `change_log`
- `classifier`
- `project_meta`

Схема базы находится в [clickhouse-init/01_create_tables.sql](/D:/Ruslan/python_projects/changelog-api/clickhouse-init/01_create_tables.sql).

## Быстрый старт через Docker

1. Скопируйте файл окружения:

```powershell
Copy-Item .env.example .env
```

2. Заполните `.env`:

```env
CH_USER=changelog
CH_PASSWORD=your-secure-password
API_PORT=8000
API_KEY=your-api-key-minimum-32-characters
```

3. Запустите сервисы:

```powershell
docker compose up -d --build
```

4. Проверьте здоровье API:

```powershell
curl http://localhost:8000/api/v1/health
```

## Локальный запуск API без Docker

Если хотите запускать только приложение локально:

1. Перейдите в каталог `api`.
2. Установите зависимости из `requirements.txt`.
3. Убедитесь, что ClickHouse доступен и переменные окружения заданы.
4. Запустите:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Пример запроса

Сохранение снапшота:

```bash
curl -X POST "http://localhost:8000/api/v1/snapshot" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-api-key" \
  -d '{
    "project_name": "Пилот-2026",
    "status_date": "2026-02-01",
    "rows": [
      {
        "UID": 1,
        "ID": 1,
        "WBS": "1",
        "Name": "Подготовительный этап",
        "Level": 1,
        "Outline": "1",
        "Parent_UID": 0,
        "Summary": "Y",
        "Milestone": "N",
        "Start": "2025-09-01",
        "Finish": "2026-03-01",
        "Baseline_Start": "2025-09-01",
        "Baseline_Finish": "2026-02-15",
        "Duration": "130d",
        "Pct_Complete": 45,
        "Actual_Start": "2025-09-01",
        "Actual_Finish": null,
        "Cost": 0,
        "Baseline_Cost": 0,
        "Work": 0,
        "Baseline_Work": 0,
        "Predecessors": "",
        "Resources": "Иванов И.И.",
        "Notes": ""
      }
    ]
  }'
```

## Тесты

Тесты находятся в [api/tests/test_api.py](/D:/Ruslan/python_projects/changelog-api/api/tests/test_api.py).

Пример запуска:

```powershell
cd api
pytest
```

## Деплой

Для базового деплоя добавлен workflow:

- [.github/workflows/deploy.yml](/D:/Ruslan/python_projects/changelog-api/.github/workflows/deploy.yml)

Он предполагает:

- push в ветку `main`;
- подключение к VM по SSH;
- `docker compose up -d --build` на сервере.

## Примечания

- `ClickHouse` не публикуется наружу, доступ идет только внутри docker-сети.
- Для чтения из таблиц с `ReplacingMergeTree` используется `FINAL`.
- Для строковых значений в SQL реализовано экранирование одинарных кавычек и обратных слешей.
- Для nullable дат обрабатываются пустые и служебные значения вроде `null`, `None`, `NA`, `1970-01-01`.
