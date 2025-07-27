# Тестирование с вашими API ключами

Для полного тестирования всех сканеров с вашими API ключами:

## 1. Установите переменные окружения

```bash
# Основные сканеры
export ETHERSCAN_KEY="ваш_etherscan_api_ключ"
export BSCSCAN_KEY="ваш_bscscan_api_ключ"
export POLYGONSCAN_KEY="ваш_polygonscan_api_ключ"

# Дополнительные сканеры
export ARBISCAN_KEY="ваш_arbitrum_api_ключ"
export BASESCAN_KEY="ваш_base_api_ключ"
export BLASTSCAN_KEY="ваш_blast_api_ключ"
export FTMSCAN_KEY="ваш_fantom_api_ключ"
export GNOSISSCAN_KEY="ваш_gnosis_api_ключ"
export LINEASCAN_KEY="ваш_linea_api_ключ"
export OPTIMISM_ETHERSCAN_KEY="ваш_optimism_api_ключ"
export OKLINK_KEY="ваш_xlayer_api_ключ"
```

## 2. Или создайте файл .env в корне проекта

```bash
# .env файл
ETHERSCAN_KEY=ваш_etherscan_api_ключ
BSCSCAN_KEY=ваш_bscscan_api_ключ
POLYGONSCAN_KEY=ваш_polygonscan_api_ключ
ARBISCAN_KEY=ваш_arbitrum_api_ключ
BASESCAN_KEY=ваш_base_api_ключ
BLASTSCAN_KEY=ваш_blast_api_ключ
FTMSCAN_KEY=ваш_fantom_api_ключ
GNOSISSCAN_KEY=ваш_gnosis_api_ключ
LINEASCAN_KEY=ваш_linea_api_ключ
OPTIMISM_ETHERSCAN_KEY=ваш_optimism_api_ключ
OKLINK_KEY=ваш_oklink_api_ключ
```

## 3. Запустите полное тестирование

```bash
cd examples
python3 test_scanner_methods.py
```

## 4. Анализируйте результаты

После завершения тестирования будут созданы файлы:

- `scanner_methods_summary.md` - Краткий обзор всех сканеров
- `scanner_methods_detailed.md` - Детальные результаты по каждому методу
- `scanner_methods_results.json` - Сырые данные для анализа
- `scanner_methods_test.log` - Подробные логи выполнения

## Ожидаемые результаты

С настроенными API ключами вы должны увидеть:

- **Работающие сканеры**: 80-90% от общего числа
- **Успешные методы**: 70-90% в зависимости от сканера
- **Модули с лучшей поддержкой**: `proxy`, `account`, `stats`
- **Проблемные модули**: `token`, `gas_tracker` (не все сканеры поддерживают)

## Анализ проблем

Если какой-то сканер не работает:

1. **Проверьте API ключ**: правильно ли настроена переменная окружения
2. **Проверьте лимиты**: не превышены ли лимиты запросов
3. **Проверьте сеть**: доступны ли эндпоинты сканера
4. **Проверьте логи**: в `scanner_methods_test.log` есть детальная информация

## Особенности сканеров

- **Flare Explorer**: Работает без API ключа, но поддерживает ограниченный набор методов
- **X Layer (OKLink)**: Использует заголовок `OK-ACCESS-KEY` вместо параметра `apikey`
- **Optimism**: Использует поддомен `optimistic.etherscan.io`
- **Тестовые сети**: Некоторые могут иметь проблемы с DNS (например, `api-test.etherscan.io`)

Результаты тестирования покажут вам точную совместимость каждого метода с каждым сканером! 