"""Import normalized HTTP capture hands into the configured FPDB database."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpdb_3_legacy.http_capture_ofc import build_ofc_hand, import_ofc_hand


@dataclass(frozen=True)
class HttpCaptureImportResult:
    site_hand_no: str
    kind: str
    row_id: int | None
    replay_ref: str | None
    status: str
    message: str = ""


def is_ofc_capture(hand_data: dict[str, Any]) -> bool:
    """Return whether a normalized HTTP capture hand uses the OFC model."""

    if hand_data.get("ofc_variant") is not None:
        return True
    if (hand_data.get("game") or {}).get("base") == "ofc":
        return True
    return "ofc" in str(hand_data.get("game_type", "")).lower()


def import_http_capture_hand(db: Any, hand_data: dict[str, Any], *, doinsert: bool = True) -> HttpCaptureImportResult:
    """Import one normalized HTTP capture hand and return its DB replay reference."""

    site_hand_no = str(hand_data.get("hand_id") or "")
    if not site_hand_no:
        return HttpCaptureImportResult("", "unknown", None, None, "skipped", "missing hand_id")

    if is_ofc_capture(hand_data):
        ofc_hand = build_ofc_hand(hand_data)
        row_id = import_ofc_hand(db, ofc_hand, doinsert=doinsert)
        return HttpCaptureImportResult(
            site_hand_no=str(ofc_hand.hand_id),
            kind="ofc",
            row_id=row_id,
            replay_ref=f"ofc:{ofc_hand.hand_id}",
            status="imported" if doinsert else "planned",
        )

    return HttpCaptureImportResult(
        site_hand_no=site_hand_no,
        kind=str((hand_data.get("game") or {}).get("base") or "unknown"),
        row_id=None,
        replay_ref=None,
        status="skipped",
        message="HTTP hand is not OFC and is not routed through this importer yet",
    )


def import_http_capture_file(db: Any, path: str | Path, *, doinsert: bool = True) -> HttpCaptureImportResult:
    """Import one normalized hand JSON file."""

    source = Path(path).expanduser()
    hand_data = json.loads(source.read_text(encoding="utf-8"))
    return import_http_capture_hand(db, hand_data, doinsert=doinsert)


def import_http_capture_directory(db: Any, directory: str | Path, *, doinsert: bool = True) -> list[HttpCaptureImportResult]:
    """Import all normalized hand_*.json files from a capture directory."""

    capture_dir = Path(directory).expanduser()
    results = []
    for path in sorted(capture_dir.glob("hand_*.json")):
        results.append(import_http_capture_file(db, path, doinsert=doinsert))
    return results
