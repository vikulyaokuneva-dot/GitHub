# ИИ Директор

## 1. Общая концепция

"ИИ Директор" - это минимальный сервис для управления задачами разработки внутри проекта.

Это НЕ автономный магический ИИ, который сам понимает бизнес, сам переписывает проект и сам принимает продуктовые решения. В текущем виде это оркестратор задач, набор правил для агентов и слой проверок.

Главная цель:

- брать задачу из очереди;
- готовить контекст для агента-разработчика;
- запускать проверки;
- контролировать, что изменены только разрешённые файлы;
- сохранять отчёты и логи по каждому запуску.

Сервис должен помогать делать изменения постепенно, проверяемо и безопасно.

## 2. Архитектура

### Task Manager

Отвечает за `tasks/tasks.json`:

- загружает задачи;
- выбирает следующую задачу;
- обновляет статус;
- увеличивает счётчик итераций;
- сохраняет состояние очереди.

### Orchestrator

Главная точка входа MVP:

```bash
python ai_director/orchestrator.py
```

Orchestrator создаёт run-директорию, пишет prompt для Developer Agent или Planner, запускает checks для обычных задач, вызывает File Guard и формирует итоговый отчёт.

### Developer Agent

Будущий агент, который будет реализовывать задачу. Сейчас для него создаётся файл `prompt_for_developer.md`.

Ожидаемый формат ответа описан в `prompts/developer_agent.md`.

### Fixer Agent

Будущий агент для точечных исправлений после failed checks или reviewer comments.

Ожидаемый формат ответа описан в `prompts/fixer_agent.md`.

### Reviewer Agent

Будущий агент для проверки результата:

- соответствие acceptance criteria;
- риски;
- пропущенные проверки;
- нарушения границ изменения файлов.

Ожидаемый формат ответа описан в `prompts/reviewer_agent.md`.

### File Guard

Слой безопасности, который проверяет изменённые файлы через `git status --porcelain`.

File Guard должен отвечать на вопрос: "имел ли агент право менять эти файлы?"

### Reporter / Logs

Reporter создаёт run-директории и сохраняет:

- `task.json`;
- `prompt_for_developer.md`;
- `check_results.json`;
- `guard_result.json`;
- `final_report.md`.

Логи и результаты запусков нужны, чтобы понимать, что сделал агент и почему задача получила финальный статус.

### Будущие блоки

LLM Client:

- единый клиент для обращения к модели;
- хранение request/response metadata;
- retry policy;
- ограничение стоимости и токенов.

Decision Engine:

- выбор следующего действия;
- перевод задачи в `FIXING`, `NEEDS_HUMAN` или `DONE`;
- анализ повторяющихся ошибок.

## 3. Жизненный цикл задачи

Допустимые статусы:

- `NEW` - задача создана и готова к работе.
- `IN_PROGRESS` - задача взята оркестратором.
- `READY_TO_CHECK` - подготовлен prompt или изменения, можно запускать проверки.
- `CHECKING` - идут автоматические проверки.
- `PASSED` - проверки прошли, но задача ещё не закрыта.
- `FAILED` - проверки или File Guard завершились ошибкой.
- `FIXING` - задача находится на итерации исправления.
- `DONE` - задача завершена.
- `NEEDS_HUMAN` - нужен человек, потому что агент не может безопасно продолжать.

MVP использует укороченный сценарий:

`NEW -> IN_PROGRESS -> READY_TO_CHECK -> CHECKING -> DONE/FAILED`

## Обработка ошибок (Fix Loop Stage 1)

В Stage 1 оркестратор не исправляет код сам и не вызывает LLM.

Если checks или File Guard завершаются ошибкой:

- создаётся `failure_snapshot.json`;
- в него сохраняются результаты checks и File Guard;
- увеличивается `iterations`;
- если `iterations` достиг или превысил `max_iterations`, задача получает статус `NEEDS_HUMAN`;
- если лимит ещё не достигнут, задача получает статус `FAILED` и готова к повторной попытке.

Если checks прошли и File Guard не нашёл нарушений, задача получает статус `DONE`.

