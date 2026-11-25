"""Environment-aware frontend origin allow-list helpers."""
from __future__ import annotations

from collections.abc import Iterable


def resolve_frontend_origins(
    default_origins: Iterable[str],
    configured_value: str | None,
    environment: str | None,
) -> set[str]:
    """Resolve browser origins without inheriting production domains in staging.

    Existing production and development deployments preserve the default plus
    configured origin behaviour. Staging starts from an empty allow-list and
    accepts only explicitly configured HTTP(S) origins.
    """
    is_staging = str(environment or "").strip().casefold() == "staging"
    origins = set() if is_staging else set(default_origins)

    for item in str(configured_value or "").split(","):
        origin = item.strip().rstrip("/")
        if origin.startswith(("https://", "http://")) and origin != "*":
            origins.add(origin)

    return origins
