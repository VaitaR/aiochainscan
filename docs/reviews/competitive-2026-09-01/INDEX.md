# Конкурентный анализ explorer-библиотек — сентябрь 2026

Сводный отчёт: 4 проекта, изучены по исходному коду (клоны в `/tmp/aiochainscan-competitors/`, depth 60), сверены с фактическим состоянием aiochainscan v0.6.0. Отчёты по каждой библиотеке: [01-blockparty.md](01-blockparty.md) · [02-safe-eth-py.md](02-safe-eth-py.md) · [03-etherscan-api-ts.md](03-etherscan-api-ts.md) · [04-blockscout-mcp-server.md](04-blockscout-mcp-server.md).

## TL;DR

Прямых конкурентов уровня aiochainscan (async + пагинация + стриминг + мульти-сканеры) на рынке **нет**:

- **blockparty** — единственный с реальной multi-provider fallback и типизированными ответами, но без пагинации вообще, с мёртвым retry, без таймаутов; beta, 1 звезда, 6 коммитов.
- **safe-eth-py** — зрелый, но explorer-клиенты — периферия (4 метода суммарно), без пагинации, async второсортный; конкурент только в нише «метаданные контракта».
- **etherscan-api (TS)** — образцовая нормализация ошибок и транспортные security-харды, но нет retry/лимитера/кэша/пагинации; Etherscan-only.
- **blockscout/mcp-server** — не конкурент, а **эталон агентной подачи данных**; наш `mcp_server.py` (3 строковых tool) против их 16 tools с конвертами, курсорами, curation — самый большой разрыв из всех.

Наши устойчивые преимущества, которых нет ни у кого: streaming-пагинация с постоянной памятью, `get_all_*`, progress-коллбеки, Rust fastabi (ABI-декодирование + keccak), Polars/Arrow экспорт, ENS, SmartContract (iter_events), NodeReal BSC, 520+ офлайн-тестов, mypy strict в CI.

## Сравнительная матрица

| Критерий | aiochainscan 0.6.0 | blockparty 0.7.5 | safe-eth-py 7.24 | etherscan-api 12.0.3 (TS) | blockscout/mcp 0.18.1 |
|---|---|---|---|---|---|
| Async / Sync | async | async + sync (копипаста) | async дубли с `async_`-префиксом | async (ESM) | async |
| Пагинация get-all | ✅ + streaming | ❌ (limit=10) | ❌ | ❌ | курсоры + next_call |
| Multi-provider fallback | ❌ | ✅ (без памяти) | ❌ | ❌ | ❌ (PRO-only) |
| Rate limiter | ✅ aiolimiter burst=1 | ✅ bucket per (provider,key), тиры | ❌ | ❌ | кредиты PRO (advisory) |
| Retry | ✅ tenacity, 5 попыток | ❌ (мёртвый код) | sync-only `sleep(5)` | ❌ | GET ×3, 0.5/1s |
| Кэш | только ENS | ✅ TTL 30s (баг коллизии) | ❌ | ❌ | ✅ TTL/LRU (мало) |
| Типизация ответов | сырые dict | ✅ pydantic ~30 моделей | 1 dataclass | TS-типы, без runtime | pydantic + curation |
| Сетей | 35 (+NodeReal BSC) | 708 (генерируемый снапшот) | 2213 enum / ~130 Blockscout | числовой chainid | PRO-цепи |
| Keyless-провайдеры | BlockScout | ✅ Routescan+Blockscout | Blockscout | ❌ | PRO (ключ нужен) |
| Verify контрактов | multi-step workflow | ❌ | косвенно (metadata) | ✅ широкая семья | ABI/inspect/read |
| Token holders | ❌ | ✅ list/count/top | ❌ | ❌ | holdings адреса |
| ENS | ✅ | ❌ | отдельный клиент | ❌ | tool (chain 1) |
| Стриминг/декодирование | ✅ fastabi, Arrow | ❌ | ❌ | ❌ | decoded input в tx-info |
| DataFrame | ✅ Polars/Arrow | ❌ | ❌ | ❌ | ❌ |
| MCP-сервер | 3 строковых tool | ❌ | ❌ | ❌ | ✅ 16 tools, эталон |
| Пулы/таймауты/лимиты ответа | ✅ (64MiB cap) | ❌ таймаутов | ✅ env | ✅ (50MB cap) | ✅ таймауты |
| Тесты | 520+ офлайн, моки | 143 офлайн (sync хромает) | 15 live-network | ~561 офлайн | офлайн |
| Активность | живой | ❄ 5+ недель, beta | ✅ релизы 1–2 нед | ❄ 2 месяца | ✅ активный |

## Продуктовый бэклог для aiochainscan

Приоритизация по «ценность × дешевизна» с учётом того, что уже в `docs/ROADMAP.md` (adaptive retry 2.1, multi-address batch 3.3, finality cache 4.1, Redis 4.2, GraphQL 5.1, Alchemy/Infura 6.x, WebSocket 7.1 — не дублируем).

### P0 — брать в ближайший релиз

