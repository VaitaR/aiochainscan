# Конкурентный отчёт: etherscan-api (sebs) — TypeScript/Node.js

> Дата: 2026-09-01 · Клон: `/tmp/aiochainscan-competitors/etherscan-api` · v12.0.3 (релиз 2026-07-02, последний коммит — там же; на дату отчёта 2 месяца тишины)
> GitHub: 551 звезда, 206 форков, MIT, ESM-only, Node ≥ 20, нулевые runtime-зависимости
> ~561 тест, TypeDoc-сайт на GitHub Pages. Разработка AI-ассистированная (массовые `Co-Authored-By: Claude Opus 4.8` в changelog).

## Вердикт vs aiochainscan

**У них лучше:**
1. **Центральная нормализация ошибок с различением «пусто» ≠ «ошибка»**: единый `EtherscanError{status, result}`, но `No transactions found` резолвится пустым списком, а не исключением (`src/get-request.ts:50-82`, `src/errors.ts:10-22`). Мелочь, радикально упрощающая пользовательский код.
2. **`resolveChainId` с кураторским map + списком мёртвых сетей**: имя сети → chain_id, мёртвые (ropsten/goerli) — **ошибка с подсказкой**, а не тихий фолбэк; принцип в коде: «silently switching networks on a blockchain client is dangerous» (`src/chains.ts:26-78`).
3. **Security-харды транспорта** — единственные среди конкурентов: cap размера ответа 50 МБ с абортой стрима, отказ идти по `http://` (чтобы ключ не утёк), гарантия что apikey не попал в сообщение об ошибке, вырезание `__proto__`/`constructor`/`prototype` из passthrough-параметров (`src/transport.ts:52-88`, `src/get-request.ts:32-47`, тесты `transport.test.js:108-126`).
4. **Рукописные типизированные shape'ы на ~25 эндпоинтов** (`src/results.ts`) с осознанным правилом «все скаляры — строки, как в API» и `unknown` для нестабильных JSON-RPC-объектов; строгий tsconfig.
5. **Аккуратный V2-миграционный UX**: старый `pickChainUrl()` экспортируется как функция, которая всегда бросает с подсказкой мигрантам (`src/index.ts:12-18`); живой `usage.chainlist()` без ключа; `usage.getapilimit()` — проверка квоты ключа.
6. **Качество тестовой стратегии**: 561 тест на нативном `node:test` без тестовых зависимостей, мок на transport-seam (4-й аргумент `init`), реальный транспорт тестируется на локальном http-сервере, один эндпоинт = один файл.

**У них хуже:**
1. **Нет retry, rate limiting и кэша вообще** — grep по `src/` пуст; всё перекладывается на пользовательский transport (README прямо это говорит). Для rate-limited API (5 rps free) — заметный пробел.
2. **Нет автоматической пагинации/стриминга/async-итераторов** — только дефолты `page=1, offset=100`; выкачать всю историю адреса нельзя.
3. **Нет поллинга** — ни `wait_for_tx`, ни poll-хелпера verify-GUID; только ручной `while`-цикл в examples. (Спрос есть, реализации нет ни у кого из конкурентов — whiteline.)
4. **Сырые ответы без конверсий** — wei в строках, hex-строки прокси; никаких wei→ether / hex→int хелперов; rантайм-валидации нет (типы — compile-time доверие).
5. **Покрытие неполное**: token holders/token info не реализованы, NFT — только трансферы, daily-stats нет.
6. **Жёсткая привязка к Etherscan**: baseUrl не конфигурируется, Blockscout/NodeReal отсутствуют; Node-only дефолтный транспорт (браузер — только через инъекцию).
7. Гигиена: устаревший `docs/tutorial.md` (учит CommonJS в ESM-only пакете), сломанный `test:live` на несуществующий каталог, закоммичен частичный `lib/`, пропущенный v11 и «100.0.0» в истории npm.

**Удобнее:** TS-эргономика (неймспейсы `api.account.txlist(...)`, автопереключение `balance`→`balancemulti` при массиве адресов), отличный docs-сайт с TypeDoc, copy-paste examples. Для Python-нас — не применимо напрямую, но паттерны ошибок/валидации chain/транспортных хардов переносимы.

## Детальный анализ

### 1. Архитектура и API