## Fix Loop Stage 2 (LLM Dry-Run)

Stage 2 добавляет подготовку Fixer Agent без применения изменений к проекту.

Если checks или File Guard завершаются ошибкой:

- формируется prompt для Fixer Agent;
- prompt сохраняется в `fix_prompt.md`;
- mock-ответ LLM сохраняется в `fix_response.md`;
- код проекта пока НЕ применяется автоматически;
- реальные API пока НЕ подключаются;
- цель этапа - отладить формат взаимодействия с ИИ и будущий цикл исправлений.

Текущий LLM Client использует OpenRouter через `src.openrouter_client.generate_text` / `generate_text_result`.

## OpenRouter LLM

Fixer Agent отправляет prompt в OpenRouter и не запускает локальные модели.

Настройки:

- `OPENROUTER_API_KEY` должен быть задан в окружении.
- `AI_DIRECTOR_MODEL` по умолчанию: `qwen/qwen3-coder:free`.
- `AI_DIRECTOR_MODEL_FALLBACKS` можно задать списком через запятую, например:
  `qwen/qwen3-coder:free,deepseek/deepseek-chat-v3-0324:free,mistralai/mistral-7b-instruct:free`.
- `ai_director/config.py` хранит `LLM_PROVIDER = "openrouter"`.

Команда для smoke-проверки:

```bash
python -m src.openrouter_client
python ai_director/orchestrator.py
```

Если OpenRouter возвращает 429, 5xx, HTTP 400 `invalid model` или 404 `no endpoints`, клиент пробует следующую модель из `AI_DIRECTOR_MODEL_FALLBACKS`. В `llm_result.json` сохраняются `attempted_models`, `selected_model`, `final_status` и `last_error`.

Если все модели недоступны, отсутствует ключ, rate limit не снялся или случился timeout, задача получает статус `no_llm` или `api_error`, а apply stage сохраняется как `skipped`.

## Planner-only режим

Задача может указать поле:

```json
{
  "mode": "planner_only"
}
```

`planner_only` используется для аналитических и планировочных задач, где нужно получить краткий план от LLM, но нельзя применять изменения к коду.

Перед задачей Orchestrator добавляет краткий project context до 8000 символов: верхнеуровневые файлы и папки, наличие ключевых путей, последние 3 run-директории и выдержку из `README_AI_DIRECTOR.md`. В `llm_result.json` сохраняются `context_included` и `context_chars`.

В этом режиме Orchestrator:

- вызывает LLM через OpenRouter;
- сохраняет ответ в `llm_result.json`;
- сохраняет план в `apply_plan.json`;
- не запускает применение изменений;
- пишет `apply_result.json` с `applied=false`, `skipped=true`, `reason="planner_only"`;
- переводит задачу в `DONE`, если LLM успешно вернула ответ.

Если OpenRouter недоступен, задача получает `no_llm` или `api_error`, как в обычном LLM fallback flow.

Пример задачи:

```json
{
  "id": "task_openrouter_demo",
  "title": "OpenRouter demo: план развития AI Director WB",
  "description": "Проанализируй структуру проекта и предложи минимальный следующий шаг. Не меняй код.",
  "status": "NEW",
  "mode": "planner_only",
  "priority": "low",
  "acceptance_criteria": [
    "LLM вызывается через OpenRouter",
    "llm_result.json сохраняется",
    "apply_plan.json сохраняется",
    "apply_result.json сохраняется"
  ]
}
```

Planner-only задачу можно добавить через CLI:

```bash
python ai_director/create_task.py --title "Next AI Director step" --prompt "Предложи следующий безопасный шаг развития AI Director WB" --mode planner_only
```

CLI добавляет задачу в `ai_director/tasks/tasks.json` со статусом `NEW`, полем `created_at`, безопасным `id` на основе slug и timestamp, и не перезаписывает существующие задачи.

Последний результат AI Director можно быстро посмотреть через CLI:

```bash
python ai_director/show_last_run.py
python ai_director/show_last_run.py --full
```

Создать planner-only задачу, сразу запустить AI Director и показать результат можно одной командой:

