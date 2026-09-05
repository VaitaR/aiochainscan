# Bug Hunt Round 2 — 2026-09-05 (после фиксов раунда 1)

Второй раунд аудита поведения aiochainscan. Выполнен поверх коммитов с фиксами
`6580ff9` (4 high + 13 medium) и `e07c74e` (~20 low), HEAD `e07c74e`, дерево чистое.
Первый раунд: [docs/BUG_HUNT_2026-09-05.md](./BUG_HUNT_2026-09-05.md).

## Методология

- 6 субагентов: (1) ревью самих фиксов, (2) стресс конкурентности/отмен/жизненного цикла,
  (3) глубокий аудит Rust-тира fastabi (в раунде 1 только скинут), (4) полный свип
  реестра цепей/конфига/URL/CLI, (5) property-фаззинг ABI/convert/курсоров, (6) обход
  файлов, не покрытых в раунде 1.
- Каждому агенту выдан список из 47 известных находок (`/tmp/bughunt/KNOWN_FINDINGS.md`)
  с запретом переоткрывать; воспроизводящееся известное — в отдельную секцию
  «Incomplete fixes», а не как новое.
- База на HEAD: **pytest 1598 passed / 63 skipped**, mypy --strict и ruff чисты.
- Пробы офлайн (фейковый транспорт), каталоги `/tmp/bughunt/{fixreview,concurrency,rust,sweep,fuzz,uncovered,verify}`.
  Одно исключение, вскрытое самоотчётом агента по фиксам: на старте два случайных
  read-only GET до живого Etherscan с bogus-ключом (ответ «Invalid API Key») до перехода
  на фейки; все цитируемые результаты — офлайн.
- Ключевые находки перепроверены координатором (см. пометки «верифицировано»).

**Итог раунда: 1 critical, 2 high, 9 medium, ~18 low/info.**

---

## Часть I. Вердикт по фиксам раунда 1

Ревью обоих коммитов хунка-за-хункой, ~60 адресных офлайн-проб (включая повтор точных
раунд-1 репро и мутации «на шаг дальше» фикса).

**Общий вердикт: фиксы качественные.** Все 4 high и 12 из 13 medium исправлены полностью
и подтверждены пробами; из ~20 low исправлено 17. Классы исключений для классификатора
пула сохранены всюду, куда удалось ударить (MethodNotDeclaredError→METHOD_UNDECLARED,
result-size refusal→FATAL, batch→ChainscanDataError). Затронутые наборы тестов зелёные.

| Находка | Вердикт | Суть |
|---|---|---|
| H1 guard+CancelledError | **OK** | Отмена больше не кэшируется, гвард перезаряжается; fatal — кэшируется как раньше |
| H2 pool per-method window | **OK** | `[etherscan, blockscout/v1]` теперь реально отдаёт holders через v1 |
| H3 NodeReal EVENT_LOGS | **PARTIAL** | См. N-M1 ниже: объявление верно, но «machinery splits the range» не выполняется |
| H4 «No logs found» | **OK** | Пустой лог → `[]`; реальные ошибки и «No … found because …» всё ещё ошибки |
| M1…M13 (12 шт.) | **OK** | Каждый пункт подтверждён пробой на HEAD |
| low #9 content-type | **PARTIAL** | `+json` принят; отсутствующий content-type всё ещё отклоняется (половина находки) |
| low #38 convert leniency | **НЕ ПРАВИЛСЯ** | `'1_0'`→10, `'２６'`→26, `True`→True, `'1e18'`→1 — воспроизводится |
| прочие low (~15) | **OK** | TTL=0, Retry-After (включая HTTP-date), %2e%2e, vv2, holesky+«test», V1 base_url, строковый end_block, topic-операторы (честный отказ, METHOD_UNDECLARED), unnamed calldata, analytics null, register_scanner env, read_contract truncation, add-scanner --save и т.д. |
| #43, #17, #11, #39, #42, #45, #47 | вне коммитов | Согласно их раунд-1 классификации (unreachable/suspected/info/policy) |

### Что фиксы сломали/недоделали (новое от ревью фиксов)

