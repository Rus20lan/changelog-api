# Как пользоваться Changelog API

Этот документ описывает практическое использование развернутого сервиса.

## Базовые данные

Production URL:

```text
https://api.cadkocomatozze.ru
```

Базовый префикс API:

```text
https://api.cadkocomatozze.ru/api/v1
```

## Аутентификация

Все эндпоинты, кроме `health`, требуют заголовок:

```text
X-Api-Key: ВАШ_API_KEY
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  https://api.cadkocomatozze.ru/api/v1/classifier
```

## Быстрая проверка

Проверка доступности API:

```bash
curl https://api.cadkocomatozze.ru/api/v1/health
```

Проверка авторизации:

```bash
curl -i https://api.cadkocomatozze.ru/api/v1/classifier
curl -i -H "X-Api-Key: YOUR_API_KEY" https://api.cadkocomatozze.ru/api/v1/classifier
```

## Основной сценарий работы

Обычная последовательность такая:

1. Отправить снапшот проекта через `POST /snapshot`.
2. Получить номер версии.
3. Если это не первая версия, запросить дельты через `GET /deltas/{project}/{v_from}/{v_to}`.
4. Классифицировать изменения на стороне клиента.
5. Сохранить журнал через `POST /changelog`.
6. Сохранить стратегические отклонения через `POST /strategic`.

## 1. Сохранение снапшота

Эндпоинт:

```text
POST /api/v1/snapshot
```

Минимальный пример:

```bash
curl -X POST "https://api.cadkocomatozze.ru/api/v1/snapshot" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
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

Типичный ответ:

```json
{
  "status": "ok",
  "project_name": "Пилот-2026",
  "version": 2,
  "tasks_saved": 142,
  "has_previous": true,
  "message": "Снепшот v2 сохранён. Задач: 142. Доступен расчёт дельт."
}
```

Что важно:

- `project_name` это ваш стабильный идентификатор проекта;
- `version` присваивается автоматически;
- если `has_previous=true`, можно сразу запрашивать дельты.

## 2. Получение последней версии

Эндпоинт:

```text
GET /api/v1/snapshot/{project_name}/latest
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/snapshot/Пилот-2026/latest"
```

## 3. Чтение конкретного снапшота

Эндпоинт:

```text
GET /api/v1/snapshot/{project_name}/{version}
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/snapshot/Пилот-2026/2"
```

С ограничением строк:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/snapshot/Пилот-2026/2?limit=10"
```

## 4. Получение дельт между версиями

Эндпоинт:

```text
GET /api/v1/deltas/{project_name}/{v_from}/{v_to}
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/deltas/Пилот-2026/1/2"
```

В ответе будут:

- `added`
- `removed`
- `changed`
- `unchanged_count`

`changed` уже содержит:

- `change_type`
- `delta_start_days`
- `delta_finish_days`
- `delta_baseline_days`

## 5. Получение классификатора

Эндпоинт:

```text
GET /api/v1/classifier
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/classifier"
```

Этот справочник удобно использовать перед сохранением журнала изменений.

## 6. Сохранение журнала изменений

Эндпоинт:

```text
POST /api/v1/changelog
```

Пример:

```bash
curl -X POST "https://api.cadkocomatozze.ru/api/v1/changelog" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "project_name": "Пилот-2026",
    "entries": [
      {
        "log_id": "Пилот-2026_1_2_45",
        "snapshot_from": 1,
        "snapshot_to": 2,
        "date": "2026-02-01",
        "uid": 45,
        "wbs": "1.3.2",
        "name": "Подготовка ОТР",
        "level": 2,
        "change_type": "increase",
        "delta_start_days": 0,
        "delta_finish_days": 18,
        "delta_baseline_days": 29,
        "category_code": "DELAY-EXT",
        "technical_summary": "Задержка поставки реагентов",
        "impact_type": "Задержка",
        "confidence": 0.90,
        "warnings": "",
        "escalation_required": false,
        "expert_comment": "",
        "status": "Auto"
      }
    ]
  }'
```

Допустимые `status`:

- `Auto`
- `Pending`
- `Confirmed`
- `Corrected`

Допустимые `change_type`:

- `add`
- `remove`
- `rename`
- `reduction`
- `increase`
- `postpone`

## 7. Чтение журнала изменений

Эндпоинт:

```text
GET /api/v1/changelog/{project_name}
```

Примеры:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/changelog/Пилот-2026"
```

Фильтр по версиям:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/changelog/Пилот-2026?snapshot_from=1&snapshot_to=2"
```

