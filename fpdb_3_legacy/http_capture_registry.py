"""Registry for HTTP/WebSocket room capture adapters."""

from __future__ import annotations

from collections.abc import Callable

from fpdb_3_legacy.http_capture_adapter import HttpRoomAdapter
from fpdb_3_legacy.swc_http_adapter import SwCHttpAdapter

AdapterFactory = Callable[[], HttpRoomAdapter]


_ADAPTER_FACTORIES: dict[str, AdapterFactory] = {
    SwCHttpAdapter.site.lower(): SwCHttpAdapter,
    "swc": SwCHttpAdapter,
    "sealswithclubs": SwCHttpAdapter,
    "seals with clubs": SwCHttpAdapter,
}


def get_http_capture_adapter(site: str) -> HttpRoomAdapter:
    """Return a fresh adapter for a captured site name."""

    key = (site or "").strip().lower()
    try:
        return _ADAPTER_FACTORIES[key]()
    except KeyError as exc:
        available = ", ".join(sorted(_ADAPTER_FACTORIES))
        raise ValueError(f"No HTTP capture adapter registered for site '{site}'. Available: {available}") from exc


def registered_http_capture_sites() -> tuple[str, ...]:
    """Return site keys known to the registry."""

    return tuple(sorted(_ADAPTER_FACTORIES))