```bash
python ai_director/run_once.py --title "Next step" --prompt "Предложи следующий безопасный шаг развития AI Director WB"
python ai_director/run_once.py --title "Next step" --prompt "..." --full
```

## Apply Stage безопасный dry-run

`apply_engine.py` - это слой будущего применения фиксов от Fixer Agent.

В текущем этапе он работает только в безопасном dry-run режиме:

- файлы проекта НЕ меняются;
- `dry_run=True` обязателен;
- создаётся `apply_plan.json`;
- создаётся `apply_result.json`;
- результат содержит только список потенциальных действий;
- реальные правки будут разрешены только на следующем этапе после whitelist, backup и diff-логирования.

Текущая цепочка при ошибке:

```text
FAILED -> failure_snapshot.json -> fix_prompt.md -> fix_response.md -> apply_plan.json -> apply_result.json
```

## 4. Правила завершения задачи

Задачу можно считать завершённой только если:

- все checks прошли;
- File Guard не нашёл запрещённых изменений;
- результат соответствует acceptance criteria;
- есть отчёт агента или run summary;
- нет открытых вопросов, требующих решения человека.

Если хотя бы одно условие не выполнено, задача не должна переходить в `DONE`.

## 5. Правила безопасности

Агентам запрещено:

- менять лишние файлы;
- трогать секреты;
- читать или менять `.env` без отдельной явной задачи;
- удалять код без причины;
- переписывать архитектуру без отдельной задачи;
- смешивать несколько крупных изменений в одну задачу;
- физически мигрировать старые файлы без отдельной миграционной задачи.

Если задача требует опасного действия, статус должен стать `NEEDS_HUMAN`.

## 6. Какие файлы можно менять

Базовые разрешённые зоны:

- `src/`
- `tests/`
- `ai_director/`

Для миграционных задач разрешённые зоны должны уточняться отдельно в самой задаче.

## 7. Какие файлы нельзя менять

Запрещённые зоны:

- `.git/`
- `.env`
- `credentials/`
- `secrets/`
- системные файлы;
- файлы с токенами, ключами и приватными настройками.

Правило простое: если файл похож на секрет или инфраструктурную основу проекта, агент не должен его менять.

## 8. Как добавлять задачи

Задачи лежат в:

```text
ai_director/tasks/tasks.json
```

Минимальная структура задачи:

```json
{
  "id": "task_001",
  "title": "Короткое название",
  "description": "Что нужно сделать",
  "status": "NEW",
  "iterations": 0,
  "max_iterations": 5,
  "checks": ["python -m pytest"],
  "acceptance_criteria": [
    "Критерий 1",
    "Критерий 2"
  ]
}
```

Правила:

- одна задача = один понятный шаг;
- acceptance criteria должны быть проверяемыми;
- checks должны быть минимально достаточными;
- если задача рискованная, явно укажи разрешённые файлы и ограничения.

## 9. Как запускать

Из корня проекта:

```bash
python ai_director/orchestrator.py
```

MVP выполнит:

1. загрузку `tasks.json`;
2. выбор первой задачи `NEW`;
3. создание run-директории;
4. запись task snapshot;
5. создание prompt для Developer Agent;
6. запуск checks;
7. запуск File Guard;
8. сохранение итогового отчёта;
9. обновление статуса задачи.

## 10. Как читать логи

Каждый запуск сохраняется в:

```text
ai_director/logs/runs/<timestamp>_<task_id>/
```

Основные файлы:

- `task.json` - снимок задачи на момент запуска;
- `prompt_for_developer.md` - prompt для будущего Developer Agent;
- `check_results.json` - stdout/stderr и коды возврата checks;
- `guard_result.json` - список изменённых файлов и нарушения File Guard;
- `final_report.md` - короткое резюме запуска.

Если задача завершилась `FAILED`, сначала смотри:

1. `check_results.json`
2. `guard_result.json`
3. `final_report.md`

## 11. План развития

### MVP

- файловый `tasks.json`;
- базовый orchestrator;
- checks через subprocess;
- File Guard;
- run reports;
- prompts без LLM-вызовов.

