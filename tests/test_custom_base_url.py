"""Custom ``base_url`` (self-hosted BlockScout / Etherscan proxy) and chain validation.

Covers:
- the URL-vs-alias heuristic of ``from_config`` / ``resolve_scanner_target``
- base URL validation and normalization (https default, opt-in cleartext http)
- scanner URL construction for self-hosted instances
- chain info probing with a TTL cache (chainlist downloaded once per process)
- ``expected_chain_id`` lazy validation raising ``ChainscanDataError``
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from aiochainscan import ChainscanClient, Method
from aiochainscan.base_url import is_url_like, validate_base_url
from aiochainscan.chain_registry import resolve_scanner_target
from aiochainscan.config import ConfigurationManager
from aiochainscan.core.mixins.chain import reset_chain_info_cache
from aiochainscan.exceptions import ChainscanDataError
from aiochainscan.services.chain_info import ChainInfo

SELF_HOSTED = 'https://my-blockscout.internal'

CHAINLIST_PAYLOAD: dict[str, Any] = {
    'comments': 'List of API endpoints maintained by Etherscan EAAS.',
    'totalcount': 2,
    'result': [
        {
            'chainname': 'Ethereum Mainnet',
            'chainid': '1',
            'blockexplorer': 'https://etherscan.io/',
            'apiurl': 'https://api.etherscan.io/v2/api?chainid=1',
            'status': 1,
        },
        {
            'chainname': 'Polygon Mainnet',
            'chainid': '137',
            'blockexplorer': 'https://polygonscan.com/',
            'apiurl': 'https://api.etherscan.io/v2/api?chainid=137',
            'status': 1,
        },
    ],
}


@pytest.fixture(autouse=True)
def _isolated_config():
    """Isolate the configuration-manager singleton from ambient env/keys."""
    ConfigurationManager.reset_instance()
    reset_chain_info_cache()
    yield
    ConfigurationManager.reset_instance()
    reset_chain_info_cache()


@pytest.fixture(autouse=True)
def _no_provider_keys(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Self-hosted BlockScout must never require provider API keys.

    Clearing the environment is not enough: keys also come from a ``.env`` file
    in the config dir, so the manager is rooted at an empty directory — without
    that, these tests pass or fail depending on whether the developer running
    them happens to have a real key checked into their workspace.
    """
    for var in ('ETHERSCAN_KEY', 'ETH_KEY', 'ETH_API_KEY'):
        monkeypatch.delenv(var, raising=False)
    ConfigurationManager.reset_instance()
    ConfigurationManager(tmp_path)


# ============================================================================
# URL vs alias heuristic
# ============================================================================


class TestIsUrlLike:
    """A string with a ``scheme://`` prefix is a URL; anything else is an alias."""

    @pytest.mark.parametrize(
        'value',
        [
            'https://my-blockscout.internal',
            'http://localhost:3000',
            'https://eth-sepolia.blockscout.com',
            'https://explorer.example.com/blockscout/',
            'HTTPS://EXAMPLE.COM',
        ],
    )
    def test_urls(self, value: str) -> None:
        assert is_url_like(value)

    @pytest.mark.parametrize(
        'value',
        [
            'ethereum',
            'eth',
            'mainnet',
            'sepolia',
            'my-blockscout.internal',  # bare host without scheme is NOT a URL
            '8453',
            '',
            'https:/example.com',  # single slash — not scheme://
            'blockscout_v2',
        ],
    )
    def test_aliases_and_garbage(self, value: str) -> None:
        assert not is_url_like(value)


# ============================================================================
# base URL validation / normalization
# ============================================================================


