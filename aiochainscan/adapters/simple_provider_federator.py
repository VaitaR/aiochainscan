from __future__ import annotations

from aiochainscan.capabilities import is_feature_supported
from aiochainscan.ports.provider_federator import ProviderFederator


class SimpleProviderFederator(ProviderFederator):
    """Choose GraphQL when capabilities indicate support, else REST.

    A `preferred` flag can force GraphQL if available.
    """

    def should_use_graphql(
        self, feature: str, *, api_kind: str, network: str, preferred: bool | None = None
    ) -> bool:
        feature_flag = f'{feature}_gql'
        supported = is_feature_supported(feature_flag, api_kind, network)
        if not supported:
            return False
        if preferred is True:
            return True
        return supported