Фильтр по статусу:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/changelog/Пилот-2026?status_filter=Pending"
```

## 8. Обновление статуса записи

Эндпоинт:

```text
PATCH /api/v1/changelog/{project_name}/{log_id}/status
```

Пример:

```bash
curl -X PATCH "https://api.cadkocomatozze.ru/api/v1/changelog/Пилот-2026/Пилот-2026_1_2_45/status" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "new_status": "Corrected",
    "category_code": "DELAY-INT",
    "expert_comment": "Уточнено после проверки экспертом"
  }'
```

## 9. Сохранение стратегических отклонений

Эндпоинт:

```text
POST /api/v1/strategic
```

Пример:

```bash
curl -X POST "https://api.cadkocomatozze.ru/api/v1/strategic" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "project_name": "Пилот-2026",
    "snapshot_version": 2,
    "entries": [
      {
        "uid": 10,
        "wbs": "2.0",
        "name": "Экспериментальный блок",
        "summary": "Y",
        "baseline_finish": "2026-06-15",
        "current_finish": "2026-07-01",
        "delta_baseline_days": 16,
        "escalation": true,
        "ai_strategic_analysis": "Сдвиг на 16 дней. Основная причина — DELAY-EXT."
      }
    ]
  }'
```

## 10. Чтение стратегических отклонений

Эндпоинт:

```text
GET /api/v1/strategic/{project_name}
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/strategic/Пилот-2026"
```

## 11. Чтение метаданных проекта

Эндпоинт:

```text
GET /api/v1/meta/{project_name}
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/meta/Пилот-2026"
```

## 12. Список версий проекта

Эндпоинт:

```text
GET /api/v1/project/{project_name}/versions
```

Пример:

```bash
curl -H "X-Api-Key: YOUR_API_KEY" \
  "https://api.cadkocomatozze.ru/api/v1/project/Пилот-2026/versions"
```

Используйте этот запрос перед частичным удалением, чтобы показать пользователю доступные версии.

## 13. Удаление выбранных версий

Эндпоинт:

```text
DELETE /api/v1/project/{project_name}/versions
```

Пример:

```bash
curl -X DELETE "https://api.cadkocomatozze.ru/api/v1/project/Пилот-2026/versions" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "versions": [2, 3]
  }'
```

Важно:

- удаляются снапшоты, связанные записи `change_log` и соответствующие записи `strategic_control`;
- дельты между оставшимися версиями автоматически не пересчитываются;
- если удалена последняя версия, `project_meta.last_version` обновляется на новую максимальную версию.

## 14. Удаление проекта целиком

Эндпоинт:

```text
DELETE /api/v1/project/{project_name}
```

Пример:

```bash
curl -X DELETE "https://api.cadkocomatozze.ru/api/v1/project/Пилот-2026" \
  -H "X-Api-Key: YOUR_API_KEY"
```

Этот вызов удаляет проект из:

- `snapshots`
- `project_meta`
- `strategic_control`
- `change_log`

## 15. Полная очистка базы

Эндпоинт:

```text
DELETE /api/v1/admin/purge
```

Для защиты от случайного вызова требуется дополнительный заголовок:

```text
X-Confirm: PURGE-ALL
```

Пример:

```bash
curl -X DELETE "https://api.cadkocomatozze.ru/api/v1/admin/purge" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -H "X-Confirm: PURGE-ALL"
```

Это необратимая операция: она очищает все данные из рабочих таблиц сервиса.

## Практический рабочий цикл

Ниже удобный реальный шаблон использования:

1. Загрузить новый JSON плана в `POST /snapshot`.
2. Получить `version`.
3. Если `version > 1`, запросить `GET /deltas/{project}/{version-1}/{version}`.
4. На стороне клиента классифицировать каждое изменение.
5. Сохранить классификацию в `POST /changelog`.
6. Отдельно сохранить стратегические summary-задачи в `POST /strategic`.
7. Если эксперт скорректировал причину, обновить запись через `PATCH /changelog/.../status`.
8. Если нужно удалить мусорные версии, сначала запросить `GET /project/{project_name}/versions`, затем вызвать `DELETE /project/{project_name}/versions`.

## Типовые ошибки

`403 Invalid API key`

- не передан заголовок `X-Api-Key`
- передан неверный ключ

`404`

- не найден проект
- не найдена версия
- не найдена запись журнала

`400`

- пустой массив `rows`
- пустой массив `entries`
- невалидный формат тела запроса

## Полезная проверка после деплоя

```bash
curl https://api.cadkocomatozze.ru/api/v1/health
curl -H "X-Api-Key: YOUR_API_KEY" https://api.cadkocomatozze.ru/api/v1/classifier
```
