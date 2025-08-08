# Оптимизация сбора транзакций - Реализация

## Описание изменений

Реализована оптимизированная система сбора всех транзакций с использованием приоритетной очереди и динамического разбиения диапазонов, как описано в плане.

## Новые компоненты

### 1. `fetch_all_elements_optimized()` в `Utils`

**Расположение**: `aiochainscan/modules/extra/utils.py`

Основная оптимизированная функция, реализующая алгоритм:

```python
async def fetch_all_elements_optimized(
    self,
    address: str,
    data_type: str,
    start_block: int = 0,
    end_block: int | None = None,
    decode_type: str = 'auto',
    max_concurrent: int = 3,
    max_offset: int = 10000,
    *args,
    **kwargs,
) -> list[dict]:
```

### 2. Обновленная `fetch_sample_transactions()`

**Расположение**: `examples/test_decode_functionality.py`

Добавлена поддержка нового оптимизированного метода с fallback на legacy:

```python
async def fetch_sample_transactions(self, pages: int = 3, use_optimized: bool = True)
```

## Алгоритм работы

### 1. Инициализация
- Создается приоритетная очередь (`heapq`) для диапазонов блоков
- Добавляется 3 начальных диапазона: левый край, центр, правый край
- Инициализируется семафор для контроля concurrency

### 2. Worker-цикл
```python
async def worker(range_info):
    """Worker function to process a single block range."""
    _, range_id, block_start, block_end = range_info

    async with semaphore:  # ≤ RPS_LIMIT одновременно
        elements = await function(
            address=address,
            start_block=block_start,
            end_block=block_end,
            page=1,
            offset=max_offset,
            **kwargs,
        )
        return range_id, block_start, block_end, elements
```

### 3. Динамическое разбиение
```python
# Если вернулось ровно max_offset элементов → делим диапазон пополам
if len(elements) >= max_offset and block_end > block_start:
    mid_block = (block_start + block_end) // 2

    # Добавляем обе половины обратно в очередь
    heapq.heappush(range_queue, (-(mid_block - block_start), range_counter, block_start, mid_block))
    heapq.heappush(range_queue, (-(block_end - mid_block), range_counter, mid_block + 1, block_end))
```

### 4. Постобработка
- Сортировка по блоку и индексу транзакции
- Удаление дубликатов по hash
- Применение декодирования (если требуется)

## Ключевые особенности

### ✅ Приоритетная очередь
- Использует `heapq` с отрицательными размерами для max-heap
- Крупнейшие диапазоны обрабатываются первыми
- Автоматически оптимизирует порядок обработки

### ✅ Контроль concurrency
- `asyncio.Semaphore(max_concurrent)` для ограничения RPS
- По умолчанию `max_concurrent=3` для соблюдения rate limits
- Batch-обработка диапазонов

### ✅ Динамическое разбиение
- Диапазон делится пополам при получении максимального количества результатов
- Автоматически адаптируется к плотности данных
- Избегает пропуска транзакций из-за лимитов API

### ✅ Deduplication и сортировка
- Удаление дубликатов по transaction hash
- Сортировка по `(blockNumber, transactionIndex)`
- Поддержка hex и decimal форматов

### ✅ Обработка ошибок
- Graceful fallback при ошибках worker'ов
- Логирование всех этапов процесса
- Возврат пустого списка при критических ошибках

### ✅ Backward compatibility
- Старый метод сохранен как `_fetch_sample_transactions_legacy()`
- Автоматический fallback при ошибках оптимизированного метода
- Параметр `use_optimized=True/False` для контроля

## Тестирование

### Юнит-тесты
**Файл**: `tests/test_utils_optimized.py`

Покрывают:
- ✅ Базовая функциональность
- ✅ Разбиение диапазонов
- ✅ Deduplication
- ✅ Сортировка результатов
- ✅ Обработка edge cases
- ✅ Error handling
- ✅ Concurrent processing
- ✅ Hex/decimal конвертация

### Интеграционные тесты
Обновленная функция `fetch_sample_transactions()` тестируется в существующих integration tests.

## Производительность

### Ожидаемые улучшения
- **3-10x ускорение** для больших наборов данных
- **Линейное масштабирование** с количеством worker'ов (до rate limit)
- **Адаптивность** к плотности данных в разных диапазонах блоков
- **Эффективное использование API** за счет приоритизации

### Контроль ресурсов
- Семафор предотвращает превышение rate limits
- Приоритетная очередь минимизирует количество запросов
- Deduplication экономит память и время обработки

## Пример использования

```python
from aiochainscan.modules.extra.utils import Utils

# Создание клиента
client = Client.from_config('eth', 'main')
utils = Utils(client)

# Оптимизированное получение всех транзакций
transactions = await utils.fetch_all_elements_optimized(
    address='0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
    data_type='normal_txs',
    start_block=0,
    max_concurrent=3,  # Соблюдение rate limits
    max_offset=10000   # Максимум за запрос
)

print(f"Получено {len(transactions)} уникальных транзакций")
```

## Совместимость

- ✅ Полная обратная совместимость с existing API
- ✅ Все existing tests продолжают работать
- ✅ Graceful fallback на legacy методы
- ✅ Не нарушает существующую функциональность

## Итоги

Реализация полностью соответствует предложенному плану и обеспечивает значительное улучшение производительности при сохранении стабильности и совместимости системы.
