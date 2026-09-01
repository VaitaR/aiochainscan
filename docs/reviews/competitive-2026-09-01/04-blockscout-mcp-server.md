# Конкурентный отчёт: blockscout/mcp-server (официальный)

> Дата: 2026-09-01 · Клон: `/tmp/aiochainscan-competitors/blockscout-mcp-server` · v0.18.1 (коммит 2026-08-05)
> GitHub: 44 звезды, 24 форка, активная разработка (244+ коммитов). Python ≥ 3.11, `mcp[cli]` (FastMCP), httpx, pydantic v2, web3, Mixpanel.
> Это не конкурент-библиотека, а **эталон агентной подачи данных** — прямой референс для нашего `mcp` extra.

## Вердикт vs aiochainscan

Наш текущий MCP-сервер (`aiochainscan/mcp_server.py`) — 3 инструмента (`get_wallet_balance`, `get_recent_transactions`, `get_token_portfolio`), каждый открывает свой `ChainscanClient`, ответы — плоские строки. Разрыв с Blockscout MCP — примерно как разрыв «single-page vs streaming» в основной библиотеке.

**У них лучше (паттерны для переноса):**
1. **16 инструментов с агентным контрактом** вместо 3 утилитарных: unlock-протокол, address overview, transactions/token transfers с age-фильтрами, NFT holdings, transaction info с декодированием, contract ABI + inspect source + read_contract, lookup token, chains list, direct_api_call как escape hatch.
2. **Стандартный конверт ответа** `ToolResponse{data, data_description, notes, instructions, pagination, content_text}` — вместо сырых строк: notes с лимитами/бюджетами, инструкции-мостки («дальше вызови …»), человекочитаемое резюме + structured output одновременно (`models.py:521-552`, `tools/common.py:730-846`).
3. **Opaque-курсоры + готовый `next_call`**: Base64URL от next-page-параметров; в ответе `pagination.next_call` — полный набор аргументов следующего вызова, LLM не нужно понимать схему пагинации (`tools/common.py:599-616,869-916`).
4. **Экономия LLM-контекста**: curation полей (только нужные, всё в строки), рекурсивная truncation с флагами `{value_sample, value_truncated}` (лимит 514 символов), выбрасывание raw_input при наличии decoded input, `content_text`-резюме для «summary-клиентов», лимит 7 результатов поиска (`tools/common.py:619-701`, `tools/transaction/_shared.py:44-52`, `server.py:159-187`).
5. **Устойчивость к частичным ошибкам**: `get_address_info` собирает 3 запроса через `asyncio.gather(..., return_exceptions=True)` — упавшие подзапросы попадают в `notes`, а не валят вызов (`tools/address/get_address_info.py:92-199`).
6. **«Умная пагинация»** для фильтрованных выборок: до 10 страниц API, пока не наберётся целевая страница отфильтрованных записей; исключение шумных типов (ERC-20/721/1155/404 из нативных транзакций) (`tools/transaction/_shared.py:130-198`).
7. **Unlock-протокол + skill-ресурсы**: `__unlock_blockchain_analysis__` раз в сессию отдаёт server_version + указатель на skill; справочник API раздаётся как MCP-ресурсы (`blockscout-mcp://skill/SKILL.md` + references), целостность проверяется при старте сервера (`server.py:149-156`, `resources/skill_resources.py:33-36,148-153`).
8. **Прогресс для долгих вызовов**: periodic progress каждые 15s с elapsed/hint в отдельной anyio-таске — у нас есть порт `ports/progress.py`, осталось подключить к MCP.
9. **LLM-дружественные ошибки**: человекочитаемые сообщения из JSON-API ошибок (title/detail/pointer), типизированные `ChainNotFoundError`/`ResponseTooLargeError`/`CreditsExhaustedError`/`InvalidCursorError` с советами («make a new request without the cursor»).

