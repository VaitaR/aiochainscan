"""BlockScout V1 must not declare methods its Etherscan-compat REST layer
does not implement.

``BlockScoutV1.SPECS`` starts from ``EtherscanLikeScanner.SPECS`` wholesale
(see the class body in ``aiochainscan/scanners/blockscout_v1.py``), which
means every Etherscan action gets declared even where BlockScout's own
``/api`` answers ``{"message":"Unknown action"|"Unknown module", "status":
"0"}`` with HTTP 400 instead. A pool falling through to BlockScout for one
of these hits an HTTP/data failure, not the ``MethodNotDeclaredError``
(``method not in scanner.SPECS`` — see ``scanners/base.py::_spec_for``) a
router needs to classify it as capability routing and move on cleanly.

Evidence (live, 2026-09-11, no API key — BlockScout's Etherscan-compat REST
needs none) against independent public instances of the same BlockScout
backend, so a single host's outage cannot explain the shared shape:

    module=token&action=tokeninfo         -> gnosis.blockscout.com:  400 "Unknown action"
    module=gastracker&action=gasestimate  -> polygon/eth-sepolia/base/arbitrum.blockscout.com: 400 "Unknown module"
    module=gastracker&action=gasoracle    -> polygon/eth-sepolia/base/arbitrum.blockscout.com: 400 "Unknown module"
    module=account&action=addresstokenbalance      -> base/eth-sepolia.blockscout.com: 400 "Unknown action"
    module=account&action=addresstokennftinventory -> arbitrum/polygon.blockscout.com: 400 "Unknown action"

All other inherited methods were live-probed too (curl, same session) and
answered ``status=1``/``"OK"`` (or a data-shaped 200 error like "Contract
address not found" for a mainnet-only address probed against an L2 — still
proof the action itself is recognized): ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS,
ACCOUNT_INTERNAL_TXS, ACCOUNT_ERC20_TRANSFERS, ACCOUNT_ERC721_TRANSFERS,
ACCOUNT_ERC1155_TRANSFERS, TX_RECEIPT_STATUS, TX_STATUS_CHECK, BLOCK_REWARD,
BLOCK_COUNTDOWN, BLOCK_NUMBER_BY_TIMESTAMP, CONTRACT_ABI, CONTRACT_SOURCE,
CONTRACT_CREATION, TOKEN_BALANCE, TOKEN_SUPPLY, ETH_SUPPLY, ETH_PRICE. Those
stay declared. TX_BY_HASH, BLOCK_BY_NUMBER, PROXY_ETH_CALL and
PROXY_GET_BALANCE never reach this REST layer at all (BlockScoutV1 detours
them through ``/api/eth-rpc`` JSON-RPC in ``_perform_request`` before the
declared SPECS query is ever built) so this audit does not touch them.

All tests here are offline (SPECS membership only, no network calls).
"""

from __future__ import annotations

from aiochainscan.domain.method import Method
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1

#: Methods BlockScout V1's REST layer answers "Unknown action"/"Unknown
#: module" for (evidence in the module docstring above) — inherited from
#: ``EtherscanLikeScanner.SPECS`` but not actually served.
UNSERVED_METHODS = (
    Method.TOKEN_INFO,
    Method.GAS_ESTIMATE,
    Method.GAS_ORACLE,
    Method.ACCOUNT_TOKEN_PORTFOLIO,
    Method.ACCOUNT_NFT_PORTFOLIO,
)


class TestBlockScoutV1DoesNotOverclaimCapability:
    """Reproduction + regression guard for the TOKEN_INFO capability bug.

    Before the fix every method in ``UNSERVED_METHODS`` (not just
    TOKEN_INFO) was still present in ``BlockScoutV1.SPECS`` because the
    class only overrides ``TOKEN_HOLDERS`` on top of the inherited base —
    this test fails against that state and passes once the fix removes
    exactly those methods.
    """

    def test_unserved_methods_are_not_declared(self) -> None:
        undeclared = [m for m in UNSERVED_METHODS if m in BlockScoutV1.SPECS]
        assert undeclared == [], (
            f'BlockScoutV1.SPECS still declares methods its REST API cannot '
            f'serve: {[str(m) for m in undeclared]}'
        )

    def test_token_info_specifically_is_not_declared(self) -> None:
        # The bug as originally reported: a pool falling through to
        # BlockScout for TOKEN_INFO gets an HTTP 400 instead of a clean
        # MethodNotDeclaredError.
        assert Method.TOKEN_INFO not in BlockScoutV1.SPECS


class TestBlockScoutV1StillDeclaresServedMethods:
    """The audit removes exactly the unserved methods — everything else
    BlockScout V1's REST layer does answer must stay declared."""

    def test_serving_methods_remain_declared(self) -> None:
        still_served = (
            Method.ACCOUNT_BALANCE,
            Method.ACCOUNT_TRANSACTIONS,
            Method.ACCOUNT_INTERNAL_TXS,
            Method.ACCOUNT_ERC20_TRANSFERS,
            Method.ACCOUNT_ERC721_TRANSFERS,
            Method.ACCOUNT_ERC1155_TRANSFERS,
            Method.TX_BY_HASH,
            Method.TX_RECEIPT_STATUS,
            Method.TX_STATUS_CHECK,
            Method.BLOCK_BY_NUMBER,
            Method.BLOCK_REWARD,
            Method.BLOCK_COUNTDOWN,
            Method.BLOCK_NUMBER_BY_TIMESTAMP,
            Method.CONTRACT_ABI,
            Method.CONTRACT_SOURCE,
            Method.CONTRACT_CREATION,
            Method.TOKEN_BALANCE,
            Method.TOKEN_SUPPLY,
            Method.TOKEN_HOLDERS,
            Method.EVENT_LOGS,
            Method.ETH_SUPPLY,
            Method.ETH_PRICE,
            Method.PROXY_ETH_CALL,
            Method.PROXY_GET_BALANCE,
        )
        missing = [m for m in still_served if m not in BlockScoutV1.SPECS]
        assert missing == []