- **N-M1 [MEDIUM, неполный фикс H3]** `nodereal.py:88-97,581-584` + `pagination.py:739`:
  `RESULT_WINDOW_OVERRIDES={EVENT_LOGS: 50000}` объявлено верно (реестр и пул больше не
  называют NodeReal «полным провайдером» логов; usage-limit ретраится), но over-cap
  refusal `-32005 «logs count exceeds the limit 50000»` остаётся FATAL
  `ChainscanClientProxyError` и поднимается из `fetch` сквозь `_fetch_window` к вызывающему
  **сырой ошибкой после 1 запроса** — сплит диапазона не запускается, потому что машина
  гарантий сплитит только по *успешному* ответу `collected >= window`. В пуле FATAL
  запрещает failover, поэтому `[nodereal, etherscan]` не может передать широкий лог-запрос
  Etherscan, который умеет сплитить. Commit-claim «the guarantee machinery splits the
  range» не соответствует поведению. Фикс: переводить result-size refusal в overflow-сигнал
  (`_Overflow.AT_CAP`) для range-capable спек и/или классифицировать так, чтобы пул мог
  смаршрутизировать на «полного» провайдера.
- **low#9 half-done**: пустой content-type по-прежнему `ChainscanClientContentTypeError`
  (`network.py:742-748`).
- **Косметика от фикса H2**: гарантированный стрим, смаршрутизированный на
  completeness-capable члена, эмитит `ChainscanProviderSwitchWarning` с бессмысленной
  причиной `provider selection changed` (`pool.py:726`→`_maybe_warn_switch`). Роутинг
  осознанный (репо-тест оборачивает в `pytest.warns`), текст — нет.
- **Мелкие резидуалы**: `%252e%252e` проходит одиночный percent-decode (`base_url.py`);
  циклы курсора с периодом >512 больше не детектятся (осознанный tradeoff нового
  512-окна, задокументирован в коде); JSON-RPC batch-эвристика отвергает и top-level
  список plain `{'id','result'}` словарей (такой формы сейчас никто не шлёт);
  `token: null` в analytics даёт баланс в масштабе по умолчанию 18 — фикс так и
  предписывал, но это в tensions с «никаких догадок о масштабе».

---

## Часть II. Новые баги

### CRITICAL

**C1. Кривая строка типа в ABI убивает весь процесс (SIGABRT) на `[fastabi]`** — верифицировано координатором
- Где: `fastabi/Cargo.toml:38` (`panic = "abort"` в release) + `fastabi/src/lib.rs:99`
  (`serde_json::from_str::<Abi>` на ABI от вызывающего); триггер — баг ethabi 18.0.0
  `param_type/reader.rs:130` (usize underflow на type-строке короче 2 символов, напр. `"]"`).
- Поведение: `decode_transaction_input(tx, abi)` с `"type": "]"` → Rust-паника,
  `panic="abort"` не даёт pyo3 перехватить → интерпретатор умирает (exit 134).
  Pure-этаж на том же ABI отвечает ошибкой. Путь атакующего: ABI/калладата — внешние данные
  (верифицированный источник контракта, токен-лист и т.п.).
- Evidence (повтор): `thread panicked at ethabi-18.0.0/src/param_type/reader.rs:130:53:
  byte index 18446744073709551615 is out of bounds of ']'` → `exit=134`. Свая.Characterization:
  только `']'` абортит; `'[]'`, `'[a]]'`, `'[0]'` и пр. — чисто.
- Фикс: убрать `panic = "abort"` (pyo3 конвертирует паники в `PanicException`) + `catch_unwind`
  вокруг парсинга ABI с маппингом в `FastAbiError`; добавить `PanicException` в
  `_FALLBACK_ERRORS` (`decode.py:335-340`) как defense-in-depth.

### HIGH

**H1 (новый). Безымянные/дублирующиеся имена входов ABI — тихая потеря данных на pure-этаже; паритет тиров сломан**
- Найдено независимо двумя агентами (Rust-тир и фаззинг), верифицировано координатором;
  картина оказалась хуже докладов.
- Где: `decode.py:450-456` (`dict(zip([param['name']…], …))`), та же схема на `:639`/`:648`
  (события); компиляция плана в индексе — `_abi_index`.