**У них хуже:**
1. **Только чтение** — все tools `readOnlyHint=True`.
2. **Жёсткая привязка к Blockscout PRO API** (`api.blockscout.com` + эффективный ключ) — self-hosted Blockscout и Etherscan-совместимые инстансы подключить нельзя. Наш сервер поверх мульти-сканерного клиента — принципиально шире.
3. Нет соединительного пула для PRO API (новый `httpx.AsyncClient` на каждый запрос); кэши in-memory per-process; контрактный кэш всего 10 записей.
4. ENS захардкожен на chain 1; нет единого «портфеля» (баланс/ERC-20/NFT — три разных вызова; сервер сам это признаёт в instructions); нет dedicated tools для internal txs и логов (всё через generic `direct_api_call` + handler'ы); ERC-721/1155 transfers — только через escape hatch.
5. `read_contract` требует от LLM передать ABI одной функции вручную — автофетч ABI не встроен (у нас `SmartContract` + fastabi могут дать это даром).
6. Session-gate/лимиты работают только в HTTP-режиме.

## Детальный анализ

### 1. Архитектура

`LoggingFastMCP(FastMCP)`; транспорт stdio по умолчанию, `--http` — stateless Streamable HTTP, `--rest` — зеркало tools как REST API (`/v1/<tool>`). CLI на typer. 16 tools регистрируются через `mcp.tool(structured_output=True, ...)` с обёрткой в `CallToolResult{structuredContent + text}`. Один файл = один tool; общие примитивы — `tools/common.py`; декораторный стек `@log_tool_invocation @pro_api_key_scope @session_gate @pro_api_credit_scope`.

Multichain через Blockscout PRO: `{pro_api_base_url}/{chain_id}/api/v2/...`; карта цепей из `/api/json/config` (TTL 300s + stale-fallback), каждая страница валидируется `ensure_chain_supported`. Дополнительные апстримы: BENS (ENS), Chainscout (список цепей), metadata-эндпоинт PRO (публичные метки адреса). Ключ — серверный env или per-request заголовок через ContextVar.

### 2. Поверхность данных (16 tools)

| Tool | Что делает |
|---|---|
| `__unlock_blockchain_analysis__` | инициализация сессии, instructions, skill-pointer |
| `get_block_info` / `get_block_number` | блок по number/hash (+txs по флагу); блок по datetime (getblocknobytime) |
| `get_address_by_ens_name` | ENS → адрес (chain 1) |
| `get_transactions_by_address` | advanced-filters: нативные tx + internal + вызовы контрактов, фильтры age_from/to/methods, умная довыборка страниц |
| `get_token_transfers_by_address` | ERC-20 transfers с age/token фильтрами |
| `get_tokens_by_address` / `nft_tokens_by_address` | ERC-20 холдинги с market data; NFT по коллекциям с curated-полями |
| `get_address_info` | gather: баланс + первая транзакция (возраст кошелька) + публичные метки; частичные ошибки → notes |
| `get_transaction_info` | tx + AA user-ops; decoded input приоритетнее raw; схлопывание token_transfers; content_text-резюме |
| `get_contract_abi` / `inspect_contract_code` | ABI; исходники двухфазно: дерево файлов → один файл (LRU+TTL кэш) |
| `read_contract` | eth_call через web3-пул; префлайт-проверка кодируемости; нормализация bytes → 0x-hex |
| `lookup_token_by_symbol` | поиск токена, лимит 7 результатов |
| `get_chains_list` | список цепей с substring-фильтром |
| `direct_api_call` | escape hatch к любому GET/POST PRO-эндпоинту; `ResponseTooLargeError` >100k символов; handler'ы curate поля для logs/summary/user-ops |

### 3. Агентные фичи

Unlock-протокол (последний коммит перенёс skill guidance в envelope instructions и урезал payload до `server_version`+`session_id` — тестируемый инвариант байт-в-байт); серверные instructions с правилами резолва `references/*` → MCP-ресурсы; прогресс 0/N и periodic; session-gate (free tier): HMAC-токены сессий, лимиты 5 вызовов/surface, бюджет-note в каждом ответе, refund при неудаче.

### 4. Инфраструктура

GET — до 3 попыток на `RequestError` (backoff 0.5/1.0s); POST — только ConnectError/ConnectTimeout. Таймауты: heavy 120s / light 20s. Rate limiting — нет; вместо него учёт кредитов PRO (заголовок `x-credits-remaining`, advisory < 5000, 402 → `CreditsExhaustedError` с «retrying will not succeed»). Телеметрия Mixpanel + community-эндпоинт, приватность: session_id маскируется, ключ — SHA-256 fingerprint, отключается env.

### 5. Слабые места

См. вердикт (read-only, PRO-only, нет пула, нет портфеля, read_contract без авто-ABI, truncation статический).

### 6. Что позаимствовать — план для `aiochainscan/mcp_server.py`

Готовые кирпичи у нас уже есть: `scanners/etherscan_v2.py`, `blockscout_v2.py`, `nodereal.py`, `chain_registry.py`, rate-limit/retry/cache-адаптеры, `services/pagination.py:normalize_items`, `decode.py` (fastabi), `services/ens_resolver.py`, `ports/progress.py`.

**Tools (по приоритету):**
1. `get_address_overview(chain_id, address)` — gather (баланс + первая tx/возраст + ENS + счётчик токенов), частичные ошибки → notes, instructions-мостки. Референс: `tools/address/get_address_info.py:92-199`.
2. `get_transactions(chain_id, address, age_from/блоки, method=None, cursor=None)` — умная довыборка страниц до целевого размера, фильтрация шумных типов, `next_call` с готовыми параметрами. Референс: `tools/transaction/_shared.py:130-198`, `tools/common.py:869-916`.
3. `get_transaction_info(chain_id, tx_hash)` — decoded input через наш fastabi, схлопывание transfers, human-readable value/fee, content_text. Референс: `tools/transaction/get_transaction_info.py:88-177`.
4. `get_contract_abi` + `read_contract` парой — автофетч ABI (лучше Blockscout: у нас SmartContract + fastabi), префлайт arity/encoding, `ContractLogicError` → человекочитаемая ошибка. Референс: `tools/contract/read_contract.py:160-227`.
5. `lookup_token(chain_id, symbol)` (лимит 7) + `list_chains(query)` поверх `chain_registry.py`; бонусом `get_block_number(chain_id, datetime)` — прямой маппинг на `get_block_by_timestamp`.

**Паттерны подачи (рефакторинг конверта ответа):**
1. `ToolResponse{data, data_description, notes, instructions, pagination, content_text}` вместо строк.
2. Opaque-курсор (Base64URL) + готовый `next_call` — ложится на `services/pagination.py`.
3. Curation полей + truncation с флагами `{value_sample, value_truncated}`, отсечение raw_input при decoded.
4. content_text-резюме + structured output одновременно; человекочитаемые суммы (decimals) + raw в `data`.
5. Instructions-мостки между tools; progress через `ports/progress.py`; серверные instructions + ресурсы-справочники вместо раздутых docstring'ов.
