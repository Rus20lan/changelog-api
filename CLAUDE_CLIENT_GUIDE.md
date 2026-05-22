# Короткая инструкция для клиента / Claude

## База

- Base URL: `https://api.cadkocomatozze.ru/api/v1`
- Все запросы, кроме `GET /health`, требуют заголовок:

```text
X-Api-Key: YOUR_API_KEY
```

## Быстрая проверка

Проверить, что API жив:

```bash
curl https://api.cadkocomatozze.ru/api/v1/health
```

Проверить, что ключ работает:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  https://api.cadkocomatozze.ru/api/v1/classifier
```

## Рабочий сценарий

### 1. Сохранить новый снапшот

```bash
curl -X POST "https://api.cadkocomatozze.ru/api/v1/snapshot" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d @snapshot_payload.json
```

Смотрите в ответе:

- `version`
- `has_previous`

### 2. Если это не первая версия, запросить дельты

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/deltas/PROJECT_NAME/PREV_VERSION/CURR_VERSION"
```

В ответе будут:

- `added`
- `removed`
- `changed`

### 3. Классифицировать изменения на стороне клиента

Для каждого изменения определить:

- `category_code`
- `technical_summary`
- `impact_type`
- `confidence`
- `status`

### 4. Сохранить журнал изменений

```bash
curl -X POST "https://api.cadkocomatozze.ru/api/v1/changelog" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d @changelog_payload.json
```

### 5. Сохранить стратегические отклонения

```bash
curl -X POST "https://api.cadkocomatozze.ru/api/v1/strategic" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d @strategic_payload.json
```

### 6. Если эксперт исправил причину, обновить статус записи

```bash
curl -X PATCH "https://api.cadkocomatozze.ru/api/v1/changelog/PROJECT_NAME/LOG_ID/status" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "new_status": "Corrected",
    "category_code": "DELAY-INT",
    "expert_comment": "Уточнение после проверки"
  }'
```

## Полезные чтения

Последняя версия проекта:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/snapshot/PROJECT_NAME/latest"
```

Журнал изменений:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/changelog/PROJECT_NAME"
```

Стратегические отклонения:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/strategic/PROJECT_NAME"
```

## Разрешённые коды причин

```text
OPT-TECH
OPT-RES
OPT-SCOPE
DELAY-EXT
DELAY-INT
DELAY-TECH
SCOPE-ADD
REPLAN
UNKNOWN
```

## Разрешённые типы изменений

```text
add
remove
rename
reduction
increase
postpone
```

## Правило на каждый новый цикл

Коротко:

1. `POST /snapshot`
2. если есть предыдущая версия -> `GET /deltas`
3. классификация
4. `POST /changelog`
5. `POST /strategic`
