# Конкурентный отчёт: blockparty (DefiDebauchery)

> Дата: 2026-09-01 · Клон: `/tmp/aiochainscan-competitors/blockparty` · v0.7.5 (beta)
> GitHub: 1 звезда, 0 форков, 6 коммитов (первый 2026-03-19, последний 2026-07-23), MIT, Python ≥ 3.10
> Заявление из обзора: «единый интерфейс Etherscan → Routescan → Blockscout с авто-переключением» — подтверждено кодом, но с оговорками (см. слабые места).

## Вердикт vs aiochainscan

**У них лучше:**
1. **Multi-provider fallback** — единственный из рассмотренных с рабочей машиной переключения провайдеров: итерация по `ProviderSet`, fallback-eligible классификация ошибок (rate limit, 5xx, невалидный ключ, «цепочка не поддержана на free-плане»), warnings при переключении, `PoolExhaustedError` со списком `(provider, exception)` (`src/blockparty/client/async_client.py:159-230`, `pool/_base.py:254-277`, `backends/_errors.py:23-56`).
2. **Общий rate-limit бюджет per (provider, api_key)** — token bucket c реестром, шарится между клиентами одного `ProviderSet`; тиры тарифов (Etherscan FREE 3rps/100k … PRO 30rps/1M, Routescan ANONYMOUS 2rps/10k) + `CustomRateLimit` (`ratelimit/budget.py`, `ratelimit/registry.py:23-49`, `ratelimit/tiers.py`).
3. **708 сетей из коробки** — снапшот `registry/data/chains.json`, генерируется CLI из трёх публичных chain-list API с majority-vote merge (`registry/sources.py:223-267`, `registry/generate.py`); keyless Routescan и keyless Blockscout работают без ключа.
4. **Pydantic-модели ответов + штамп провайдера** — каждый ответ — конверт `ExplorerResponse[T]` с полем `provider` (кто ответил после fallback); hex-осведомлённый `CoercedInt` (`models/responses.py:28-60`, `_types.py:24-45`).
5. **Фронтенд-ссылки**: `urls_for(resp.provider)` строит ссылки именно того эксплорера, который ответил (`client/_base.py:104-141`, `urls/builder.py:55-105`).
6. **Endpoint-покрытие шире в точках**: `get_token_holder_list`, `get_token_holder_count`, `get_top_token_holders`, `get_token_info` (соцсети/цена/логотип), `get_historical_balance`, `get_historical_token_balance/supply`, полный набор topic0..3 + все операторы в `get_logs`, daily-stats generic-метод (`client/_endpoints.py:212-562`).

**У них хуже:**
1. **Пагинации нет вообще** — grep по `get_all|paginate|iterator` пуст; дефолт `limit=10`. Для аналитических задач библиотека не годится. Наше ключевое преимущество (streaming, `get_all_*`, progress) у них отсутствует полностью.
2. **Retry — фикция**: `RetryConfig` с exponential backoff — мёртвый код, нигде не подключён (`client/_middleware.py:69-104`); фактически одна попытка на провайдера → fallback. Adaptive rate-limit по `X-Ratelimit-*` заголовкам тоже мёртвый код — транспорт выбрасывает заголовки.
3. **Fallback без памяти**: каждый запрос снова стартует с первого провайдера; нет sticky/cooldown/circuit breaker → при глобальном rate limit провайдера каждый запрос платит лишний round-trip.
4. **Баг кросс-провайдерской коллизии кэша**: ключ кэша — только параметры запроса, без URL/провайдера; два keyless-провайдера дают одинаковый ключ → ответ Blockscout может отдаться как «Routescan», причём cache-hit парсинг вне try/except — `ValidationError` летит пользователю напрямую (`_middleware.py:37-41`, `async_client.py:186-191`).
5. **Нет таймаутов** — голые сессии `aiohttp.ClientSession()`/`requests.Session()` без timeout (вечное зависание); кэш без max-size (утечка памяти); sync/async — ручная копипаста 978×2 строк (5 файлов на новый эндпоинт).
6. Нет contract verify, нет proxy-модуля (eth_call/eth_getBalance), нет `get_block(by number)`, нет NFT-метаданных.

