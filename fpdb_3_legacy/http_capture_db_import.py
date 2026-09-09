"""Import normalized HTTP capture hands into the configured FPDB database."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.Exceptions import FpdbHandDuplicate
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    HttpCaptureHandConfig,
    build_fpdb_hand,
    import_fpdb_hand,
)
from fpdb_3_legacy.http_capture_ofc import build_ofc_hand, import_ofc_hand

SWC_SITE_ID = 23
_NATIVE_CARD_TOKEN_RE = re.compile(r"^10([cdhs])$")


def _rollback_quietly(db: Any) -> None:
    """Undo an incomplete write, never masking the failure that prompted it.

    Used on the error path, where the exception being handled is the one worth
    reporting: a rollback that fails as well (a connection already gone) must
    not replace it.
    """
    rollback = getattr(db, "rollback", None)
    if rollback is None:
        return
    try:
        rollback()
    except Exception:  # noqa: BLE001 - the original error is the one to raise
        pass


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


def is_native_capture(hand_data: dict[str, Any]) -> bool:
    """Return whether a normalized hand came from the native SwC tap."""

    return (hand_data.get("metadata") or {}).get("adapter") == "swc_native"


def _legacy_native_card_tokens(value: Any) -> Any:
    """Convert native ``10x`` card tokens to Hand.py's legacy ``Tx`` form."""

    if isinstance(value, str):
        match = _NATIVE_CARD_TOKEN_RE.fullmatch(value)
        return f"T{match.group(1)}" if match else value
    if isinstance(value, list):
        return [_legacy_native_card_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: _legacy_native_card_tokens(item) for key, item in value.items()}
    return value


def _native_board_rows(hand_data: dict[str, Any]) -> list[list[int]]:
    """Return complete native boards in the ``Boards`` table shape."""

    boards = hand_data.get("boards")
    if not isinstance(boards, list) or len(boards) <= 1:
        return []
    normalized = _legacy_native_card_tokens(boards)
    rows = []
    for board_id, board in enumerate(normalized, start=1):
        if not isinstance(board, dict):
            return []
        cards = [card for street in ("FLOP", "TURN", "RIVER") for card in board.get(street, [])]
        if len(cards) < 5:
            return []
        rows.append([board_id, *[Card.encodeCard(card) for card in cards[:5]]])
    return rows


def _enrich_existing_native_boards(db: Any, hand_data: dict[str, Any]) -> int | None:
    """Repair boards on an already-imported hand using native card evidence.

    Only the run-it-twice flag and Boards rows are repaired here. ``bombPot`` is
    intentionally left untouched because the existing hand-history import stores
    the total bomb-pot amount in cents, while native capture currently exposes
    only a boolean bomb-pot marker. Replacing the stored amount with 0/1 would
    corrupt metadata that was already correct.
    """

    rows = _native_board_rows(hand_data)
    if not rows or not hasattr(db, "get_cursor") or not hasattr(db, "sql"):
        return None
    placeholder = db.sql.query["placeholder"]
    cursor = db.get_cursor()
    site_hand_no = hand_data.get("hand_id")
    if site_hand_no is not None:
        try:
            site_hand_no = int(site_hand_no)
        except (TypeError, ValueError):
            pass
    lookup = (
        "SELECT H.id FROM Hands H JOIN Gametypes G ON H.gametypeId=G.id "
        f"WHERE H.siteHandNo={placeholder} AND G.siteId={placeholder}"
    )
    cursor.execute(lookup, (site_hand_no, SWC_SITE_ID))
    hand_ids = [row[0] for row in cursor.fetchall()]
    if not hand_ids:
        return None

    update = f"UPDATE Hands SET runItTwice={placeholder} WHERE id={placeholder}"
    delete = f"DELETE FROM Boards WHERE handId={placeholder}"
    store = db.sql.query["store_boards"].replace("%s", placeholder)
    for hand_id in hand_ids:
        cursor.execute(update, (True, hand_id))
        cursor.execute(delete, (hand_id,))
        for row in rows:
            cursor.execute(store, [hand_id, *row])
    db.commit()
    return hand_ids[0]


