## GraphQL Support Plan (Hexagonal Architecture Only)

### Goals
- Provide first-class support for providers that expose GraphQL endpoints instead of Etherscan-like REST.
- Keep public facades and service APIs stable; integrate via ports/adapters only.
- Maintain TDD: add failing tests first, implement in small increments.

### Non-goals (for this phase)
- No changes to the unified core (ChainscanClient/scanners) path.
- No replacement of existing REST flow; GraphQL is an additional transport/provider path.

### Design Overview
- Extend the hexagonal layer with GraphQL-specific ports/adapters and a thin provider selection layer (federator) while preserving existing services.
- Unify pagination semantics across REST (page/offset) and GraphQL (cursor) via a generic Page[T] domain type and conversion helpers.
- Normalize data and errors at the adapter boundary to existing DTOs/normalizers.

### New and Updated Components

1) Domain (new types)
- Page[T]: generic, typed container for paginated results with opaque cursor strings
- Unifies REST (page/offset) and GraphQL (cursor-based) pagination patterns
- Maintains backward compatibility - only new typed facades use Page[T]

2) Ports (new protocols)
- **GraphQLClient**: Execute GraphQL queries with lifecycle management (execute, close)
- **GraphQLQueryBuilder**: Transform logical methods (Method enum) into provider-specific GraphQL queries
- **ProviderFederator**: Choose between REST/GraphQL based on capabilities, health, and configuration

3) Adapters (new implementations)
- **AiohttpGraphQLClient**: GraphQL client using aiohttp with existing retry/rate-limit/telemetry integration
- **BlockscoutGraphQLBuilder**: Builds Blockscout GraphQL queries for core methods (logs, transactions, token transfers)
- **SimpleProviderFederator**: Chooses REST vs GraphQL based on capabilities.py and health status
- **Future**: BitqueryGraphQLBuilder, SubgraphGraphQLBuilder as needed

4) File structure (new components only)
- **domain/models.py**: Add Page[T] generic type
- **ports/**: Add 3 new protocol files (graphql_client, graphql_query_builder, federator)
- **adapters/**: Add 3 new implementations (aiohttp_graphql_client, blockscout_graphql_builder, simple_provider_federator)
- **services/**: Edit existing files to add optional GraphQL DI parameters; add pagination.py for cursor helpers
- **capabilities.py**: Extend with GraphQL support flags per provider/network

5) Services (updates only)
- Inject optional GraphQL ports (GraphQLClient, GraphQLQueryBuilder) and ProviderFederator via DI.
- For methods where GraphQL is supported and either configured as preferred or REST is unavailable/429/5xx, execute via GraphQL.
- Keep the facade/service signatures unchanged; return existing DTOs/normalized dicts/typed DTOs.
- Add pagination parameter to list-returning services for GraphQL cursor support.

### Pagination Unification Strategy
- **Problem**: REST uses page/offset, GraphQL uses cursor-based pagination
- **Solution**: Page[T] domain type with opaque cursor strings that work for both
- **Implementation**:
  - REST: encode page/offset as opaque string (`"page=2&offset=100"`)
  - GraphQL: use native endCursor from response
  - Conversion helpers in services/pagination.py
- **Backward compatibility**: Only new `*_typed` facades return Page[T], existing facades unchanged

### Error Handling Strategy
- **Problem**: GraphQL errors differ from HTTP errors (errors[] array vs status codes)
- **Solution**: Map GraphQL errors to existing Chainscan exception hierarchy
- **Implementation**: Handle both HTTP-level (transport) and GraphQL-level (query) errors in GraphQL adapter
- **Telemetry**: Add `provider_type` field to distinguish graphql vs rest errors

### Data Normalization Strategy
- **Reuse existing normalizers**: EIP-55 addresses, timestamps, hex conversions, wei amounts
- **GraphQL-specific mappers**: Transform GraphQL field names to match existing DTO structures
- **Consistency**: Same normalized output regardless of REST or GraphQL source

### Infrastructure Reuse
- **Ports**: Reuse existing RateLimiter, RetryPolicy, Cache, Telemetry ports
- **Composition**: Same DI pattern for GraphQL as REST (inject ports into adapters)
- **Telemetry**: Same event format with additional `provider_type` field

### Capability Management
- **Extension**: Add GraphQL support flags to capabilities.py per provider/network
- **Decision logic**: Federator uses capabilities to choose REST vs GraphQL
- **Examples**: `supports_logs_gql`, `supports_txlist_gql` for Blockscout networks

### Testing Strategy (TDD approach)
1. **Domain layer**: Pagination helpers (encode/decode cursors, REST↔GraphQL bridge)
2. **Adapter layer**: GraphQL client (error mapping, lifecycle), Query builders (query generation)
3. **Service layer**: DI integration, provider selection logic, normalization consistency
4. **Federator**: Capability-based selection, health tracking, fallback logic
5. **Integration**: End-to-end GraphQL→DTO flow
6. **Regression**: Existing REST tests remain green (no breaking changes)

### Implementation Roadmap
1. **Foundation**: Domain types (Page[T]), pagination helpers, ports protocols — DONE
2. **GraphQL adapter**: HTTP client with lifecycle, error mapping, telemetry integration — DONE
3. **Query builders**: Provider-specific generation for Blockscout (tx by hash, token transfers, address txs) — DONE (logs pending provider support)
4. **Service integration**: Optional GraphQL DI + fallback on REST — DONE (logs fallback preferred)
5. **Federator**: Capability-based selection + basic health hooks — DONE
6. **Capabilities**: Flags per provider/network (`*_gql`) — DONE
7. **Typed facades**: `get_logs_page_typed`, `get_token_transfers_page_typed`, `get_address_transactions_page_typed` — DONE
8. **Documentation**: Update usage/notes — PARTIAL (this plan updated)

### Usage Concepts (post-implementation)

#### Typed facades with GraphQL
- New `*_typed` facades return `Page[DTO]` with cursor-based pagination
- DI allows injecting GraphQL client/builder for preferred providers
- Federator automatically selects GraphQL when available and faster

#### Backward compatibility guarantee
- Existing untyped facades return `list[dict]` unchanged
- Same function signatures, same return formats
- GraphQL is opt-in via DI or federator selection, never forced

### Quality Assurance
- **Tests**: TDD approach, existing suite unchanged, comprehensive coverage
- **Code quality**: ruff, mypy --strict, import-linter contracts updated
- **Architecture**: Services don't import adapters, ports remain protocol-only

### Risk Analysis
- **Integration complexity**: Mitigate via DI and capability gating, no forced behavior changes
- **Pagination compatibility**: Opaque cursors handle both REST and GraphQL patterns
- **Error handling**: Centralized GraphQL error mapping in adapter layer
- **Performance**: Reuse HTTP sessions, apply existing retry/rate-limit patterns

### Decision Points
- **Provider priority**: Start with Blockscout (public, stable GraphQL)
- **Configuration**: Support both DI and environment-based GraphQL preference
- **Scope**: Focus on high-value endpoints (logs, transactions) in phase 1

### Rollout Strategy
- **Phase 1**: GraphQL for transaction by hash — DONE; logs kept on REST due to schema variance
- **Phase 1.1**: Token transfers, address transactions via GraphQL — DONE
- **Phase 1.2**: Federator health tracking — DONE; expand provider matrix — NEXT; docs sweep — NEXT
