from __future__ import annotations

from typing import Any, cast

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
        """https://www.oklink.com/docs/en/#evm-rpc-data-log-get-event-logs"""
        # if url link have oklink prefix so  params startblock and endblock

        """[Beta] The Event Log API was designed to provide an alternative to the native eth_getLogs

        https://github.com/ethereum/wiki/wiki/JSON-RPC#eth_getlogs.
        """
        # Prefer new service path via facade for hexagonal migration
        try:
            from aiochainscan import get_logs as get_logs_facade  # lazy import to avoid cycles

            return await get_logs_facade(
                start_block=self._check_block(start_block),
                end_block=self._check_block(end_block),
                address=address,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
                topics=topics,
                topic_operators=topic_operators,
                page=page,
                offset=offset,
            )
        except Exception:
            result = await self._get(
                action='getLogs',
                address=address,
                fromBlock=self._check_block(start_block),
                toBlock=self._check_block(end_block),
                headers=None,
                **(self._fill_topics(topics, topic_operators) if topics else {}),
                page=page,
                offset=offset,
            )
            return cast(list[dict[str, Any]], result)

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