**Удобнее:** из коробки «взял и работает на любой цепочке без ключа» (Routescan/Blockscout keyless + реестр 708 сетей) и валидация в типизированные модели. Удобнее для простых одностраничных запросов; для реальных данных (выгрузки, стриминг) — хуже нас во всём.

## Детальный анализ

### 1. Архитектура

Строгая слоистая структура (`src/blockparty/`):

| Слой | Файлы | Ответственность |
|---|---|---|
| Transport | `client/_transport.py` | «Глупая труба»: GET + params → JSON dict. aiohttp/requests/httpx, маппинг исключений в `TransportError/TransportTimeout/TransportConnectionError/TransportHTTPError` |
| Client core | `client/_base.py`, `_endpoints.py`, `_middleware.py`, `_params.py`, `async_client.py`, `sync_client.py` | Резолв провайдеров, кэш, rate limit, fallback, парсинг |
| Backends | `backends/_base.py`, `etherscan.py`, `routescan.py`, `blockscout.py`, `_errors.py` | Абстракция провайдера: параметры, нормализация, классификация ошибок |
| Pool | `pool/_base.py`, `async_pool.py`, `sync_pool.py` | `ProviderCredential`/`ProviderSet`, пул клиентов по chain_id |
| Rate limit | `ratelimit/budget.py`, `registry.py`, `tiers.py` | Token bucket + реестр + тиры тарифов |
| Registry | `registry/chain_registry.py`, `sources.py`, `generate.py`, `data/chains.json` | 708 сетей: lookup, поиск, CLI-регенерация |
| URLs | `urls/builder.py` | Фронтенд-ссылки эксплорера |

Публичный API (`__init__.py:69-147`): `AsyncBlockpartyClient`/`SyncBlockpartyClient`, `AsyncBlockpartyPool`/`SyncBlockpartyPool`, `ProviderSet`/`ProviderCredential`, `ChainRegistry`, `ExplorerURLs`, тиры, 11 исключений, 3 warnings-класса, ~30 Pydantic-моделей.

Бэкенды — stateless: `ExplorerBackend` — Protocol (`name`, `build_request_params()`, `normalize_internal_tx()`, `parse_error()`). Etherscan/Routescan — пустые синглтоны (URL-различия живут в реестре: Etherscan v2 gateway `api.etherscan.io/v2/api?chainid=N`, Routescan — chain_id в пути `api.routescan.io/v2/network/{net}/evm/{chain_id}/etherscan/api`). Blockscout переопределяет нормализацию internal-tx (`transactionHash→hash`, `callType→type`) и разбор ошибок (успех = `message=="OK"` или result-список).

Fallback: итерация по `self._resolved`, `TransportHTTPError` → `is_fallback_eligible()`, `TransportError` → всегда fallback; ошибки парсинга → fallback на всё, кроме `InvalidAddressError` и `PremiumEndpointError`. Каждый fallback эмитит `FallbackWarning`/`AuthFallbackWarning`. Исчерпание — `PoolExhaustedError(errors)`. Штамп провайдера: `result.provider = rp.credential.type`. Важно: выбор провайдера **не запоминается** между запросами.

### 2. Функциональная матрица (44 эндпоинта)

Декларативный реестр `ENDPOINT_REGISTRY` (`client/_endpoints.py:212-562`) + обёртки-методы в обоих клиентах.

- **Account (17)**: normal/internal txs (по адресу/hash/range), ERC-20/721/1155 transfers, `get_balance` (мультиадрес до 20), `get_historical_balance`, `get_address_token_balance`, `get_address_nft_inventory`, `get_mined_blocks`, `get_beacon_withdrawals`, `get_funded_by`, `get_deposit_transactions`, `get_withdrawal_transactions`, `get_plasma_deposits`.
- **Contract (3)**: abi, source_code, creation (до 5 адресов). **Verify НЕТ.**
- **Transaction (2)**: status, receipt status. **Block (3)**: reward, countdown, block-no-by-time (блока по номеру нет).
- **Logs (1)**: topic0..topic3 + все операторы `topic0_1_opr…topic2_3_opr`.
- **Token (8)**: balance, historical balance, supply, historical supply, **holder list, holder count, top holders, token info** (соцсети, цена, image).
- **Stats (8)**: eth_price, eth_supply/supply2, node_count, **daily-stats generic-метод** (динамический `action` для всех `daily*`), chain_size, eth_daily_price, chainlist.
- **Pool** делегирует только 9 из 44 методов (остальные — через `pool.get_client(chain_id)`).