- Поведение (все пробы на HEAD, pure-этаж = базовая установка):
  - два безымянных `uint256` → `decoded_data = {'': <последнее значение>}` — первое
    значение **молча потеряно**;
  - `transfer(address,uint256)` без имён → декод **полностью пуст** `decoded_func=''`:
    внутри плана декода параметры съезжают, адрес декодируется из слова uint256 →
    `ValueError: address: padding is not zero` поглощается как «malformed calldata»;
  - дубли имён `a`,`a` → остаётся только последнее значение;
  - Rust-тир на том же вводе отвечает `param_0`/`param_1` со всеми значениями →
    добавление/удаление `[fastabi]` меняет результат (нарушение контракта паритета).
  - `TestTierParity` этого не ловит: тест сам подставляет имена (`or f'p{position}'`).
- Фикс: безымянным — позиционные ключи (как уже делает `decode_arguments` → `'0'`,`'1'`),
  коллизии — суффикс; починить компиляцию плана для пустых имён; добавить оба случая в паритет-тест.

**H2 (новый). Алиасы сетей etherscan (`eth`, `bnb`, `binance`, `matic`, `arb`, `op`) резолвятся реестром, но роняют конструкцию клиента** — верифицировано координатором
- Где: `chain_registry.py:248-265` (таблица алиасов) + `:1010-1046` (алиас нормализует
  `config_network`, но `scanner_network` остаётся сырым) + `scanners/base.py:244-249` (отказ).
- Поведение: `from_config('etherscan','bnb')` → `ValueError: Network 'bnb' not supported by
  etherscan v2. Available: arbitrum, base, bsc, …` — при этом `'bsc'` и `56` конструируются.
  Зеркало раунд-1 item 26: там оракул отвергал объявленную сеть, тут не-канонизованное
  имя доезжает до сканера.
