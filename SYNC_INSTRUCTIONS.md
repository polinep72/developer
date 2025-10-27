# Инструкции по синхронизации - Soft_IPK

## Обзор
Данный проект представляет собой многоуровневую структуру с множеством подпроектов. Для обеспечения непрерывности работы между разными компьютерами необходимо следовать данным инструкциям.

## Настройка Git

### Инициализация репозитория (если не создан)
```bash
cd Soft_IPK
git init
git add .
git commit -m "Initial commit: Multi-level project structure"
```

### Настройка .gitignore
Создать файл `.gitignore` с содержимым:
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
env.bak/
venv.bak/

# Logs
*.log
logs/
app_logs/

# Database
*.db
*.sqlite3

# Temporary files
temp/
uploads_temp/
*.tmp

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Docker
.docker/

# AI/ML models
*.pkl
*.faiss
faiss_index/

# Excel/CSV temp files
*.xlsx
*.csv
```

## Рабочий процесс

### При начале работы на новом компьютере:
1. **Клонирование репозитория**:
   ```bash
   git clone <repository-url> Soft_IPK
   cd Soft_IPK
   ```

2. **Чтение файлов контекста**:
   - Прочитать PROJECT_CONTEXT.md для понимания архитектуры
   - Изучить SOLUTIONS_HISTORY.md для истории решений
   - Просмотреть CHAT_HISTORY.md для контекста переписки

3. **Анализ подпроектов**:
   - Определить, с каким подпроектом предстоит работать
   - Проверить наличие файлов контекста в подпроекте
   - При отсутствии - создать их

### При работе с подпроектами:
1. **Переход в подпроект**:
   ```bash
   cd <subproject-name>
   ```

2. **Проверка контекста**:
   - Читать PROJECT_CONTEXT.md подпроекта
   - Изучить SOLUTIONS_HISTORY.md подпроекта
   - Просмотреть CHAT_HISTORY.md подпроекта

3. **Обновление контекста**:
   - При решении проблем обновлять SOLUTIONS_HISTORY.md
   - При переписке с AI обновлять CHAT_HISTORY.md
   - При изменении архитектуры обновлять PROJECT_CONTEXT.md

### При завершении работы:
1. **Сохранение изменений**:
   ```bash
   git add .
   git commit -m "Update: <описание изменений>"
   git push
   ```

2. **Обновление CHANGELOG.md**:
   - Добавить запись о внесенных изменениях
   - Указать версию и дату
   - Описать добавленные/измененные/исправленные функции

## Синхронизация между уровнями проекта

### Переход на уровень выше:
1. Обновить файлы контекста корневого уровня
2. Включить информацию о решенных проблемах в подпроектах
3. Обновить связи между подпроектами

### Переход в подпроект:
1. Создать/обновить файлы контекста подпроекта
2. Учесть влияние изменений на другие подпроекты
3. Документировать новые связи

## Рекомендации по использованию

### Структура коммитов:
- Использовать Conventional Commits формат
- Примеры: `feat: add new parser functionality`, `fix: resolve database connection issue`
- Группировать изменения по подпроектам

### Работа с ветками:
- Создавать отдельные ветки для крупных изменений
- Использовать префиксы: `feature/`, `fix/`, `refactor/`
- Примеры: `feature/wsb-v5`, `fix/chipdip-parser`

### Документирование:
- Всегда обновлять файлы контекста при изменениях
- Использовать единый формат для всех уровней проекта
- Включать код-референсы для существующего кода
- Использовать стандартные markdown блоки для нового кода

## Автоматизация

### Скрипт проверки контекста:
Создать скрипт `check-context.sh`:
```bash
#!/bin/bash
echo "Checking project context files..."

# Check root level
for file in PROJECT_CONTEXT.md SOLUTIONS_HISTORY.md CHAT_HISTORY.md SYNC_INSTRUCTIONS.md .cursorrules CHANGELOG.md; do
    if [ ! -f "$file" ]; then
        echo "Missing: $file"
    else
        echo "Found: $file"
    fi
done

# Check subprojects
for dir in */; do
    if [ -d "$dir" ] && [ "$dir" != "venv/" ] && [ "$dir" != "logs/" ]; then
        echo "Checking subproject: $dir"
        cd "$dir"
        for file in PROJECT_CONTEXT.md SOLUTIONS_HISTORY.md CHAT_HISTORY.md; do
            if [ ! -f "$file" ]; then
                echo "Missing in $dir: $file"
            fi
        done
        cd ..
    fi
done
```

### Настройка Git hooks:
Создать `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Check if context files are updated
if git diff --cached --name-only | grep -q "PROJECT_CONTEXT.md\|SOLUTIONS_HISTORY.md\|CHAT_HISTORY.md"; then
    echo "Context files updated - good!"
else
    echo "Warning: No context files updated in this commit"
fi
```