Фабрика `init(apiKey?, chain?, timeout?, request?)` возвращает объект-неймспейсы `log, proxy, stats, block, transaction, contract, account, gastracker, usage` (`src/init.ts:39-67`). V2: один хост `https://api.etherscan.io`, путь `/v2/api`, `chainid`-параметр; `apikey`/`chainid` инжектируются централизовано в defaults. Каждый модуль — DI-фабрика, получающая готовый `getRequest` (замыкание биндит `module:`); HTTP-транспорт инъекцируется 4-м аргументом `init`.

Типизация: строгая ручная (`strict`, `noUncheckedIndexedAccess`, …), без кодогенерации и zod; конверт `EtherscanResponse<T>` типирует только `result`.

### 2. Функциональная матрица (54 метода, 9 модулей)

- **account (13)**: txlist, txlistinternal (по txhash или адресу), tokentx, tokennfttx, token1155tx, balance/balancemulti (авто-выбор при массиве), tokenbalance, getminedblocks, txsBeaconWithdrawal, getdeposittxs/getwithdrawaltxs (L2), fundedby, txnbridge (Plasma). Плюс **AdvancedFilter (Beta)**: `from`/`to`/`fromto_opr` — фильтрация по отправителю/получателю (`src/account.ts:20-41`) — из новых фич Etherscan V2, у нас отсутствует.
- **contract (10)**: getabi, getsourcecode, getcontractcreation, **verify-семья: verifysourcecode (POST), verifyvyper, verifystylus (Rust/WASM), verifyzksyncsourcecode, checkverifystatus, verifyproxycontract + checkproxyverification** — заметно шире нашей (у нас CONTRACT_VERIFY есть как multi-step workflow; stylus/zksync/proxy-verify стоит сверить).
- **proxy (14)**: полный набор JSON-RPC (eth_call, eth_getStorageAt, eth_sendRawTransaction, eth_estimateGas, …) — у нас только 2.
- **log (1)**: getLogs с topic0–3 и всеми операторами.
- **block (4)**, **stats (6)**, **transaction (2)**, **gastracker (2)**, **usage (2)**: getapilimit + chainlist.

### 3. Инфраструктура запросов

Собственный транспорт на `node:https` (axios удалён в v12-rewrite): таймаут 10s, POST form-encoded, cap 50 МБ, отказ от cleartext, guard от double-settle. Retry/rate-limit/cache — нет. Ошибки: REST `status:"0"` → `EtherscanError`; «No transactions found» → пустой список; JSON-RPC `error` → `EtherscanError`; HTTP non-2xx → reject; невалидный JSON → reject.

### 4. DX

TypeDoc-сайт на GitHub Pages (автодеплой по тегам), examples.md на 203 строки, CI Node 20/22/24, publish + docs workflows. Проверка квоты ключа — `usage.getapilimit()`, но автотроттлинга на её основе нет.

### 5. Слабые места

См. вердикт: отсутствие retry/лимитера/кэша/пагинации/поллинга, сырые ответы, неполное покрытие, Etherscan-only, проблемы гигиены репозитория.

### 6. Что позаимствовать

1. Правило «пустой результат — не ошибка» + единый тип ошибки с полями `status`/`result` (`get-request.ts:50-82`) — сверить с нашим `network.py` (скрытый rate-limit в HTTP 200 мы уже распознаём; различение «пусто vs ошибка» стоит зафиксировать явно).
2. `resolve_chain_id` с кураторским map, списком мёртвых сетей и loud-fail на неизвестном имени (`chains.ts:26-78`) + живой `chainlist()` без ключа.
3. Транспортные харды: cap размера ответа (у нас уже есть 64MiB — сохранить), отказ cleartext, гарантия отсутствия apikey в сообщениях об ошибках/логах (у нас есть редакция в логах — расширить на сообщения исключений), защита от prototype-pollution-аналогов при passthrough-параметрах.
4. **Поллинг как библиотечный хелпер**: `wait_for_transaction(txhash, timeout, interval)` поверх receipt-status и `wait_for_verification(guid)` поверх checkverifystatus — нет ни у кого; дешёвая и заметная фича.
5. AdvancedFilter (`from`/`to`/`fromto_opr`) для account-эндпоинтов Etherscan V2 — проверить поддержку в наших SPECS; это заметное отличие V2-поверхности.
6. Тестовая стратегия: мок на transport-seam + тесты реального транспорта на локальном сервере, один assert на тест.
