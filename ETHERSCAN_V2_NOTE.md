# Etherscan V2 API Migration Note

## Проблема

При тестировании обнаружено, что **Etherscan V1 API устарел** и требует миграции на V2:

```
Response: {
  'status': '0',
  'message': 'NOTOK',
  'result': 'You are using a deprecated V1 endpoint, switch to Etherscan API V2'
}
```

## Что изменилось в V2

### URL и Authentication

**V1 API (устарел):**
```
URL: https://api.etherscan.io/api
Auth: Query parameter ?apikey=YOUR_KEY
```

**V2 API (актуальный):**
```
URL: https://api.etherscan.io/v2/api
Auth: Query parameter ?apikey=YOUR_KEY (да, V2 всё ещё использует query!)
Parameters: Требуется chainid в query (?chainid=1)
```

**Важно:** Несмотря на документацию, Etherscan V2 API **НЕ использует** заголовок `X-API-Key`. API ключ передается через query параметр `apikey`, как и в V1.

### Chain ID Support

V2 API использует один ключ для всех сетей:
```python
# Один ключ для всех
client = ChainProvider.etherscan(chain_id=1, api_key='KEY')    # Ethereum
client = ChainProvider.etherscan(chain_id=56, api_key='KEY')   # BSC
client = ChainProvider.etherscan(chain_id=137, api_key='KEY')  # Polygon
```

## Реализация в библиотеке

### ✅ Что уже сделано

1. **Автоматическая загрузка .env**
   - Файл `.env` загружается при импорте `aiochainscan.chains`
   - Поддерживаются переменные: `ETHERSCAN_KEY`, `ETHERSCAN_API_KEY`

2. **EtherscanV2 Scanner**
   - Использует правильный endpoint: `https://api.etherscan.io/v2/api`
   - Header authentication: `X-API-Key`
   - Добавляет параметр `chainid` в запросы

3. **ChainProvider API**
   - Метод `ChainProvider.etherscan(chain_id=...)` использует V2 scanner
   - Автоматическое чтение ключа из `ETHERSCAN_KEY`

### Код в `scanners/etherscan_v2.py`

```python
@register_scanner
class EtherscanV2(Scanner):
    name = 'etherscan'
    version = 'v2'
    auth_mode = 'header'
    auth_field = 'X-API-Key'

    def _build_request(self, spec, **params):
        # Добавляет chainid в параметры
        request_data = super()._build_request(spec, **params)
        request_data['params']['chainid'] = str(self.chain_info.chain_id)
        return request_data

    async def call(self, method, **params):
        # Использует V2 endpoint
        url = 'https://api.etherscan.io/v2/api'
        # ... отправка запроса с X-API-Key header
```

## Требования к API ключу

### ⚠️ Важно

Старые API ключи от V1 API **не работают** с V2 API:
```
Response: {'status': '0', 'message': 'NOTOK', 'result': 'Missing/Invalid API Key'}
```

### Решение

1. Зарегистрируйте **новый V2 API ключ** на https://etherscan.io/apis
2. Убедитесь, что выбрана опция "Etherscan API V2"
3. Добавьте ключ в `.env`:
   ```bash
   ETHERSCAN_KEY=ваш_новый_v2_ключ
   ```

## Альтернатива: BlockScout

Для разработки и тестирования рекомендуется использовать **BlockScout** - бесплатный, без API ключа:

```python
from aiochainscan import ChainProvider

# Работает без API ключа!
client = ChainProvider.blockscout(chain_id=1)  # Ethereum
client = ChainProvider.blockscout(chain='sepolia')  # Sepolia testnet

balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

### Поддерживаемые сети BlockScout

- Ethereum Mainnet (chain_id=1)
- Sepolia Testnet (chain_id=11155111)
- Optimism (chain_id=10)
- Arbitrum One (chain_id=42161)
- Base (chain_id=8453)
- Gnosis (chain_id=100)
- Polygon (chain_id=137)
- Scroll (chain_id=534352)
- Linea (chain_id=59144)

## Тестирование

### Проверка BlockScout (работает)

```bash
python examples/chain_provider_demo.py
```

Результат:
```
📊 Ethereum via BlockScout (chain_id=1):
   ✓ Balance: 29.589347 ETH (from BlockScout)
```

### Проверка Etherscan V2 (требует новый ключ)

```python
from aiochainscan import ChainProvider

client = ChainProvider.etherscan(chain_id=1)
# Требуется зарегистрированный V2 API ключ
```

## Документация Etherscan

- V2 API Docs: https://docs.etherscan.io/
- V1 to V2 Migration: https://docs.etherscan.io/v2-migration
- Get API Key: https://etherscan.io/apis

## Статус реализации

- ✅ Автозагрузка .env файла
- ✅ EtherscanV2 scanner с правильным endpoint
- ✅ Header authentication (X-API-Key)
- ✅ Chain ID в параметрах запроса
- ✅ ChainProvider.etherscan() использует V2
- ✅ BlockScout как бесплатная альтернатива
- ⏳ Требуется: Регистрация V2 API ключа пользователем

## Рекомендации

1. **Для разработки**: Используйте BlockScout (бесплатно, без ключа)
2. **Для production**: Зарегистрируйте Etherscan V2 API ключ
3. **Multi-chain**: Один Etherscan V2 ключ работает для всех сетей
4. **Fallback**: Реализуйте переключение BlockScout ↔ Etherscan
