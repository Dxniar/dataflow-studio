# DataFlow Studio — итоговый отчёт

Дата: 25 октября 2026 года. Личное портфолио, созданное с помощью ИИ; все данные синтетические. Это не кейс оплаченного заказчика.

## 1. Название проекта

**DataFlow Studio 1.1 — Excel & CSV Automation with Python.** Настольное приложение и CLI для повторяемой обработки таблиц. Лицензия — MIT. В версии 1.1 переработан интерфейс: компактная навигация, единые иконки, больше места таблицам, тёмные полосы прокрутки и читаемая панель операций с отдельным просмотром JSON.

## 2. Репозиторий GitHub

[Dxniar/dataflow-studio](https://github.com/Dxniar/dataflow-studio), опубликованная ветка `main`.

Страница релиза: [v1.1.0](https://github.com/Dxniar/dataflow-studio/releases/tag/v1.1.0). Вложения: [Windows ZIP](https://github.com/Dxniar/dataflow-studio/releases/download/v1.1.0/DataFlowStudio-Windows.zip), [исходники](https://github.com/Dxniar/dataflow-studio/releases/download/v1.1.0/dataflow-studio-source.zip), [MP4](https://github.com/Dxniar/dataflow-studio/releases/download/v1.1.0/dataflow-studio-demo.mp4) и контрольные суммы SHA-256.

## 3. Архитектура и принятые решения

Общий движок на pandas/openpyxl обслуживает CustomTkinter GUI и Typer CLI. Конфигурация валидируется до обработки; результат содержит отдельную таблицу и рассчитанные метрики. Исходная таблица сохраняется для сравнения. Фоновые потоки выполняют длительные операции, очередь передаёт результаты главному потоку Tk, который обновляет виджеты.

Подробное ТЗ и разрешение на автономную работу позволили принимать обычные технические решения без промежуточных согласований. Работа начата в отдельной новой папке с выделенной веткой сборки. Общий контракт закреплён до параллельной реализации, исполнителям выделены разные файлы. Интеграция, исправления, сборка и повторные проверки выполнялись централизованно.

См. [ARCHITECTURE.md](ARCHITECTURE.md) и [API_CONTRACT.md](API_CONTRACT.md).

## 4. Реализованная функциональность

- Чтение CSV/XLSX с выбором листа Excel, кодировки и разделителя CSV; просмотр столбцов, типов и пропусков.
- Удаление дубликатов и пустых строк, очистка пробелов, заполнение пропусков, нормализация заголовков и точное сопоставление значений.
- Переименование, удаление, выбор и перестановка столбцов; преобразование типов, фильтрация и сортировка.
- Добавление строк из нескольких таблиц в режимах union/strict/intersection; конвертация CSV ↔ XLSX.
- Пакетная обработка с результатом по каждому файлу, повторное использование JSON-workflow, сравнение до/после, история и настройки текущего сеанса.
- Защита исходных путей и существующих файлов, уникальные имена выгрузок, защита формулоподобного текста. Произвольные выражения из JSON не выполняются.

GUI содержит восемь страниц: Dashboard, Data Cleaning, Transform Data, Merge Files, Convert Files, Before / After, History & Logs, Settings.

## 5. Запуск GUI

Из корня проекта в PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m dataflow
```

Требуется Python 3.11+ с Tk; для Windows-сборки рекомендован Python 3.12. Реальный GUI прошёл все восемь страниц и десять проверок workflow: загрузку, выбор листа, обработку, сравнение, чтение выгрузки, отказ от перезаписи, конвертацию, batch, merge и переключение оформления.

## 6. Запуск CLI

```powershell
.\.venv\Scripts\dataflow.exe --help
.\.venv\Scripts\dataflow.exe inspect examples/input/customers_dirty.csv
.\.venv\Scripts\dataflow.exe process examples/input/customers_dirty.csv --config examples/demo_config.json --output examples/output/processed.xlsx --collision unique
```

Доступны `inspect`, `clean`, `process`, `convert`, `merge`, `batch`. Выполнены **16 проверок команд README и их справок**: восемь файловых примеров, семь справок и полный демо-сценарий; все завершились успешно. Восемь выгрузок повторно прочитаны, размеры совпали с JSON-отчётами. SHA-256 подтвердил неизменность исходных файлов при обработке.

## 7. Результаты pytest и Ruff

Локально на Windows/Python 3.12: **103 теста пройдены**, Ruff lint и проверка форматирования пройдены. Включена регрессия для CLI с принудительным ANSI-оформлением.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Проверены преобразования, строгая конфигурация, Unicode, формулоподобный текст, ошибки входных файлов, защита выгрузок, частичный сбой batch и одинаковое поведение GUI-контроллера/CLI. Подробности: [VALIDATION.md](VALIDATION.md).

## 8. Статус GitHub Actions

Матрица охватывает Windows/Linux и Python 3.11–3.13; отдельное задание собирает Windows-приложение. Результат нового запуска для версии 1.1 добавляется при финальной проверке релиза. Исторический [запуск 40139251864](https://github.com/Dxniar/dataflow-studio/actions/runs/40139251864) проверял версию 1.0 и завершился успешно во всех семи заданиях.

## 9. Статус Windows EXE

PyInstaller собрал `dist/DataFlowStudio/DataFlowStudio.exe`; настоящее окно EXE было открыто. Автоматические проверки обработки проводились на Python-версии GUI; для EXE отдельно проверен запуск окна. Wheel и source distribution также собраны.

Архив: `artifacts/DataFlowStudio-Windows.zip`, около **48,5 МБ**. Распакуйте весь архив и запустите `DataFlowStudio/DataFlowStudio.exe`; Python устанавливать не требуется. Сохраняйте папку `_internal` рядом с EXE. Сборка portable, без установщика и цифровой подписи.

## 10. Скриншоты

Пять настоящих снимков работающего приложения:

| Файл | Содержание |
| --- | --- |
| [01-dashboard.png](../assets/screenshots/01-dashboard.png) | Dashboard. |
| [02-input-data.png](../assets/screenshots/02-input-data.png) | Исходная синтетическая таблица. |
| [03-processing.png](../assets/screenshots/03-processing.png) | Выбранные операции. |
| [04-before-after.png](../assets/screenshots/04-before-after.png) | Сравнение и рассчитанные метрики. |
| [05-results.png](../assets/screenshots/05-results.png) | Выгрузки и история результатов. |

## 11. Демонстрация до/после

```powershell
.\.venv\Scripts\python.exe scripts/run_demo.py
```

| Метрика | До | После |
| --- | --- | --- |
| Строки | 153 | 132 |
| Пропуски | 39 | 0 |
| Столбцы | 6 | 6 |

Удалены **18 дубликатов** и **3 полностью пустые строки**. Batch: **2 успешных файла**, **0 ошибок**. Результаты и JSON-отчёт сохраняются в `examples/output/`. Это измерения синтетического примера, а не показатель бизнеса или гарантия производительности. См. [DEMO.md](DEMO.md).

## 12. Видео и инструкция записи

Файл: `artifacts/dataflow-studio-demo.mp4`. Длительность — **59,93 секунды**, 1920×1080, H.264, 15 fps, английские титры, без аудио и водяного знака. Использована настоящая запись действий GUI и реальной обработки синтетических данных. Видео смонтировано и снабжено титрами; результаты не подменялись.

Проверены пять разных кадров и полное декодирование файла без ошибок; сравнение показывает реальные строки и все столбцы с прокруткой. [Скачать видео](https://github.com/Dxniar/dataflow-studio/releases/download/v1.1.0/dataflow-studio-demo.mp4). Для повторной записи подготовлены [сценарий и инструкция OBS](VIDEO_SCRIPT.md).

## 13. Известные ограничения

- Файлы и копии до/после целиком находятся в оперативной памяти. Превью ограничено 100 строками, но обработка не является потоковой.
- pandas определяет типы при импорте: числовые идентификаторы могут потерять ведущие нули. Проверяйте импорт перед использованием результата.
- XLSX-выгрузка сохраняет таблицу значений, а не оформление, диаграммы, макросы, структуру нескольких листов или исходные формулы. Формулы не вычисляются; кэшированные значения могут быть устаревшими или отсутствовать.
- История и настройки действуют в текущем сеансе. Одновременно выполняется одна задача; отмена, планировщик и восстановление прерванной обработки не реализованы.
- Windows EXE не подписан и требует всей папки с `_internal`; возможны предупреждения о неизвестном издателе.
- Merge добавляет строки. Реляционные JOIN, нечёткое сопоставление, защищённые паролем книги и удалённые URL вне текущей области проекта.

Полный список: [LIMITATIONS.md](LIMITATIONS.md).

## 14. Список файлов и структура

Корень проекта: `C:\Users\ayatd\Desktop\Pet projects\DataFlow Studio`.

```text
src/dataflow/core/     Общий движок, валидация, чтение и безопасный экспорт
src/dataflow/gui/      Страницы CustomTkinter, таблицы и фоновый контроллер
src/dataflow/cli.py    Typer CLI и JSON-отчёты
tests/                Автоматические проверки
examples/             Синтетические входные файлы и JSON-workflow
scripts/              Генерация примеров, демо, GUI-проверка и Windows-сборка
assets/screenshots/   Пять снимков настоящего приложения
docs/                 Архитектура, API, демо, ограничения и проверки
.github/workflows/    CI и Windows-сборка
```

Материалы передачи: `artifacts/DataFlowStudio-Windows.zip`, `artifacts/dataflow-studio-source.zip`, `artifacts/dataflow-studio-demo.mp4` и `artifacts/SHA256SUMS.txt`. Они также передаются через [релиз v1.1.0](https://github.com/Dxniar/dataflow-studio/releases/tag/v1.1.0). Генерируемая папка `artifacts/` исключена из Git.

## 15. English Upwork portfolio description

**DataFlow Studio — Excel & CSV Automation with Python**

DataFlow Studio is an AI-assisted personal portfolio project for repeatable Excel and CSV workflows. A shared Python engine powers a desktop interface and CLI for cleaning, transforming, merging, converting and batch-processing tables. Users can compare original and processed data, reuse validated JSON workflows and export results while protecting source files.

The demonstration uses synthetic records, including English, Russian and Kazakh text. It is not a paid client case study. Source code, automated tests, reproducible examples and documentation are included. Client deliverables would be scoped to agreed files, operations and acceptance examples; the full desktop application is not included in every service package.
