"""
Base scanner class for implementing different blockchain explorer APIs.
"""

from abc import ABC
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, ClassVar, Literal

from ..chain_registry import resolve_chain_id
from ..core.endpoint import EndpointSpec, coerce_response_items
from ..core.url_builder import UrlBuilder
from ..crypto import to_checksum_address
from ..domain.method import Method
from ..exceptions import ChainscanClientError, ChainscanNetworkError, MethodNotDeclaredError
from ..network import Network

#: Public (dialect) param names that carry a block-range bound. A spec whose
#: ``param_map`` declares any of them can narrow that method's query by
#: block; see :meth:`Scanner.supports_block_range`.
BLOCK_RANGE_PARAM_KEYS: frozenset[str] = frozenset(
    {'start_block', 'end_block', 'from_block', 'to_block'}
)


def spec_declares_block_range(spec: EndpointSpec) -> bool:
    """Whether a spec's ``param_map`` declares any public block-range param.

    The single source of the capability: shared by
    :meth:`Scanner.supports_block_range` (instance path) and the scanner
    registry (class path) so both answer identically.
    """
    return any(key in spec.param_map for key in BLOCK_RANGE_PARAM_KEYS)


def hex_block_tag(value: Any) -> Any:
    """Coerce a block identifier to a JSON-RPC hex-quantity tag.

    ``int`` and decimal-digit strings (``123``, ``'123'``) become ``'0x...'``
    tags; anything else passes through unchanged (``'latest'``, an existing
    ``'0x...'`` tag). Shared by the scanners that route block-shaped methods
    through JSON-RPC (BlockScout V1 eth-rpc, NodeReal eth_*).
    """
    if isinstance(value, int):
        return hex(value)
    if isinstance(value, str) and value.isdigit():
        return hex(int(value))
    return value


def checksummed_holder_address(value: Any) -> Any:
    """Checksum a holder address, passing through values EIP-55 cannot digest."""
    if isinstance(value, str):
        try:
            return to_checksum_address(value)
        except ValueError:
            return value
    return value


def holder_item(address: Any, value: Any) -> dict[str, Any]:
    """Build the unified token-holder item every scanner's holder parser emits.

    The ONE cross-scanner item shape — ``{'address': EIP-55 str, 'value':
    str}`` with the quantity in raw units (Wei-like: never Int64). The
    scanners' parsers keep only their provider-specific field extraction and
    hand the resolved address/value here; a falsy ``value`` becomes ``'0'``
    (providers answer missing quantities as ``None``).
    """
    return {
        'address': checksummed_holder_address(address),
        'value': str(value) if value else '0',
    }


@contextmanager
def translate_unexpected_errors(context: str) -> Iterator[None]:
    """Error-translation ladder applied once at the scanner seams.

    Every library error propagates unchanged: all ``Chainscan*`` exceptions
    (transport, API, proxy, rate limit — the enumerated classes some scanners
    listed individually are all subclasses of :class:`ChainscanClientError`)
    must keep their identity so the Network retry policy and pool failure
    classification keep working, and so must
    :class:`MethodNotDeclaredError` — a capability error (deliberately *not*
    a ``ChainscanClientError``) that the provider pool routes on. Any other
    exception is masked as a non-retryable :class:`ChainscanNetworkError`
    carrying ``context``.

    The base :meth:`Scanner.call` and every ``fetch_page`` path apply this
    ladder exactly once; provider-dialect translations (e.g. NodeReal
    JSON-RPC ``-32005``) compose inside it.
    """
    try:
        yield
    except ChainscanClientError:
        raise
    except MethodNotDeclaredError:
        # Capability error (ValueError family): the pool routes on it —
        # masking it would turn silent provider failover into a cooldown.
        raise
    except Exception as exc:
        raise ChainscanNetworkError(f'{context}: {exc}', retryable=False) from exc