1. **Multi-provider fallback с памятью** (`ProviderSet`-подобный уровень над сканерами): порядок провайдеров, fallback-eligible классификация (rate-limit/5xx/ключ/«цепь не поддержана на free-плане» — не фатал), warnings, `PoolExhaustedError[(provider, exc)]`, штамп «кто ответил». Обязательно **лучше blockparty**: sticky-provider + cooldown/circuit breaker, учёт `retry_after`. Референсы: `blockparty/pool/_base.py:254-277`, `backends/_errors.py:23-56`, `client/async_client.py:159-230`.
2. **Поллинг-хелперы**: `wait_for_transaction(txhash, timeout, interval)`, `wait_for_verification(guid)`, `wait_for_block(n)` — нет ни у одного конкурента при очевидном спросе. Строится поверх `get_transaction_status`/`check_transaction_status`.
3. **Token holders**: `get_token_holders` / `get_top_token_holders` / `get_token_holder_count` (Etherscan `tokenholderlist`/`topholders`; Blockscout v2 `/token/{addr}/holders`). Закрывает пробел vs blockparty; стримингом поверх нашей пагинации получится сильнее, чем у них.
4. **Ревизия MCP-сервера по образцу Blockscout MCP** (детальный план в [04](04-blockscout-mcp-server.md#6-что-позаимствовать--план-для-aiochainscanmcp_serverpy)): конверт `ToolResponse{data, notes, instructions, pagination, content_text}`, opaque-курсор + `next_call`, curation/truncation, `get_address_overview`, `get_transaction_info` с fastabi-декодированием, `read_contract` с авто-ABI (у нас это получится лучше ихнего), `lookup_token`, `list_chains`.
5. **Произвольный base_url / self-hosted Blockscout + валидация цепи**: `from_config('blockscout_v2', 'https://my-blockscout.internal')`; `GET /v2/chainlist` с кэшем для etherscan-валидации chain_id (референс `safe-eth-py/etherscan_client_v2.py:86-138` — но с кэшем и таймаутом).

### P1 — следующий за ним

6. **Опциональные типизированные ответы** (`extra="typed"`): pydantic-модели поверх текущих dict (не ломая контракт), hex-осведомлённые типы (`CoercedInt`), конверт с полем `provider`. Референс: `blockparty/models/responses.py`, `_types.py:24-45`.
7. **Фронтенд-ссылки от ответившего провайдера** (`urls_for(tx_hash)` после fallback) — референс `blockparty/urls/builder.py`.
8. **Единая `ContractMetadata(name, abi, implementation, partial_match)`** с fallback-цепочкой провайдеров (Etherscan → Blockscout; Sourcify — кандидат в сканеры) — референс `safe-eth-py/contract_metadata.py`.
9. **Хелперы конверсий** (`wei_to_ether`, `hex_to_int`, `to_datetime`) — «Etherscan отдаёт строки» — все конкуренты отдают сырые строки; module-level утилиты сделают нас удобнее всех.
10. **Исторические данные**: historical balance / token balance history (Etherscan `balancehistory`, Blockscout v2 coin-balance-history) — есть у blockparty/Blockscout MCP, у нас нет.
11. **AdvancedFilter Etherscan V2** (`from`/`to`/`fromto_opr`) в account-SPECS — новая V2-поверхность, есть в etherscan-api, у нас нет.

### P2 — по мере роста

12. Генератор реестра сетей из публичных chain-list API → бандл-снапшот + кастомный JSON (модель blockparty; под наш `chain_registry.py`).
13. Синхронная тонкая обёртка (`SyncChainscanClient` = `asyncio.run` мост; НЕ копипаста как у blockparty — 978×2 строк, 5 файлов на эндпоинт).
14. Docs-сайт MkDocs (уже в ROADMAP 9.1 — приоритизировать: у blockparty/etherscan-api docs-сайты, у нас 40+ разрозненных .md).
15. Транспортные харды: отказ cleartext (ключ не ходит по http), гарантия отсутствия ключа в текстах исключений (референс `etherscan-api/src/transport.ts:52-58`); 64MiB cap у нас уже есть.
16. Rate-limit тиры как пресеты (FREE/PRO rps/rpd) поверх `AioLimiterAdapter` — референс `blockparty/ratelimit/tiers.py`.

### Чего не делать (анти-паттерны конкурентов)

- Ручная sync/async копипаста (blockparty) — если делать sync, то только тонкий мост.
- `None` на любую ошибку и rate-limit-детект по подстроке (safe-eth-py).
- Кэш с ключом без провайдера/URL (blockparty баг коллизии) и кэш без eviction.
- Хардкод-словарь из сотен Blockscout-инстансов с ручным сопровождением (safe-eth-py) — только динамическая база + реестр.
- Раздутые docstring'и вместо серверных instructions/ресурсов в MCP (Blockscout пошли правильным путём).

## Методология

Клоны: `git clone --depth 60` (2026-09-01), метаданные GitHub API (звёзды/форки/даты). Пять параллельных субагентов: по одному на каждого конкурента + инвентаризация aiochainscan (публичный API, сканеры, инфраструктура, extras, ROADMAP). Все утверждения снабжены file:line-ссылками на исходники в отчётах по библиотекам.