class TestValidateBaseUrl:
    def test_https_accepted_and_trailing_slash_stripped(self) -> None:
        assert validate_base_url('https://my-blockscout.internal/') == SELF_HOSTED

    def test_host_and_scheme_lowercased(self) -> None:
        assert validate_base_url('HTTPS://My-BlockScout.Internal') == SELF_HOSTED

    def test_port_and_base_path_preserved(self) -> None:
        assert (
            validate_base_url('https://explorer.example.com:8443/bs/')
            == 'https://explorer.example.com:8443/bs'
        )

    def test_cleartext_http_refused_by_default(self) -> None:
        with pytest.raises(ValueError, match='allow_http=True'):
            validate_base_url('http://my-blockscout.internal')

    def test_cleartext_http_allowed_opt_in(self) -> None:
        assert (
            validate_base_url('http://my-blockscout.internal', allow_http=True)
            == 'http://my-blockscout.internal'
        )

    @pytest.mark.parametrize(
        'url',
        [
            'ftp://my-blockscout.internal',
            'ws://my-blockscout.internal',
            'file:///etc/passwd',
        ],
    )
    def test_non_http_scheme_refused(self, url: str) -> None:
        with pytest.raises(ValueError, match='scheme'):
            validate_base_url(url)

    def test_missing_host_refused(self) -> None:
        with pytest.raises(ValueError, match='host'):
            validate_base_url('https://')

    def test_credentials_refused(self) -> None:
        with pytest.raises(ValueError, match='[Cc]redentials'):
            validate_base_url('https://user:secret@my-blockscout.internal')

    def test_query_string_refused(self) -> None:
        with pytest.raises(ValueError, match='query'):
            validate_base_url('https://my-blockscout.internal/?apikey=secret')

    def test_fragment_refused(self) -> None:
        with pytest.raises(ValueError, match='fragment'):
            validate_base_url('https://my-blockscout.internal/#anchor')

    def test_parent_directory_segment_refused(self) -> None:
        with pytest.raises(ValueError, match=r'\.\.'):
            validate_base_url('https://my-blockscout.internal/../probe')

    @pytest.mark.parametrize(
        'url',
        [
            'https://my-blockscout.internal/%2e%2e/probe',
            'https://my-blockscout.internal/..%2fprobe',
            'https://my-blockscout.internal/.%2e/probe',
        ],
    )
    def test_percent_encoded_parent_segment_refused(self, url: str) -> None:
        """Same traversal to any server that decodes the path."""
        with pytest.raises(ValueError, match=r'\.\.'):
            validate_base_url(url)

    def test_whitespace_refused(self) -> None:
        with pytest.raises(ValueError, match='whitespace'):
            validate_base_url('https://my blockscout.internal')

    def test_empty_refused(self) -> None:
        with pytest.raises(ValueError):
            validate_base_url('')


# ============================================================================
# resolve_scanner_target: URL branch
# ============================================================================


