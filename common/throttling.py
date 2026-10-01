from typing import Any

from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from common.client_ip import get_client_ip, rate_limit_identity


class ClientIPScopedRateThrottle(ScopedRateThrottle):
    """ScopedRateThrottle keyed on the resolved client IP.

    DRF's default get_ident() uses the raw X-Forwarded-For header, so an
    anonymous client could get a fresh bucket per request by varying it.
    """

    def get_ident(self, request: Request) -> str:
        return rate_limit_identity(get_client_ip(request))


class ActionScopedRateThrottleMixin:
    throttle_classes = [ClientIPScopedRateThrottle]
    throttle_scope_prefix: str | None = None
    # Maps an action name, or an (action, method) pair, to a throttle scope.
    throttle_scope_action_map: dict[Any, str] = {}

    def get_throttles(self) -> list[BaseThrottle]:
        throttle_scope = self.get_throttle_scope()
        if throttle_scope is None:
            return []
        self.throttle_scope = throttle_scope
        throttles: list[BaseThrottle] = super().get_throttles()  # type: ignore[misc]  # mixed into an APIView
        return throttles

    def get_throttle_scope(self) -> str | None:
        action = getattr(self, "action", None)
        request = getattr(self, "request", None)
        if request is None or self.throttle_scope_prefix is None:
            return None
        if action is None:
            action_map = getattr(self, "action_map", {})
            action = action_map.get(request.method.lower())
        if action is None:
            return None

        method = request.method.lower()
        if (action, method) in self.throttle_scope_action_map:
            return self.throttle_scope_action_map[(action, method)]
        if action in self.throttle_scope_action_map:
            return self.throttle_scope_action_map[action]
        return f"{self.throttle_scope_prefix}_default"
