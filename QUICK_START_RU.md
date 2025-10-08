# Быстрый старт для aiochainscan

## ✅ Проблема решена!

Критическая проблема с установкой библиотеки **полностью исправлена**. Теперь установка работает корректно.

## Установка

### Способ 1: Из GitHub (рекомендуется)
```bash
pip install git+https://github.com/VaitaR/aiochainscan.git
```

### Способ 2: Клонировать и установить
```bash
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
pip install .
```

### Способ 3: Режим разработки
```bash
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
pip install -e ".[dev]"
```

## Проверка установки

```bash
# Запустите скрипт проверки
python verify_installation.py
```

Или вручную:

```python
import aiochainscan
print(f"Версия: {aiochainscan.__version__}")

from aiochainscan import Client, get_balance, get_block
print("✓ Установка успешна!")
```

## Что было исправлено

### До исправления ❌
- `pip install git+https://...` устанавливал только метаданные
- Python модули не копировались в site-packages
- `import aiochainscan` выдавал `ModuleNotFoundError`
- Невозможно было использовать библиотеку

### После исправления ✅
- Все Python модули корректно устанавливаются
- Импорт работает из коробки
- CLI инструмент доступен
- Все зависимости установлены
- Работает на Python 3.10, 3.11, 3.12, 3.13

## Быстрый пример использования

```python
import asyncio
from aiochainscan import get_balance, get_block_typed

async def main():
    # Получить баланс адреса
    balance = await get_balance(
        address="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3",
        api_kind="eth",
        network="main",
        api_key="YOUR_API_KEY"
    )
    print(f"Баланс: {balance} wei")

    # Получить информацию о блоке (типизированная версия)
    block = await get_block_typed(
        tag=17000000,
        full=False,
        api_kind="eth",
        network="main",
        api_key="YOUR_API_KEY"
    )
    print(f"Блок #{block['block_number']}")

asyncio.run(main())
```

## Настройка API ключей

```bash
# Создайте .env файл
export ETHERSCAN_KEY="ваш_ключ_etherscan"
export BSCSCAN_KEY="ваш_ключ_bscscan"
export POLYGONSCAN_KEY="ваш_ключ_polygonscan"
```

Или используйте CLI:
```bash
aiochainscan generate-env
# Отредактируйте сгенерированный .env файл
aiochainscan check
```

## Технические детали исправления

### Изменена система сборки
```toml
# Было (не работало):
[build-system]
requires = ["maturin>=1.6,<2.0"]
build-backend = "maturin"

# Стало (работает):
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
```

### Созданы новые файлы
1. `setup.py` - явная конфигурация пакета
2. `MANIFEST.in` - список файлов для включения
3. `.github/workflows/test-install.yml` - CI тесты установки
4. `verify_installation.py` - скрипт проверки

### Добавлена версия
```python
# В aiochainscan/__init__.py
__version__ = '0.2.1'
```

## Что включено в пакет

- ✅ Все Python модули (`aiochainscan/**/*.py`)
- ✅ Основные компоненты: `client`, `config`, `network`
- ✅ Унифицированная архитектура: `core/`, `scanners/`
- ✅ Гексагональная архитектура: `domain/`, `ports/`, `adapters/`, `services/`
- ✅ Легаси модули: `modules/` (account, block, contract, и т.д.)
- ✅ Тайп-хинты: `py.typed`, `*.pyi`
- ✅ CLI утилита: команда `aiochainscan`
- ✅ Все зависимости

## Опциональный Rust декодер (быстрый)

Rust расширение теперь действительно опционально:

```bash
# Сначала установите базовый пакет
pip install git+https://github.com/VaitaR/aiochainscan.git

# Затем опционально соберите Rust расширение
pip install maturin
maturin develop --manifest-path aiochainscan/fastabi/Cargo.toml
```

**Требования:**
- Rust toolchain (https://rustup.rs)
- maturin

**Преимущества:**
- 🚀 В 10-100 раз быстрее декодирование ABI
- 🔄 Автоматический откат на Python, если Rust недоступен

## Поддерживаемые блокчейны

- Ethereum (основная сеть + тестовые)
- BSC (BNB Smart Chain)
- Polygon
- Arbitrum
- Optimism
- Base
- И многие другие (15+ сетей)

## Решение проблем

### Если всё ещё получаете ошибку импорта:

```bash
# Удалите старую версию
pip uninstall aiochainscan

# Очистите кеш pip
pip cache purge

# Установите заново
pip install --no-cache-dir git+https://github.com/VaitaR/aiochainscan.git

# Проверьте
python -c "import aiochainscan; print(aiochainscan.__version__)"
```

### Проверьте расположение пакета:

```python
import aiochainscan
print(aiochainscan.__file__)
# Должно показать: .../site-packages/aiochainscan/__init__.py
```

## Автоматическое тестирование

CI автоматически проверяет:
- ✅ Установку wheel (Python 3.10-3.13)
- ✅ Установку source distribution
- ✅ Editable install
- ✅ Прямую установку из git
- ✅ Целостность структуры пакета
- ✅ Работоспособность импортов

## Документация

- **README.md** - Полная документация на английском
- **instructions.md** - Техническая документация проекта
- **PYPI_PUBLISHING.md** - Руководство по публикации в PyPI
- **INSTALLATION_FIX_SUMMARY.md** - Подробное описание исправления

## Вопросы и поддержка

- GitHub Issues: https://github.com/VaitaR/aiochainscan/issues
- Запустите `python verify_installation.py` для диагностики
- Проверьте результаты CI для вашей платформы

## Сравнение: до и после

| Аспект | До | После |
|--------|-----|--------|
| Система сборки | maturin (только Rust) | setuptools (Python + Rust опционально) |
| Установка из GitHub | ❌ Не работала | ✅ Работает |
| Python файлы в пакете | ❌ Нет | ✅ Да (все модули) |
| `import aiochainscan` | ❌ ModuleNotFoundError | ✅ Работает |
| CI тесты установки | ❌ Нет | ✅ Да (4 метода, 4 версии Python) |
| Готово для PyPI | ❌ Нет | ✅ Да |
| Rust расширение | ❌ Обязательно | ✅ Опционально |

---

**Исправлено:** 2025-10-08
**Версия:** 0.2.1
**Статус:** ✅ Готово к использованию и публикации в PyPI
