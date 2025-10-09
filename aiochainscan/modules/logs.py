from __future__ import annotations

from typing import Any

from aiochainscan.modules.base import BaseModule


class Logs(BaseModule):
    """Logs

    https://docs.etherscan.io/api-endpoints/logs
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    _TOPIC_OPERATORS = ('and', 'or')
    _BLOCKS = ('latest',)

    @property
    def _module(self) -> str:
        return 'logs'

    async def get_logs(
        self,
        start_block: int | str,
        end_block: int | str,
        address: str,
        page: int | str | None = None,
        offset: int | str | None = None,
        topics: list[str] | None = None,  # Make topics optional
        topic_operators: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Event Log API for retrieving contract event logs"""

        """[Beta] The Event Log API was designed to provide an alternative to the native eth_getLogs

        https://github.com/ethereum/wiki/wiki/JSON-RPC#eth_getlogs.
        """
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.logs import get_logs as _svc_get_logs

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        # Preserve original topic filling for tests
        extra = self._fill_topics(topics, topic_operators) if topics else {}
        return await _svc_get_logs(
            start_block=self._check_block(start_block),
            end_block=self._check_block(end_block),
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            topics=None,
            topic_operators=None,
            page=page,
            offset=offset,
            extra_params=extra,
        )

    def _check_block(self, block: str | int) -> str | int:
        if isinstance(block, int):
            return block
        if block in self._BLOCKS:
            return block
        raise ValueError(
            f'Invalid value {block!r}, only integers or {self._BLOCKS} are supported.'
        )

    def _fill_topics(self, topics: list[str], topic_operators: list[str] | None) -> dict[str, str]:
        if topics and len(topics) > 1:
            self._check_topics(topics, topic_operators)

            topic_params = {f'topic{idx}': value for idx, value in enumerate(topics)}
            topic_operator_params = {
                f'topic{idx}_{idx + 1}_opr': value
                for idx, value in enumerate(topic_operators or [])
            }

            return {**topic_params, **topic_operator_params}
        elif topics:
            return {'topic0': topics[0]}
        else:
            return {}  # Return an empty dictionary if topics is None

    def _check_topics(self, topics: list[str], topic_operators: list[str] | None) -> None:
        if not topic_operators:
            raise ValueError('Topic operators are required when more than 1 topic passed.')

        for op in topic_operators:
            if op not in self._TOPIC_OPERATORS:
                raise ValueError(
                    f'Invalid topic operator {op!r}, must be one of: {self._TOPIC_OPERATORS}'
                )

        if len(topics) - (len(topic_operators) if topic_operators else 0) != 1:
            raise ValueError('Invalid length of topic_operators list, must be len(topics) - 1.')