### v1

- LLM Client;
- реальные Developer/Fixer/Reviewer agents;
- статусы `FIXING`, `PASSED`, `NEEDS_HUMAN`;
- лимиты итераций;
- отдельные checks по типам задач;
- строгие task scopes.

### v2

- Decision Engine;
- автоматический разбор ошибок тестов;
- планировщик волн миграции;
- интеграция с CI;
- richer audit trail;
- политики стоимости и качества LLM-вызовов.

## 12. Миграция

В текущем шаге физическая миграция старых файлов НЕ выполняется.

Этот раздел описывает карту миграции и правила. Реальный перенос будет отдельными задачами.

### 12.1 Блоки для миграции

Кандидаты на будущую миграцию:

- `report_payload_builder.py`
- `report_payload_schema.py`
- `email_renderer_v2.py`
- `pdf_renderer_v2.py`
- `report_v2/tests/`

Аналитические домены:

- `profit_contribution`
- ABC-анализ
- SKU health
- revenue / profit

Правила:

- сначала тесты;
- потом перенос;
- не переписывать всё сразу;
- если непонятно, ставить `NEEDS_HUMAN`;
- старое поведение фиксировать тестами до переноса;
- новые слои включать только после зелёных проверок.

### 12.2 Блоки с нуля

Эти части строятся в `ai_director/` как новые:

- Orchestrator
- Task Manager
- File Guard
- Prompts
- Reporter
- LLM Client - позже
- Decision Engine - позже

### 12.3 Правила миграции

- по одному блоку;
- один шаг = одна задача;
- сначала тесты;
- старый код = источник правды;
- новый код = после тестов;
- не удалять старое без отдельной задачи;
- не смешивать миграцию payload, PDF и email в одном шаге;
- каждый перенос должен иметь acceptance criteria;
- если обнаружено расхождение данных, задача уходит в `NEEDS_HUMAN`.

### 12.4 Таблица миграции

| Блок | Старый | Новый | Тип |
| --- | --- | --- | --- |
| Payload | `report_payload_builder.py` | payload layer | MIGRATE |
| Schema | `report_payload_schema.py` | payload contracts | MIGRATE |
| Email | `email_renderer_v2.py` | renderer | MIGRATE |
| PDF | `pdf_renderer_v2.py` | renderer | MIGRATE |
| Tests | `report_v2/tests/` | test layer | MIGRATE |
| Profit contribution | `profit_contribution` artifacts / adapters | analytics adapter | MIGRATE |
| ABC-анализ | `abc_analysis` artifacts / adapters | analytics adapter | MIGRATE |
| SKU health | SKU health sections / watchlists | analytics adapter | MIGRATE |
| Revenue / profit | financial metrics | financial layer | MIGRATE |
| Orchestrator | - | `ai_director` | BUILD_NEW |
| Task Manager | - | `ai_director` | BUILD_NEW |
| File Guard | - | `ai_director` | BUILD_NEW |
| Prompts | - | `ai_director` | BUILD_NEW |
| Reporter | - | `ai_director` | BUILD_NEW |

### 12.5 Волны разработки

Wave 1 - каркас:

- создать `ai_director/`;
- добавить Task Manager, Orchestrator, File Guard, Reporter;
- добавить prompts;
- добавить документацию.

Wave 2 - тесты:

- покрыть Task Manager;
- покрыть File Guard;
- покрыть Reporter;
- покрыть базовый lifecycle orchestrator.

Wave 3 - адаптеры:

- добавить adapter layer для payload;
- добавить adapter layer для renderers;
- добавить контрактные тесты на старое поведение.

Wave 4 - LLM:

- добавить LLM Client;
- подключить Developer Agent;
- подключить Fixer Agent;
- подключить Reviewer Agent;
- сохранять LLM transcripts.

Wave 5 - автономность:

- добавить Decision Engine;
- добавить автоматические fix loops;
- добавить лимиты риска;
- добавить режим `NEEDS_HUMAN`;
- добавить CI/integration hooks.