- Фикс: канонизовать `scanner_network` тем же маппингом, что и `url_network` (или убрать
  6 алиасов из record'а).

### MEDIUM

- **M1. NodeReal over-cap логи: сплита нет, сырой FATAL наружу** — см. N-M1 (неполный фикс H3).
- **M2. `fixedMxN` → `Decimal` валит MCP-сериализацию**: pure-этаж декодирует fixed в
  `Decimal`, `_to_rust_convention` не имеет для него ветки (`decode.py:302-323`), MCP
  `get_transaction_info` делает `orjson.dumps` → `TypeError: Type is not JSON serializable` —
  тул целиком падает вместо ответа. Фикс: рендерить Decimal строкой (`format(v,'f')`).
- **M3. `tuple[]` с пустыми `components` → вечное вращение на ОБОИХ тирах** (DoS-hang):
  `count * head_size(empty tuple) == 0` обходит проверку «массив влезает в буфер» —
  96-байтный calldata с `count=2^63` вешает декод (подтверждено: 3.5 мин 96% CPU, оба тира).
  Фикс: `count > 0` при `head_size == 0` → corrupted length (оба тира).
- **M4. `moralis_hex` неверен в 2 из 32 записей** (`chain_registry.py:659-663,744-749`):
  arbitrum-sepolia (421614) `'0xaa37a7'` = 11155367 (испорченная копия sepolia; верно
  `0x66eee`); mode (34443) `'0x868c'` = 34444, off-by-one (верно `0x868b`). Остальные 30
  репарсятся точно. Теста на round-trip нет.
- **M5. Не-UTF-8 `.env` убивает `from_config`**: `_load_env_file` ловит только `OSError`
  (`config.py:364-383`) → `UnicodeDecodeError` наружу. Единственный источник конфига без
  warn-and-continue (JSON-лоадер, для контраста, толерантен). Фикс: `errors='replace'` +
  warning.
- **M6. `blockscout_v2` всегда сообщает currency `ETH`**: record прибит к
  `api_kind='blockscout_eth'` (`chain_registry.py:328-334`) → `client.currency`='ETH' для
  bsc/polygon/gnosis (v1 корректно даёт `BNB` и т.д.). Течёт в пул и MCP-вывод
  (wallet balance / address overview). Запросы не задеты (v2 не пользуется UrlBuilder).
- **M7. 4 устаревших `blockscout_instance` хоста рекламируются впустую** (goerli, fantom,
  blast, mode — `chain_registry.py:634-749`): ни один сканер не конструируется для этих
  цепей, но MCP `list_chains` публикует хосты и инструкции утверждают «scanner 'etherscan'
  covers every listed chain» — реально etherscan покрывает 10 из 33 перечисленных. Агент,
  последовавший совету тулза, получит construction error.
- **M8. `ConfigurationManager(config_dir=B)` молча возвращает синглтон с директорией A**:
  `__new__` игнорирует `config_dir` при живом `_instance` (`config.py:110-142`); после
  первого использования в процессе (включая `get_config_manager()` с `Path.cwd()`) эмбеддер
  читает чужие `.env`/JSON без предупреждения.
- **M9. Нормализованная модель: `status='pending'` → `is_error=True`**
  (`domain/normalize.py:221-223`, `status.lower() != 'ok'`). Pending — не execution failure;
  противоречит собственному контракту слоя («never invented, never defaulted»). Механизм
  подтверждён пробой; встречаемость у BlockScout V2 — по swagger (enum не зафиксирован),
  live не проверялся. Фикс: ошибкой считать только известные failure-статусы.

### LOW (сводно)

**Конкурентность/цикл (стресс-агент; ядро в целом крепкое — см. Часть III):**
- `network.py:695` — redaction payload'а считается eager на каждый запрос даже при
  выключенном DEBUG (~313 µs на 200-tx страницу чистого loop-времени).
- `core/streaming.py:469` + `core/client.py:64` — ABI-декод стрима выполняется инлайн на
  loop, вопреки докстрингу «decoded in thread pool (non-blocking)» (офлоадят только
  `SmartContract.iter_events` и Arrow-путь).
- `network.py:677` — запрос к уже закрытому Network сначала прогоняет guard-пробник и
  кэширует `ChainscanClientError('Network is closed')` как «вечную конфигурационную
  ошибку»; семантически неверно (это lifecycle, не конфиг), практически безвредно.

**Rust-тир:**
- Экзотические ширины (`int12`, `uint0`, `bytes0`) декодируются на Rust-тире, pure-этаж
  поднимает `AbiTypeNotSupportedError` — расхождение тиров (Solidity их не производит).
- Экспортируемый `decode_one` бросает `ValueError` на unknown selector/truncation, в
  отличие от остальных входов, возвращающих пустой результат (в самой библиотеке не
  используется; контракт .pyi не описывает).
- `decode_input` держит GIL весь декод (библиотека биндит именно его; `decode_one` с
  `allow_threads` не используется).

**MCP/фаззинг:**
- `mcp/cursors.py:139` `unwrap_scanner_cursor` обходит tool-binding и whitelist (обе
  защиты модуля) и отдаёт сырые `TypeError`/`ValueError` (внутренних вызовов нет, но это
  публичный экспорт).
- `abi_pure.py:396-406` `encode_arguments`: скаляр там, где ABI ждёт массив/тупл → сырой
  `TypeError`, соскальзывающий мимо `except ValueError` в `read_contract`.
- `mcp/envelope.py:193` `format_units`: `decimals` из метаданных провайдера без клампа —
  `decimals=10**7` даёт 10-мегабайтную строку за 6.3 c за вызов; float-вход молча
  трекается (`int(1.5)→1`) вопреки докстрингу «unchanged».
- `cursors.py:85` версия курсора: `v: true` и `v: 1.0` проходят (`True == 1` в Python).

**Реестр/конфиг/CLI (свип):**
- `.env`-диалект: `export KEY=x` сохраняет ключ `'export KEY'`; inline-комментарий
  `val # c` остаётся в значении; BOM ломает первый ключ; `./.env` перекрывает `./.env.local`
  (инверсия общеупотребимой конвенции).
- `register_scanner`/JSON: `"supported_networks": "main"` → `set('main')` молча; int →
  голый `TypeError`; неизвестные id в `api_keys` молча дропаются.
- `base_url.py`: netloc не валидируется — `https://example.com\..\etc` и порты 0/65536+
  принимаются и выстреливают поздними DNS/запросными ошибками вместо конструкционного `ValueError`.
- `cli.py`: `--networks 'main, test,,x'` регистрирует `{'', ' test', 'main', 'x'}`; `test`
  печатает одну и ту же ошибку дважды; `add-scanner` создаёт запись, которой нельзя
  воспользоваться из публичного API (сообщение об этом не говорит).
- `scripts/agent/probe_provider_caps.py:361` — режим `--json` всегда `exit 0`, вердикт
  drift/inconclusive считается только в текстовом режиме (ломает «exit status is the
  verdict» для CI); `:237` — любая ошибка (429/таймаут) трактуется как enforcement капы →
  ложный DRIFT.
- `core/endpoint.py:124` — декларация «пустое wire-имя = инертный вход» на самом деле
  эмитит параметр с пустым именем (латентно: текущие спеки `''` не декларируют).

---

## Часть III. Что проверено и чисто (раунд 2)

- **Конкурентность (ядро крепкое)**: 50 параллельных first-request'ов → гвард выполняется
  ровно один раз; отмена владельца перезаряжает гвард без дедлока; 200-call storm —
  `_active_requests→0`, close() дренит in-flight (в т.ч. 15-30 случайных отмен), после
  close() ни один dispatch не стартует; двойные/тройные отмены в dispatch/backoff (300
  испытаний) не текут; tenacity-состояния изолированы (100 конкурентных прогонов);
  пул: 100-call failover storm, sticky/cooldown/exhaustion корректны, pinned-стримы
  перезапускаются только на first-page failure, concurrent close+cancel дренит обоих
  членов; aiolimiter не тратит токены отменённых ожиданий; InMemoryCache под 200-task
  storm с 20% отмен держит размер и лок; MCP ClientPool: `get()` синхронный — гонки
  конструкторов нет; loop-lag: orjson 5.8 MB / 20k items = 15 ms без фризов.
- **Фаззинг (fixed seeds)**: eth-abi↔abi_pure round-trip 3499×3 на deep-типах (nested
  tuples с динамикой глубины 2-4, массивы динамики, граничные значения всех семейств,
  i64::MAX-флип) — **0 расхождений**; hostile buffers 40 000 — 0 raw-исключений; convert
  против integer-эталона (±10^80, half-up, hex/ISO) 3000×4 — **0**; format_units 5000 — 0;
  курсоры 6000 мутаций — 0 сырых исключений, forged всегда отвергнут.
- **Rust-паритет**: из 14 правил strictness abi_pure — 12 точный паритет (таблица
  в отчёте агента); fixed/ufixed — корректный gated fall-through на одиночном и батч-пути;
  keccak/версии/импорт-фоллбек/LRU (content-hash ключи, moka, 1000) — чисто; panic-sweep
  3235 malformed-calldata декодов — 0 паник (кроме C1, который в этот sweep не входит —
  он в парсинге ABI, не calldata).
- **Реестр-свип (скрипт, не руками)**: 228 строковых + 140 int комбинаций «сканер × сеть»
  через construction; перекрёстная сверка 6 таблиц (records/aliases/BASE_URLS/STANDARD_CHAINS/
  UrlBuilder/BLOCKSCOUT_SCANNER_NETWORKS); chainlist-парсер на офлайн-фикстурах;
  base_url→wire 32 фазз-кейса × 3 custom-URL сканера; 15 .env-кейсов; 21 CLI-кейс —
  сверх перечисленных находок чисто.
- **Ранее не покрытые файлы**: endpoint/url_builder/host (в т.ч. сквозная проверка, что
  `chainid` для ('etherscan','base') = 8453 доезжает до провода), types/constants
  (значения = докам), `__init__` exports, ports↔adapters, normalize/normalized/response
  (полная матрица форм), normalized streaming twins (деривация 1:1 от стрим-сиблингов),
  mcp/server.py (12 тулов, схемы, structuredContent, isError-путь, AIOCHAINSCAN_MCP_SCANNER),
  .pyi vs lib.rs — чисто (с двумя note в LOW).

## Ограничения раунда

- Rust-тир верифицирован на prebuilt-колесе `aiochainscan_fastabi-1.0.0` из
  `fastabi/target/wheels/` (mtime новее `lib.rs`, версия совпадает с Cargo.toml); пересборка
  не выполнялась.
- M9 (pending→is_error): механизм подтверждён пробой, встречаемость у провайдера —
  inference из swagger/docs, без live-звонков (правило аудита).
- Известные #38 (convert leniency) и #43 (hex balance в get_wallet_balance) подтверждены
  неисправленными — правились не в этих коммитах.

## Приоритет исправлений

1. **C1** — `panic="abort"` + catch_unwind: процесс умирает от внешних данных.
2. **H1** — unnamed/duplicate ABI inputs: тихая потеря данных на базовой установке.
3. **H2** — алиасы etherscan, не доезжающие до сканера.
4. **M1** — довести фикс H3: result-size refusal → overflow-сигнал/failover.
5. **M2, M3** — MCP-краш на Decimal; hang на `tuple[]`.
6. **M4–M9** — данные (moralis_hex, currency), толерантность конфига, list_chains.