def _native_public_import_copy(hand_data: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare a complete native public hand for the legacy Hand.py importer.

    Native captures do not reliably expose private cards or starting stacks, but
    they can still contain a complete public hand: every action is assigned to
    a player and exact action amounts reconcile with settlement. Importing only
    that conservative subset preserves HUD/stat data without inventing actions.
    Unknown stacks are represented as zero because Hand.py requires a value;
    the original opaque native values remain in the capture envelope.
    """
    if not is_native_capture(hand_data) or (hand_data.get("game") or {}).get("base") != "hold":
        return None
    audit = (hand_data.get("metadata") or {}).get("importability") or {}
    required = (
        audit.get("complete_action_players") is True,
        audit.get("settlement_conservation_complete") is True,
        audit.get("has_small_blind") is True,
        audit.get("has_big_blind") is True,
        audit.get("has_collection") is True,
        bool(hand_data.get("actions")),
        bool(hand_data.get("players")),
    )
    if not all(required):
        return None

    candidate = _legacy_native_card_tokens(hand_data)
    candidate["game"] = {**(hand_data.get("game") or {}), "fpdb_supported": True}
    candidate["players"] = [
        {**player, "starting_stack": player.get("starting_stack") or 0}
        for player in hand_data.get("players", [])
    ]
    return candidate


def _import_native_hand(db: Any, hand_data: dict[str, Any], *, doinsert: bool) -> HttpCaptureImportResult:
    repaired_hand_id = _enrich_existing_native_boards(db, hand_data) if doinsert else None
    candidate = _native_public_import_copy(hand_data)
    site_hand_no = str(hand_data.get("hand_id") or "")
    if candidate is None:
        if repaired_hand_id is not None:
            return HttpCaptureImportResult(
                site_hand_no,
                "native",
                repaired_hand_id,
                f"native:{site_hand_no}",
                "updated",
                "existing hand board metadata repaired",
            )
        return HttpCaptureImportResult(
            site_hand_no=site_hand_no,
            kind=str((hand_data.get("game") or {}).get("base") or "unknown"),
            row_id=None,
            replay_ref=None,
            status="skipped",
            message="native hand is incomplete or its settlement is not proven",
        )
    if not doinsert:
        return HttpCaptureImportResult(site_hand_no, "native", None, f"native:{site_hand_no}", "planned")

    try:
        config = HttpCaptureHandConfig(site_ids={"SealsWithClubs": SWC_SITE_ID, "default": SWC_SITE_ID})
        hand = build_fpdb_hand(candidate, config=config)
        if hasattr(db, "resetBulkCache"):
            db.resetBulkCache()
        import_fpdb_hand(hand, db, file_id=0, doinsert=True)
    except CaptureNotImportableError as error:
        return HttpCaptureImportResult(site_hand_no, "native", None, None, "skipped", str(error))
    except FpdbHandDuplicate:
        if hasattr(db, "rollback"):
            db.rollback()
        if repaired_hand_id is not None:
            return HttpCaptureImportResult(
                site_hand_no,
                "native",
                repaired_hand_id,
                f"native:{site_hand_no}",
                "updated",
                "existing hand board metadata repaired",
            )
        return HttpCaptureImportResult(
            site_hand_no, "native", None, f"native:{site_hand_no}", "duplicate", "hand already imported"
        )
    except Exception:
        # Any other failure -- a transient HandsPlayers insert error, the
        # database going away mid-hand -- can leave an uncommitted Hands row on
        # this connection. The caller treats such a failure as non-terminal and
        # retries on the *same* connection, where duplicate detection would see
        # that uncommitted row, the FpdbHandDuplicate handler above would roll it
        # back, and the hand would be retired as "already imported" while never
        # having reached the database. Undo the partial write before the retry.
        _rollback_quietly(db)
        raise

    return HttpCaptureImportResult(
        site_hand_no,
        "native",
        getattr(hand, "dbid_hands", None),
        f"native:{site_hand_no}",
        "imported",
    )


def import_http_capture_hand(db: Any, hand_data: dict[str, Any], *, doinsert: bool = True) -> HttpCaptureImportResult:
    """Import one normalized HTTP capture hand and return its DB replay reference."""

    site_hand_no = str(hand_data.get("hand_id") or "")
    if not site_hand_no:
        return HttpCaptureImportResult("", "unknown", None, None, "skipped", "missing hand_id")

    if is_native_capture(hand_data):
        return _import_native_hand(db, hand_data, doinsert=doinsert)

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