class TestResolveCustomBaseUrlTarget:
    def test_blockscout_v2_self_hosted_keyless(self) -> None:
        target = resolve_scanner_target('blockscout_v2', SELF_HOSTED)
        assert target.scanner_name == 'blockscout'
        assert target.scanner_version == 'v2'
        assert target.base_url == SELF_HOSTED
        assert target.api_key == ''
        assert target.api_kind == 'blockscout_eth'
        assert target.network == 'custom'
        assert target.chain_id is None  # unknown until probed

    def test_blockscout_v2_with_expected_chain_id(self) -> None:
        target = resolve_scanner_target('blockscout_v2', SELF_HOSTED, expected_chain_id=100)
        assert target.chain_id == 100

    def test_blockscout_v1_self_hosted_keyless(self) -> None:
        target = resolve_scanner_target('blockscout', SELF_HOSTED)
        assert target.scanner_name == 'blockscout'
        assert target.scanner_version == 'v1'
        assert target.base_url == SELF_HOSTED
        assert target.api_key == ''

    def test_http_url_requires_allow_http(self) -> None:
        with pytest.raises(ValueError, match='allow_http=True'):
            resolve_scanner_target('blockscout_v2', 'http://my-blockscout.internal')

    def test_http_url_with_allow_http(self) -> None:
        target = resolve_scanner_target(
            'blockscout_v2', 'http://my-blockscout.internal/', allow_http=True
        )
        assert target.base_url == 'http://my-blockscout.internal'

    def test_nodereal_rejects_custom_base_url(self) -> None:
        with pytest.raises(ValueError, match='does not support a custom base_url'):
            resolve_scanner_target('nodereal', SELF_HOSTED)

    def test_unknown_scanner_rejects_custom_base_url(self) -> None:
        with pytest.raises(ValueError, match='custom base_url'):
            resolve_scanner_target('moralis', SELF_HOSTED)

    def test_etherscan_proxy_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match='API key required'):
            resolve_scanner_target('etherscan', 'https://eth-proxy.internal', expected_chain_id=1)

    def test_etherscan_proxy_requires_expected_chain_id(self) -> None:
        with pytest.raises(ValueError, match='expected_chain_id'):
            resolve_scanner_target('etherscan', 'https://eth-proxy.internal', api_key='k')

    def test_etherscan_proxy_with_key_and_chain(self) -> None:
        target = resolve_scanner_target(
            'etherscan', 'https://eth-proxy.internal', api_key='k', expected_chain_id=137
        )
        assert target.scanner_name == 'etherscan'
        assert target.scanner_version == 'v2'
        assert target.api_key == 'k'
        assert target.chain_id == 137
        assert target.base_url == 'https://eth-proxy.internal'

    def test_cleartext_with_api_key_warns(self) -> None:
        with pytest.warns(RuntimeWarning, match='cleartext'):
            resolve_scanner_target(
                'etherscan',
                'http://eth-proxy.internal',
                api_key='k',
                expected_chain_id=1,
                allow_http=True,
            )

    def test_aliases_untouched(self) -> None:
        """Known aliases keep resolving exactly as before (backward compat)."""
        target = resolve_scanner_target('blockscout_v2', 'ethereum')
        assert target.base_url is None
        assert target.chain_id == 1
        assert target.network == 'ethereum'


# ============================================================================
# Client wiring: scanner URL construction for self-hosted instances
# ============================================================================


