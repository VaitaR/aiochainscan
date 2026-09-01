# Конкурентный отчёт: safe-eth-py (safe-global) — explorer-клиенты

> Дата: 2026-09-01 · Клон: `/tmp/aiochainscan-competitors/safe-eth-py` · v7.24.0 (HEAD 2026-09-01)
> GitHub: 193 звезды, 226 форков, MIT, релизы каждые 1–2 недели (7.22.1 → 7.23.0 → 7.24.0 за июль–август 2026)
> Оговорка: из пользовательского обзора — «EtherscanClientV2 + BlockscoutClient, Blockscout через native REST v2» — подтверждено, но **базовой абстракции `BaseExplorer` не существует**, а legacy Etherscan V1 удалён 2025-08-20 (PR #1888).

## Вердикт vs aiochainscan

**У них лучше:**
1. **Зрелость и поддержка** — проект Safe Global, 8 лет истории, релизы раз в 1–2 недели, дисциплина (uv `exclude-newer`, CodeQL, coveralls). Но: 49 из 60 последних коммитов — бот-коммиты реестра адресов Safe; сами explorer-клиенты меняются редко.
2. **Нормализованная `ContractMetadata` через разных провайдеров** — dataclass `ContractMetadata(name, abi, partial_match, implementation)` с per-provider извлечением proxy-implementation: Etherscan — поле `Implementation`, Blockscout — `implementations[0].address_hash`, Sourcify — свой (`contract_metadata.py:6-10`, `etherscan_client_v2.py:140-156`, `blockscout_client.py:183-202`). Один тип результата от трёх источников.
3. **Etherscan `GET /v2/chainlist`** + classmethods `get_supported_networks()` / `is_supported_network()` / `get_base_url()` (`etherscan_client_v2.py:86-138`) — валидация chain_id и маппинг «chain → explorer». Ходят в сеть при каждом вызове без кэша — это мы сделаем лучше.
4. **Enum `EthereumNetwork` на 2213 цепей** (`ethereum_network.py:9`) — самая полная карту цепей среди конкурентов.
5. **Env-конфигурация клиента**: `*_REQUEST_TIMEOUT` (дефолт 10 c), `*_MAX_REQUESTS` (пул `TCPConnector(limit_per_host=…)`, дефолт 100) (`etherscan_client_v2.py:43-45,233-238`).

**У них хуже (почти по всем осям explorer-SDK):**
1. **Поверхность explorer-клиентов мизерная**: Etherscan V2 — 3 содержательных метода (`get_contract_source_code/abi/metadata`), Blockscout — 1 (`get_contract_metadata`). Ни балансов, ни транзакций, ни логов, ни токенов, ни holders — grep по всему пакету подтверждает. Это вспомогалка для верификации контрактов Safe TX Service, а не explorer SDK. Как конкурент aiochainscan по функциональности — не конкурент.
2. **Пагинации нет вообще** — ни get-all, ни стриминга, ни одного list-эндпоинта в текущей версии.
3. **`None` на любую неудачу** — «нет данных», сетевая ошибка и исчерпанная квота неразличимы (`etherscan_client_v2.py:69-71`); rate-limit детектится строковым поиском `"Max rate limit reached" in result`, который на list/dict-ответах не срабатывает.
4. **Async второсортный**: методы-дубли с префиксом `async_` (не одинаковые имена!), **ретраев в async нет** (только sync `time.sleep(5)`-цикл), aiohttp-сессии не закрываются.
5. **Нельзя поставить клиенты отдельно**: зависимость от `safe_eth` целиком — `web3>=7`, `py-evm`, `safe-pysha3` — десятки мегабайт ради трёх HTTP-методов.
6. **Тесты клиентов — live-network** (требуют `ETHERSCAN_API_KEY`, `@pytest.mark.flaky(reruns=5)`), моков транспорта нет; запуск всего suite требует Django + Postgres + Ganache.
7. Blockscout: hand-maintained словарь ~130 URL с дублирующимися ключами (MANTLE_TESTNET, MODE, STORY_AENEID_TESTNET и др.), сопровождается бот-коммитами.

**Удобнее:** для единственного кейса «метаданные верифицированного контракта + proxy-implementation на любой сети» — да: одна строка, один нормализованный тип, keyless Blockscout. Для всего остального (аналитика, транзакции, токены, логи) — aiochainscan покрывает на порядок больше.

## Детальный анализ

### 1. Абстракция explorer-клиентов

Единой абстракции нет: `EtherscanClientV2` (`etherscan_client_v2.py:27`) и `BlockscoutClient` (`blockscout_client.py:21`) — независимые классы от `object`. Async-версии **наследуют** sync-классы, переопределяют транспорт (`_async_do_request`) и добавляют методы-дубли с префиксом `async_` (`async_get_contract_abi`); парсинг переиспользуется через общие `_process_*` статические методы. Единый интерфейс между Etherscan/Blockscout/Sourcify — неформальный duck-typing: `get_contract_metadata(address) -> Optional[ContractMetadata]`. ABC/Protocol нет, `clients/__init__.py` реэкспортирует всё плоским списком.

### 2. Функциональная матрица

| Клиент | Методы |
|---|---|
| `EtherscanClientV2` (+Async) | `get_supported_networks()`, `is_supported_network()`, `get_base_url()` (все — через живой HTTP `v2/chainlist` без кэша и таймаута), `get_contract_source_code()`, `get_contract_abi()`, `get_contract_metadata()` |
| `BlockscoutClient` (+Async) | `get_contract_metadata()` — `GET {base}/api/v2/smart-contracts/{address}`; карта `NETWORK_WITH_URL` ~130 инстансов |

Token holders, NFT, internal txs, logs, balances, token info — **отсутствуют полностью**. Pydantic не используется вовсе; адреса/Wei — сырые строки; единственная типизация — `ChecksumAddress` из eth_typing.

### 3. Инфраструктура запросов

- HTTP: sync `requests.Session` (Etherscan — с пулом `HTTPAdapter(10, 100)`, Blockscout — голый), async `aiohttp` + `TCPConnector(limit_per_host=100)`. Таймауты через env (дефолт 10 c).
- Rate limit: проактивного нет; реактивно — строка «Max rate limit reached» → `EtherscanRateLimitError`. Sync-ретрай: 3 попытки `time.sleep(5)`; **async без ретраев**. Retry-After / 429-заголовки не обрабатываются.
- Кэша нет; `is_supported_network` дёргает живой HTTP без таймаута на каждый вызов. Подмена `User-Agent: curl/7.77.0`.
- Ошибки: `EtherscanRateLimitError`, `BlockScoutConfigurationProblem`; `EtherscanClientConfigurationProblem` объявлен и никогда не используется (мёртвый код).

### 4. DX и качество

- `py.typed` есть, mypy в CI, но `check_untyped_defs` закомментирован; возвраты рыхлые (`Optional[Union[Dict, List, str]]`).
- 15 тест-методов на 4 клиента, все live-network со skip без ключа; моки отсутствуют.
- Релизы через GitHub release → PyPI (uv build/publish); версия динамическая (hatchling).

### 5. Слабые места (сводка)

Нет пагинации и list-эндпоинтов; крайне узкая поверхность; тяжёлые зависимости; None-на-всё; хрупкий строковый rate-limit-детект; async второсортный; live-тесты вместо моков; Django-обвязка для запуска тестов HTTP-клиентов.

### 6. Что позаимствовать

1. Multichain-паттерн «один хост + chainid» для Etherscan V2 (`etherscan_client_v2.py:54-58`) — у нас уже так; подтверждение, что per-chain карты хостов — тупик (их V1 на 492 строки удалён, Blockscout-словарь гниёт с дублями).
2. `GET /v2/chainlist` + `is_supported_network`/`get_base_url` — **с кэшем**, которого у них нет: готовая утилита валидации chain при `from_config`.
3. Нормализованная модель метаданных контракта через общего провайдера (`ContractMetadata`) — повторить на pydantic/dataclass и **добавить fallback-цепочку провайдеров** (Etherscan → Blockscout → Sourcify), которой у них тоже нет.
4. Blockscout native REST v2 — подтверждение жизнеспособности path-based `{host}/api/v2/…` с динамической базой (не хардкод-словарь); whiteline: `/token/{addr}/holders`, `/tokens/{addr}/instances`, `/transactions`, `/logs` — конкурент эти данные не отдаёт вовсе.
5. Env-конфигурация таймаутов/пулов с документацией — улучшить типизированным config-объектом.

**Анти-паттерны, которых избегать:** reactive rate-limit по подстроке; `None`-на-всё; блокирующий `time.sleep` в sync-предке, от которого наследуется async-класс без ретраев; live-network тесты; обязательная тяжёлая обвязка для тестов.
