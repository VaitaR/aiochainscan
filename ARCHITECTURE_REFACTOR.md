# Архитектурный рефакторинг ChainscanClient

## 🎯 Цель рефакторинга

Упростить и унифицировать интерфейс ChainscanClient, убрав двойственную логику между `scanner_id` и `network` параметрами.

## 📊 Анализ текущей архитектуры

### Текущие проблемы:
1. **Двойственная логика**: `scanner_id` и `network` дублируют информацию
2. **Разные схемы**: разные провайдеры используют параметры по-разному
3. **Сложность понимания**: `('blockscout', 'v1', 'blockscout_eth', 'eth')` неясно

### Выясненные особенности провайдеров:

#### Etherscan V2:
- **URL**: `https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance`
- **Аутентификация**: query параметр `apikey`
- **Chain ID**: передается как `chainid` параметр
- **Единый домен**: `etherscan.io` для всех сетей

#### BlockScout:
- **URL**: `https://eth.blockscout.com/api?module=account&action=balance`
- **Аутентификация**: query параметр `apikey`
- **Instance domains**: разные для каждой сети (`eth.blockscout.com`, `base.blockscout.com`)
- **Network mapping**: `network='eth'` → instance=`eth.blockscout.com`

#### Moralis:
- **URL**: `https://deep-index.moralis.io/api/v2.2/0x1/native/balance/0x...`
- **Аутентификация**: header `X-API-Key`
- **Chain ID**: в hex формате в URL пути (`0x1`, `0x2105`)
- **RESTful API**: path-based параметры

## 🚀 Предлагаемая архитектура

### Унифицированные параметры:
```python
# Вместо 4 параметров - 3 основных
ChainscanClient.from_config(
    scanner_name='blockscout',      # Provider name
    scanner_version='v1',           # API version
    network='eth'                   # Chain name/ID
)
```

### Автоматическое разрешение:
- `network='eth'` → chain_id=1, blockscout_instance='eth.blockscout.com'
- `network='base'` → chain_id=8453, blockscout_instance='base.blockscout.com'
- `network=1` → chain_id=1, blockscout_instance='eth.blockscout.com'

### Provider-specific логика:
- **Etherscan V2**: chain_id как query параметр `chainid`
- **BlockScout**: instance_domain для URL построения
- **Moralis**: chain_id_hex в URL пути

## 📋 Задачи по реализации

### ✅ Выполненные задачи:
1. **Создан chain_registry.py** - стандартизированные chain_id с алиасами
2. **Обновлен from_config** - принимает network как chain name/ID
3. **Обновлены сканеры** - принимают chain_id и используют его правильно
4. **Обновлены тесты** - отражают новую архитектуру
5. **Обновлена документация** - примеры с именованными параметрами

### 🔄 Текущие задачи:
1. **Обновить все примеры** - использовать именованные параметры
2. **Протестировать интеграцию** - убедиться что все провайдеры работают
3. **Обновить тесты** - проверить все сценарии

### 📝 Файлы для проверки:

#### Core компоненты:
- `aiochainscan/core/client.py` - from_config и ChainscanClient
- `aiochainscan/chain_registry.py` - стандартизированные chain_id
- `aiochainscan/scanners/base.py` - базовый сканер с chain_id
- `aiochainscan/scanners/etherscan_v2.py` - Etherscan с chain_id в query
- `aiochainscan/scanners/blockscout_v1.py` - BlockScout с instance_domain
- `aiochainscan/scanners/moralis_v1.py` - Moralis с chain_id_hex в пути

#### Документация:
- `README.md` - примеры с именованными параметрами
- `AGENTS.md` - обновленная архитектура
- `examples/*.py` - обновленные примеры

#### Тесты:
- `tests/test_*` - обновленные тесты
- `tests/test_e2e_*` - интеграционные тесты

## 🎯 Проверка корректности

### Тестовые сценарии:
1. **Etherscan V2 для Ethereum**: `ChainscanClient.from_config('etherscan', 'v2', 'ethereum')`
2. **Etherscan V2 для Base**: `ChainscanClient.from_config('etherscan', 'v2', 'base')`
3. **BlockScout для Ethereum**: `ChainscanClient.from_config('blockscout', 'v1', 'ethereum')`
4. **BlockScout для Polygon**: `ChainscanClient.from_config('blockscout', 'v1', 'polygon')`
5. **Moralis для Ethereum**: `ChainscanClient.from_config('moralis', 'v1', 'ethereum')`

### Что проверять:
- ✅ Клиенты создаются без ошибок
- ✅ Правильные URL генерируются
- ✅ Аутентификация работает
- ✅ Реальные API вызовы возвращают данные
- ✅ Chain ID правильно передается

## 🚀 Результат

**Новая унифицированная архитектура:**
```python
# Все провайдеры используют одинаковый интерфейс
client = ChainscanClient.from_config('blockscout', 'v1', 'ethereum')     # BlockScout
client = ChainscanClient.from_config('etherscan', 'v2', 'ethereum')      # Etherscan
client = ChainscanClient.from_config('moralis', 'v1', 'ethereum')        # Moralis

# Работает с chain_id
client = ChainscanClient.from_config('etherscan', 'v2', 1)          # Ethereum
client = ChainscanClient.from_config('blockscout', 'v1', 8453)       # Base
```

**Преимущества:**
- ✅ **Единообразие** - одинаковый интерфейс для всех провайдеров
- ✅ **Простота** - меньше параметров, ясная семантика
- ✅ **Гибкость** - работает с chain names и chain IDs
- ✅ **Расширяемость** - легко добавлять новые провайдеры
- ✅ **Backward compatibility** - старый код продолжает работать

## 📈 Следующие шаги

1. **Тестирование** - убедиться что все провайдеры работают
2. **Документация** - обновить все примеры
3. **Мониторинг** - следить за работой в продакшене
4. **Оптимизация** - убрать legacy код когда будет готово