class TestClientCustomBaseUrl:
    async def test_blockscout_v2_scanner_uses_custom_base_url(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        try:
            assert client._scanner.base_url == SELF_HOSTED
            assert client.network == 'custom'
            assert client.chain_id is None
            assert client.api_key == ''

            spec = client._scanner.SPECS[Method.ACCOUNT_BALANCE]
            url = client._scanner._build_url(
                spec, address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
            )
            assert url == (
                f'{SELF_HOSTED}/api/v2/addresses/0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
            )
        finally:
            await client.close()

    async def test_blockscout_v2_custom_base_path(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', 'https://explorer.example.com/bs')
        try:
            spec = client._scanner.SPECS[Method.ACCOUNT_BALANCE]
            url = client._scanner._build_url(
                spec, address='0xabc0000000000000000000000000000000000001'
            )
            assert url.startswith('https://explorer.example.com/bs/api/v2/addresses/')
        finally:
            await client.close()

    async def test_blockscout_v2_expected_chain_id_sets_chain(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED, expected_chain_id=100)
        try:
            assert client.chain_id == 100
            assert client._scanner.chain_id == 100
        finally:
            await client.close()

    async def test_blockscout_v1_scanner_uses_custom_base_url(self) -> None:
        client = ChainscanClient.from_config('blockscout', SELF_HOSTED)
        try:
            assert client._scanner.base_url == SELF_HOSTED
            assert client._scanner.instance_domain is None
        finally:
            await client.close()

    async def test_etherscan_proxy_overrides_api_url(self) -> None:
        client = ChainscanClient.from_config(
            'etherscan', 'https://eth-proxy.internal', api_key='k', expected_chain_id=137
        )
        try:
            assert client._url_builder.API_URL == 'https://eth-proxy.internal'
            assert client._scanner.chain_id == 137
        finally:
            await client.close()

    async def test_alias_path_still_uses_registry_urls(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        try:
            assert client._scanner.base_url == 'https://eth.blockscout.com'
        finally:
            await client.close()


# ============================================================================
# Chain info: probe, cache, validation (offline transport via httpx.MockTransport)
# ============================================================================


def _install_transport(client: ChainscanClient, handler: Any) -> None:
    """Serve all client traffic offline through an httpx MockTransport."""
    client._network._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _blockscout_handler(chain_hex: str = '0x1', calls: list[str] | None = None):
    """Handler serving a BlockScout instance (eth_chainId probe + balance)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(f'{request.method} {request.url.path}')
        if request.url.path == '/api/eth-rpc':
            return httpx.Response(200, json={'jsonrpc': '2.0', 'result': chain_hex, 'id': 1})
        if request.url.path.startswith('/api/v2/addresses/'):
            return httpx.Response(200, json={'hash': '0xabc', 'coin_balance': '42'})
        return httpx.Response(404, json={'message': 'not found'})

    return handler


class TestGetChainInfoBlockscout:
    async def test_probes_chain_id_via_eth_rpc(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        calls: list[str] = []
        _install_transport(client, _blockscout_handler('0x1', calls))
        try:
            info = await client.get_chain_info()
            assert isinstance(info, ChainInfo)
            assert info.chain_id == 1
            assert info.explorer_url == SELF_HOSTED
            assert 'POST /api/eth-rpc' in calls
        finally:
            await client.close()

    async def test_cached_no_second_http_call(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        calls: list[str] = []
        _install_transport(client, _blockscout_handler('0x1', calls))
        try:
            await client.get_chain_info()
            await client.get_chain_info()
            probe_calls = [c for c in calls if c == 'POST /api/eth-rpc']
            assert len(probe_calls) == 1  # second call served from cache
        finally:
            await client.close()


class TestGetChainInfoRegistryBlockScoutV1:
    """The registry path resolves an instance, so it can be probed like a
    custom one — ``base_url`` used to stay None there and the probe refused."""

    async def test_v1_alias_path_probes_the_resolved_instance(self) -> None:
        client = ChainscanClient.from_config('blockscout', 'ethereum')
        calls: list[str] = []
        _install_transport(client, _blockscout_handler('0x1', calls))
        try:
            info = await client.get_chain_info()
            assert info.chain_id == 1
            assert info.explorer_url == 'https://eth.blockscout.com'
            assert 'POST /api/eth-rpc' in calls
        finally:
            await client.close()

    async def test_v1_alias_path_validates_the_chain(self) -> None:
        client = ChainscanClient.from_config('blockscout', 'ethereum')
        _install_transport(client, _blockscout_handler('0x38'))
        try:
            with pytest.raises(ChainscanDataError, match='expected 1, instance serves 56'):
                await client.validate_chain(1)
        finally:
            await client.close()


class TestGetChainInfoEtherscan:
    async def test_chainlist_entry_returned(self) -> None:
        client = ChainscanClient.from_config('etherscan', 'ethereum', api_key='k')
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(f'{request.method} {request.url.path}')
            assert request.url.path == '/v2/chainlist'
            return httpx.Response(200, json=CHAINLIST_PAYLOAD)

        _install_transport(client, handler)
        try:
            info = await client.get_chain_info()
            assert info.chain_id == 1
            assert info.name == 'Ethereum Mainnet'
            assert info.explorer_url == 'https://etherscan.io/'
        finally:
            await client.close()

    async def test_chainlist_downloaded_once_across_clients(self) -> None:
        """~60 networks must not be re-downloaded for every client (shared cache)."""
        http_calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            http_calls.append(request.url.path)
            return httpx.Response(200, json=CHAINLIST_PAYLOAD)

        client1 = ChainscanClient.from_config('etherscan', 'ethereum', api_key='k')
        client2 = ChainscanClient.from_config('etherscan', 'polygon', api_key='k')
        _install_transport(client1, handler)
        _install_transport(client2, handler)
        try:
            await client1.get_chain_info()
            await client2.get_chain_info()
            assert http_calls.count('/v2/chainlist') == 1
            # second client served from the shared cache
        finally:
            await client1.close()
            await client2.close()

    async def test_unknown_chain_raises_data_error(self) -> None:
        client = ChainscanClient.from_config('etherscan', 'ethereum', api_key='k')

        def handler(request: httpx.Request) -> httpx.Response:
            payload = {**CHAINLIST_PAYLOAD, 'result': [CHAINLIST_PAYLOAD['result'][1]]}
            return httpx.Response(200, json=payload)

        _install_transport(client, handler)
        try:
            with pytest.raises(ChainscanDataError, match='chainlist'):
                await client.get_chain_info()
        finally:
            await client.close()


class TestValidateChain:
    async def test_validate_chain_returns_matching_info(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        _install_transport(client, _blockscout_handler('0x1'))
        try:
            info = await client.validate_chain(1)
            assert info.chain_id == 1
        finally:
            await client.close()

    async def test_validate_chain_mismatch_raises(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        _install_transport(client, _blockscout_handler('0x1'))
        try:
            with pytest.raises(ChainscanDataError, match='expected 137, instance serves 1'):
                await client.validate_chain(137)
        finally:
            await client.close()

    async def test_no_expectation_returns_info(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        _install_transport(client, _blockscout_handler('0x64'))
        try:
            info = await client.validate_chain()  # no expected id and no configured id
            assert info.chain_id == 100
        finally:
            await client.close()

    async def test_nodereal_chain_info_unsupported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('NODEREAL_KEY', 'nrkey123')
        client = ChainscanClient.from_config('nodereal', 'bsc')
        try:
            with pytest.raises(ValueError, match='nodereal'):
                await client.get_chain_info()
        finally:
            await client.close()


class TestExpectedChainIdLazyValidation:
    """from_config(expected_chain_id=...) validates before the first request."""

    async def test_mismatch_fails_first_request(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED, expected_chain_id=999)
        _install_transport(client, _blockscout_handler('0x1'))
        try:
            with pytest.raises(ChainscanDataError, match='expected 999, instance serves 1'):
                await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        finally:
            await client.close()

    async def test_mismatch_fails_every_subsequent_request(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED, expected_chain_id=999)
        _install_transport(client, _blockscout_handler('0x1'))
        try:
            with pytest.raises(ChainscanDataError):
                await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
            with pytest.raises(ChainscanDataError):
                await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        finally:
            await client.close()

    async def test_matching_chain_happy_path(self) -> None:
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED, expected_chain_id=1)
        calls: list[str] = []
        _install_transport(client, _blockscout_handler('0x1', calls))
        try:
            balance = await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
            assert balance == '42'
            # validation ran exactly once, then the actual request
            assert calls.count('POST /api/eth-rpc') == 1
            assert any(c.startswith('GET /api/v2/addresses/') for c in calls)
        finally:
            await client.close()

    async def test_alias_config_with_wrong_expectation_fails(self) -> None:
        """expected_chain_id also guards built-in alias configurations."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum', expected_chain_id=137)
        _install_transport(client, _blockscout_handler('0x1'))
        try:
            with pytest.raises(ChainscanDataError):
                await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        finally:
            await client.close()

    async def test_no_expectation_no_probe(self) -> None:
        """Without expected_chain_id nothing is validated and no probe is sent."""
        client = ChainscanClient.from_config('blockscout_v2', SELF_HOSTED)
        calls: list[str] = []
        _install_transport(client, _blockscout_handler('0x1', calls))
        try:
            balance = await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
            assert balance == '42'
            assert calls == ['GET /api/v2/addresses/0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045']
        finally:
            await client.close()