class Scanner(ABC):
    """
    Abstract base class for blockchain scanner implementations.

    Each scanner represents a specific API provider (like Etherscan, BlockScout)
    with a specific version, supporting certain networks and providing
    specific endpoint implementations.
    """

    # These must be defined by subclasses
    name: str
    """Scanner name (e.g., 'etherscan', 'blockscout')"""

    version: str
    """Scanner API version (e.g., 'v1', 'v2')"""

    supported_networks: set[str]
    """Networks supported by this scanner (e.g., {'main', 'test'})"""

    auth_mode: Literal['query', 'header'] = 'query'
    """How to authenticate - 'query' for URL params, 'header' for HTTP headers"""

    auth_field: str = 'apikey'
    """Field name for authentication (e.g., 'apikey', 'OK-ACCESS-KEY')"""

    SPECS: dict[Method, EndpointSpec]
    """Mapping of logical methods to endpoint specifications"""

    result_window: int | None = None
    """Total results one page/offset query can reach before the provider stops.

    Etherscan-family REST APIs bound ``page * offset`` (see
    ``constants.API_MAX_OFFSET_ETHERSCAN``): once that many items have been
    walked, further pages return nothing more, which is *silent truncation*.
    A scanner that declares this window lets
    :func:`services.pagination.iter_pages` split the requested block range and
    keep the result complete (``guarantee_complete``).

    ``None`` means "no such window": the provider paginates by an opaque
    server-issued cursor that runs to exhaustion (BlockScout V2
    ``next_page_params``, NodeReal ``pageKey``), so a single query is already
    complete and nothing needs splitting.

    Declaring the window is opt-in. A third-party scanner that *has* a result
    window but leaves this ``None`` cannot be protected by
    ``guarantee_complete`` — the engine has no way to detect its cap.
    """

    max_page_size: int | None = None
    """Largest page size (``offset``) the provider serves in one request.

    Declared where the provider **silently clamps** a larger request instead of
    refusing it: the short page then looks like the end of the data to any
    "partial page means done" stop condition, and the rest of the range is lost
    without an error. ``None`` means no known clamp (nothing to correct for).
    """

    RESULT_WINDOW_OVERRIDES: dict[Method, int | None] = {}
    """Per-method windows for endpoints that do not share the scanner's cap.

    One provider can bound different endpoints differently: BlockScout V1
    honours ``page * offset <= 10_000`` on the account endpoints but answers at
    most 1000 logs from ``getLogs`` regardless of paging. Declaring the smaller
    window makes ``guarantee_complete`` split at the *real* boundary instead of
    walking to a cap the endpoint will never reach.
    """

    cursor_keys: ClassVar[frozenset[str]] = frozenset()
    """Cursor-key vocabulary shared by every method this scanner paginates.

    The keys a cursor of this scanner's dialect may carry when the dialect is
    uniform across endpoints (Etherscan-like page/offset). Scanners whose
    cursors differ per endpoint declare the per-method vocabulary in
    :attr:`CURSOR_KEYS` instead and leave this empty. Declared here — where the
    cursor is produced — so consumers that must validate cursors (the MCP
    key whitelist) never hand-copy another scanner's private key names.
    """

    CURSOR_KEYS: ClassVar[dict[Method, frozenset[str]]] = {}
    """Per-method cursor vocabularies for dialects that differ per endpoint.

    A server-issued cursor's shape is a property of ONE endpoint (BlockScout V2
    ``next_page_params`` carries ``block_number``/``index`` for transactions
    but ``address_hash``/``value`` for holders), so scanners with such dialects
    declare the vocabulary per :class:`Method`. Methods absent from the mapping
    fall back to :attr:`cursor_keys`; an explicit empty frozenset declares "this
    method emits no cursor".
    """

    chain_id: int | None
    """Numeric chain id; ``None`` for custom base URLs until probed/recorded."""

    _instance_root: str | None = None
    """Instance root this scanner serves, when it has one.

    The base URL or host the scanner's requests target — a registry-mapped
    public instance or a custom self-hosted URL. Each concrete scanner's
    ``__init__`` sets it from the attribute it already resolves; ``None`` for
    scanners with no per-instance identity (Etherscan's shared host). Consumed
    only by the ``__str__``/``__repr__``/``_error_context`` defaults below, so
    every scanner's messages carry the same facts without per-scanner overrides.
    """

    def __init__(
        self,
        api_key: str,
        network: str,
        url_builder: UrlBuilder,
        chain_id: int | None = None,
        network_client: Network | None = None,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize scanner instance.

        Args:
            api_key: API key for authentication
            network: Network name (must be in supported_networks; arbitrary
                when ``base_url`` is given — the registry is bypassed)
            url_builder: UrlBuilder instance for URL construction
            chain_id: Chain ID (optional, will be resolved from network)
            network_client: Network instance for connection pooling.
                Scanner uses it for requests (client owns lifecycle).
                Required at call time; raises RuntimeError if None when call() is invoked.
            base_url: Custom base URL (self-hosted instance / proxy). When
                set, the supported-networks check is skipped and the scanner
                must build all request URLs from this value instead of the
                registry mappings. ``chain_id`` stays ``None`` unless given
                explicitly (the chain is unknown until probed — see
                ``ChainscanClient.get_chain_info``).

        Raises:
            ValueError: If network is not supported
        """
        # A custom base URL bypasses the registry: the instance is not one of
        # the built-in per-network deployments, so the supported-networks set
        # does not apply. Scanners that cannot honor a base URL reject it.
        if base_url is None and network not in self.supported_networks:
            available = ', '.join(sorted(self.supported_networks))
            raise ValueError(
                f"Network '{network}' not supported by {self.name} v{self.version}. "
                f'Available: {available}'
            )

        self.api_key = api_key
        self.network = network
        self.url_builder = url_builder
        self.base_url = base_url
        # Chain-id resolution ownership: ``resolve_scanner_target`` (via
        # ``ScannerTarget.chain_id``) owns it on the ``ChainscanClient`` path
        # and always hands a resolved id here — this scanner trusts it and
        # never re-resolves. The ``resolve_chain_id`` fallback below serves
        # direct scanner construction only (tests, standalone use), where no
        # client resolved a target first.
        if chain_id is not None:
            self.chain_id = chain_id
        elif base_url is not None:
            # Custom instance: the served chain is unknown until probed.
            self.chain_id = None
        else:
            self.chain_id = resolve_chain_id(network)
        self._network_client = network_client

    async def fetch_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch a single page of results plus the cursor to the next page.

        This is the pagination seam of the Scanner port: page cursors flow
        *through* this interface, so callers never reach into scanner
        internals (``SPECS`` / ``_build_url`` / ``map_params``).

        Cursor contract:
        - Returns ``(items, next_cursor)``.
        - ``next_cursor is None`` means "no more pages"; callers must stop.
        - ``next_cursor`` is opaque to callers. To fetch the next page, merge
          it into ``params`` (``params = {**params, **next_cursor}``) and call
          ``fetch_page`` again. Callers must not inspect or modify its contents.
          The ONE exception is a security validator: the scanner declares the
          key names a cursor may carry (:meth:`cursor_keys_for`) precisely so
          such validation can check declarations instead of hand-copied
          dialect knowledge.
        - Exceptions surface through the shared error ladder: every
          ``Chainscan*`` and capability error propagates unchanged, anything
          unexpected is masked as a non-retryable
          :class:`ChainscanNetworkError` (the base default routes through
          :meth:`call`; overriding implementations apply
          :func:`translate_unexpected_errors` themselves). No retry here.

        The default implementation routes through :meth:`call` and always
        terminates after a single page (cursor is ``None``). Scanners with
        native pagination override this method to surface their cursor
        (e.g. BlockScout V2 ``next_page_params``, Etherscan page/offset).

        Args:
            method: Logical method to execute
            params: Parameters for the method (include the previous cursor
                via merge when fetching subsequent pages)

        Returns:
            Tuple of (items, next_cursor) where ``next_cursor is None``
            signals the end of pagination

        Raises:
            ValueError: If method is not supported
            Various network/API errors
        """
        result = await self.call(method, **params)
        return self._coerce_items(result), None

    @staticmethod
    def _coerce_items(result: Any) -> list[dict[str, Any]]:
        """Best-effort coercion of a parsed response into a list of items.

        Canonical implementation: :func:`core.endpoint.coerce_response_items`
        (shared with ``services.pagination.normalize_items``).
        """
        return coerce_response_items(result)

    def _spec_for(self, method: Method) -> EndpointSpec:
        """Return the endpoint spec for ``method`` or raise the standard error.

        Raises:
            MethodNotDeclaredError: If ``method`` is not in this scanner's
                SPECS (message names the scanner and its available methods).
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise MethodNotDeclaredError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )
        return self.SPECS[method]

    def _require_network_client(self) -> Network:
        """Return the injected :class:`Network` or raise the standard RuntimeError.

        The scanner does not own HTTP: a client must have been injected via
        ``ChainscanClient.from_config()`` (the constructor accepts ``None``
        only because construction and wiring are separate steps).
        """
        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )
        return self._network_client

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Execute a logical method call.

        The base owns the whole seam: SPECS lookup, the missing-client guard,
        the error-translation ladder (applied exactly once — see
        :func:`translate_unexpected_errors`), request building and the ONE
        transport dispatch (:meth:`_perform_request`). Concrete scanners
        override only the provider-dialect hooks
        (:meth:`_perform_request`, :meth:`_request_url`,
        :meth:`_transport_headers`, :meth:`_error_context`).

        Args:
            method: Logical method to execute
            **params: Parameters for the method

        Returns:
            Parsed response from the API

        Raises:
            MethodNotDeclaredError: If method is not supported (a
                ``ValueError`` subclass)
            Various network/API errors
        """
        spec = self._spec_for(method)
        # Missing-client guard before the ladder: a missing Network is a
        # programming error (RuntimeError), never a network failure.
        self._require_network_client()

        with translate_unexpected_errors(self._error_context(method)):
            return await self._perform_request(spec, method, params)

    async def _perform_request(
        self,
        spec: EndpointSpec,
        method: Method,
        params: dict[str, Any],
    ) -> Any:
        """Perform the request for ``spec`` and return the parsed result.

        The default dialect is fully SPECS-driven: build the request from the
        spec (:meth:`_build_request` — param policy, auth, chain-id
        placeholders, URL), send it through the ONE transport dispatch
        (:meth:`_perform_raw_request`) and apply the spec parser. Override
        only for a provider dialect no spec can express (NodeReal JSON-RPC
        envelopes, BlockScout V1 ``/api/eth-rpc`` proxy routing) — a dialect
        whose transport already yields the final shape returns it directly
        and skips the parser.

        Args:
            spec: Endpoint specification for ``method``
            method: Logical method being executed
            params: Public parameters (mutable copy owned by the override)

        Returns:
            Parsed response
        """
        raw_response = await self._perform_raw_request(spec, method, params)
        return spec.parse_response(raw_response)

    async def _perform_raw_request(
        self,
        spec: EndpointSpec,
        method: Method,
        params: dict[str, Any],
    ) -> Any:
        """Build and send the request for ``spec``; return the raw response.

        The raw seam ``fetch_page`` implementations build on (they need the
        unparsed envelope to extract their cursor). Default implementation
        builds via :meth:`_build_request` and dispatches via
        :meth:`_dispatch_request`.
        """
        request_data = self._build_request(spec, **params)
        network = self._require_network_client()
        return await self._dispatch_request(spec, request_data, network)

    async def _dispatch_request(
        self,
        spec: EndpointSpec,
        request_data: dict[str, Any],
        network: Network,
    ) -> Any:
        """The ONE transport dispatch, shared by every SPECS-driven request.

        Two URL topologies, one mechanism:

        - no ``'url'`` in ``request_data``: the endpoint lives at the
          UrlBuilder's ``API_URL`` — ``network.get/post`` apply the profile's
          filtering and signing;
        - ``'url'`` present (a :meth:`_request_url` override): the scanner
          owns the full URL — sent via ``network.request`` with no UrlBuilder
          signing; GET carries query params, POST sends the mapped params as
          a JSON body (an empty payload is sent as ``None``, matching the
          providers that reject empty bodies).
        """
        url = request_data.get('url')
        headers = request_data.get('headers')
        if url is None:
            if spec.http_method == 'GET':
                return await network.get(params=request_data.get('params'), headers=headers)
            return await network.post(data=request_data.get('data'), headers=headers)

        payload = (
            request_data.get('params') if spec.http_method == 'GET' else request_data.get('data')
        )
        if spec.http_method == 'GET':
            return await network.request(
                method='GET', url=url, params=payload or None, headers=headers
            )
        return await network.request(
            method='POST', url=url, json_data=payload or None, headers=headers
        )

    def _request_url(self, spec: EndpointSpec, params: dict[str, Any]) -> str | None:
        """Full request URL for full-URL scanners; ``None`` for UrlBuilder ones.

        Default ``None``: the request targets the UrlBuilder's ``API_URL``
        through ``network.get/post``. Full-URL scanners (per-instance hosts,
        path placeholders) return ``f'{root}{spec.path}'`` here and their
        requests go through ``network.request`` instead.
        """
        return None

    def _transport_headers(self, spec: EndpointSpec) -> dict[str, str]:
        """Per-scanner transport headers merged into every built request.

        Default: none. Full-URL scanners use this for provider quirks the
        UrlBuilder profile cannot express (e.g. BlockScout V2 advertising
        ``gzip, deflate`` only — never brotli).
        """
        return {}

    def _error_context(self, method: Method) -> str:
        """Context string the error ladder stamps on unexpected failures.

        Names the scanner, its version, the failing method and — when the
        scanner serves a per-instance deployment — the instance root, so one
        default says everything the scanners used to say in divergent
        overrides (two of which dropped the method name).
        """
        context = f'{self.name} v{self.version} unexpected error for {method.name}'
        if self._instance_root is not None:
            context += f' ({self._instance_root})'
        return context

    def _require_mapped_network(self, mapping: dict[str, str], kind: str) -> str:
        """Resolve :attr:`network` through a per-scanner URL map.

        The ONE unknown-network ValueError shape, shared by every scanner
        whose ``__init__`` resolves its endpoints from a network → URL table.
        Unreachable through the client (the base constructor validates
        ``supported_networks`` first and every table covers them) — kept as
        the defensive guard for direct scanner construction.
        """
        resolved = mapping.get(self.network)
        if resolved is None:
            available = ', '.join(sorted(mapping))
            raise ValueError(
                f"Network '{self.network}' not mapped to a {kind}. Available: {available}"
            )
        return resolved

    def _build_request(self, spec: EndpointSpec, **params: Any) -> dict[str, Any]:
        """
        Build request data from endpoint spec and parameters.

        Args:
            spec: Endpoint specification
            **params: Method parameters

        Returns:
            Dictionary with request data (``headers``, ``params``/``data``
            and, for full-URL scanners, ``url``)
        """
        # Map parameters using the spec (unknown-param policy + path
        # placeholders are the spec's own declaration — see
        # ``EndpointSpec.map_params``).
        mapped_params = spec.map_params(**params)

        # Substitute chain_id placeholders
        if hasattr(self, 'chain_id'):
            for key, value in mapped_params.items():
                if isinstance(value, str) and value == '{chain_id}':
                    mapped_params[key] = self.chain_id

        # Set up authentication
        headers: dict[str, str] = dict(self._transport_headers(spec))
        if spec.requires_api_key and self.api_key:
            if self.auth_mode == 'query':
                mapped_params[self.auth_field] = self.api_key
            else:  # header
                headers[self.auth_field] = self.api_key

        # Build request data
        request_data: dict[str, Any] = {'headers': headers}

        url = self._request_url(spec, params)
        if url is not None:
            request_data['url'] = url

        if spec.http_method == 'GET':
            request_data['params'] = mapped_params
        else:  # POST
            request_data['data'] = mapped_params

        return request_data

    def supports_method(self, method: Method) -> bool:
        """
        Check if this scanner supports a logical method.

        Args:
            method: Method to check

        Returns:
            True if supported, False otherwise
        """
        return method in self.SPECS

    # ------------------------------------------------------------------
    # Block-range capability (declared by SPECS, never by scanner name).
    # ------------------------------------------------------------------

    def supports_block_range(self, method: Method) -> bool:
        """
        Check whether the method's spec declares a block-range parameter.

        Derived entirely from ``SPECS``: a method supports a block range
        here iff its :class:`~aiochainscan.core.endpoint.EndpointSpec`
        ``param_map`` maps at least one public block-range name
        (``start_block``/``end_block``/``from_block``/``to_block``). This is
        how the streaming/paginated client paths tell "the provider can
        narrow this query by block" from "the range would be silently
        dropped on the wire" (e.g. BlockScout V2 address endpoints take no
        Etherscan-style block bounds) — no scanner-name matching anywhere.

        Args:
            method: Method to check

        Returns:
            True if the declaring spec carries a block-range parameter;
            ``False`` for undeclared methods and rangeless specs alike
            (test doubles without ``SPECS`` count as rangeless).
        """
        specs: Any = getattr(self, 'SPECS', None)
        spec = specs.get(method) if isinstance(specs, dict) else None
        return spec is not None and spec_declares_block_range(spec)

    @classmethod
    def result_window_for(cls, method: Method) -> int | None:
        """The window that bounds THIS method, falling back to the scanner's.

        Read by :func:`services.pagination.page_fetcher` so every guaranteed
        path sees the per-endpoint cap, and by
        :func:`scanners.scanners_serving_completely`, which asks the same
        question of a scanner CLASS — hence a classmethod: a per-endpoint
        window must decide capability the same way it decides pagination.
        """
        overrides = cls.RESULT_WINDOW_OVERRIDES
        if method in overrides:
            return overrides[method]
        return cls.result_window

    @classmethod
    def cursor_keys_for(cls, method: Method) -> frozenset[str]:
        """The cursor-key vocabulary for THIS method.

        Per-method declaration first (:attr:`CURSOR_KEYS`), falling back to the
        scanner-wide :attr:`cursor_keys`. Read by the MCP cursor allow-list
        derivation (:func:`aiochainscan.mcp.tools.scanner_cursor_keys`), which
        unions it over every registered scanner that serves the method — the
        one legitimate reader of cursor contents, since a forged token is
        bounded by what it may merge. A classmethod for the same reason as
        :meth:`result_window_for`: the registry asks questions of classes.
        """
        return frozenset(cls.CURSOR_KEYS.get(method, cls.cursor_keys))

    def get_supported_methods(self) -> list[Method]:
        """
        Get list of all supported methods.

        Returns:
            List of supported Method enum values
        """
        return list(self.SPECS.keys())

    def __str__(self) -> str:
        """String representation of the scanner."""
        networks = ', '.join(sorted(self.supported_networks))
        root = f', instance: {self._instance_root}' if self._instance_root is not None else ''
        return f'{self.name} v{self.version} (networks: {networks}{root})'

    def __repr__(self) -> str:
        """Detailed string representation.

        ``network`` and ``methods`` are read defensively (getattr/isinstance)
        for the same reason ``supports_block_range`` is: init-skipping test
        doubles must survive a repr.
        """
        parts = [
            f"name='{self.name}'",
            f"version='{self.version}'",
            f'networks={self.supported_networks}',
            f"auth_mode='{self.auth_mode}'",
        ]
        network = getattr(self, 'network', None)
        if network is not None:
            parts.append(f"network='{network}'")
        if self._instance_root is not None:
            parts.append(f"instance_root='{self._instance_root}'")
        specs: Any = getattr(self, 'SPECS', None)
        if isinstance(specs, dict):
            parts.append(f'methods={len(specs)}')
        return f"{self.__class__.__name__}({', '.join(parts)})"