Сети: **708 цепочек** в бандл-снапшоте (blockscout 627 / routescan 70 / etherscan 64), регенерация CLI из chain-list API, `SUPPORTED_CHAINS.md` автогенерируется. Routescan без ключа — явный кейс (`ProviderCredential(type="routescan")`, tier ANONYMOUS 2rps/10k rpd).

### 3. Инфраструктура запросов

- **Retry**: заявлен, не подключён (мёртвый `RetryConfig`).
- **Rate limit**: token bucket на (provider, api_key), шарится через реестр; тиры; rpd хранится, но не энфорсится; `update_from_headers()` для Blockscout — мёртвый код.
- **Кэш**: in-memory, TTL 30s (default), ключ = sha256 параметров (без провайдера — баг), `force_refresh=True` bypass, per-client, без eviction.
- **HTTP**: aiohttp (default)/httpx async; requests/httpx sync; инъекция пользовательской сессии (`wrap_*_transport`), `owns_transport=False`; Pydantic ≥ 2.12 обязателен.
- **Ошибки**: чистая иерархия `BlockpartyError` → {ConfigurationError, ChainNotFoundError, ExplorerNotFoundError, ExplorerAPIError → {InvalidAPIKey, RateLimit, PremiumEndpoint, ChainNotSupported, InvalidAddress}, PoolExhaustedError} + warnings в стиле urllib3.

### 4. DX и качество

- Sync+async — ручная копипаста (978×2 строк), CONTRIBUTING требует правки 5 файлов на эндпоинт.
- `py.typed` есть, `mypy strict = true` в pyproject, **но mypy не в CI** (только ruff + pytest 3.10–3.13).
- Тесты: 143 в 14 файлах, полностью офлайн (мок-транспорты в conftest — хороший шаблон), но sync-клиент почти не тестируется (19 vs 6 тестов); `live_test.py` упомянут в CONTRIBUTING, но в репо отсутствует.
- Доки: Sphinx + furo на Read the Docs, полный API-reference. README аккуратный.

### 5. Слабые места (сводка)

Нет пагинации/стриминга; retry и adaptive headers — мёртвый код; fallback без памяти (нет cooldown); коллизия кэша между keyless-провайдерами + неперехваченный ValidationError на cache-hit; нет таймаутов; кэш без границ; ручная sync/async дубликация; нет verify/proxy/block-by-number/NFT-метаданных; Beta, 6 коммитов, 1 звезда, 5+ недель без движения.

### 6. Что позаимствовать (референсы для нашего бэклога)

1. `ProviderSet` + shared per-(provider, key) token bucket + тиры — `pool/_base.py:48-69,140-183`, `ratelimit/registry.py:23-49`, `ratelimit/tiers.py`. Обязательно добавить то, чего у них нет: sticky-provider + cooldown.
2. Декларативный `ENDPOINT_REGISTRY` + `ParamSpec` (перевод имён параметров, comma-join списков с валидацией, ResponseShape-dispatch) — `client/_endpoints.py:79-167,212-562`, `client/_params.py:10-38`. Каркас, поверх которого у нас тривиально строится и стриминг.
3. Машина fallback с классификацией ошибок и warnings: `backends/_errors.py:23-56`, `pool/_base.py:254-277`, `client/_base.py:149-160`, `exceptions.py:115-126`. Особо ценен паттерн «free-план не поддерживает цепочку → fallback-ошибка, а не фатал» (`ChainNotSupportedError`, `exceptions.py:89-100`).
4. Генератор реестра сетей из публичных chain-list API + бандл-снапшот + кастомный JSON — `registry/sources.py`, `registry/generate.py`, `registry/chain_registry.py:44-66`.
5. `urls_for(resp.provider)` — фронтенд-ссылки от фактически ответившего провайдера — `client/_base.py:104-141`, `urls/builder.py:55-105`.

Бонус: `CoercedInt` с hex-коэрцией (`_types.py:24-45`); Protocol-транспорты с инъекцией сессии + одноимённые мок-транспорты в тестах (`_transport.py:249-326`, `tests/conftest.py`).
