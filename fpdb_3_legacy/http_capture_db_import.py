"""Import normalized HTTP capture hands into the configured FPDB database."""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from decimal import Decimal
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
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("http_capture_db_import")

SWC_SITE_ID = 23
_NATIVE_CARD_TOKEN_RE = re.compile(r"^10([cdhs])$")

#: SQL for the native board repair. Held as constants written with the MySQL-style
#: ``%s`` marker and adapted to the backend's placeholder the way the entries in
#: ``db.sql.query`` are, rather than interpolated at the call site. Every value
#: still travels as a bound parameter either way -- the only thing that ever
#: varied was the placeholder, which is a property of the driver and not of the
#: data -- but built this way the statement is a constant string, which is what
#: both a reader and a static analyser need in order to see that.
_NATIVE_HAND_LOOKUP_SQL = (
    "SELECT H.id FROM Hands H JOIN Gametypes G ON H.gametypeId=G.id WHERE H.siteHandNo=%s AND G.siteId=%s"
)
_NATIVE_RUN_IT_TWICE_SQL = "UPDATE Hands SET runItTwice=%s WHERE id=%s"
_NATIVE_DELETE_BOARDS_SQL = "DELETE FROM Boards WHERE handId=%s"


#: The Files row every natively captured hand is attached to. Hands.fileId is a
#: non-null foreign key to Files.id on MySQL and PostgreSQL, and real file ids
#: start at 1, so importing with 0 breaks that constraint and rolls the hand back
#: -- on SQLite, which declares no foreign keys, the same import succeeds, which
#: is why this only bites the server backends. One row is reused for the whole
#: capture, as the CoinPoker live path does.
NATIVE_CAPTURE_FILE_NAME = "swc-native-capture"

_native_capture_file_ids: dict[int, int] = {}


def _ensure_capture_file(db: Any) -> int:
    """Return a Files row id the native hands can hang off, creating it once."""
    cached = _native_capture_file_ids.get(id(db))
    if cached:
        return cached
    if not hasattr(db, "get_id") or not hasattr(db, "storeFile"):
        return 0
    try:
        file_id = db.get_id(NATIVE_CAPTURE_FILE_NAME)
        if not file_id:
            now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            file_id = db.storeFile([NATIVE_CAPTURE_FILE_NAME, "SealsWithClubs", now, now, 0, 0, 0, 0, 0, 0, 0, False])
        # get_id() opens a PostgreSQL transaction; the capture then waits on
        # network traffic, so it must not be left holding one idle.
        db.commit()
    except Exception:
        # Falling back to 0 restores the previous behaviour: harmless on SQLite,
        # and on a server backend the foreign key will say so plainly.
        log.warning("Could not create the SwC capture Files row", exc_info=True)
        _rollback_quietly(db)
        return 0
    file_id = int(file_id)
    _native_capture_file_ids[id(db)] = file_id
    return file_id


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
    except Exception:
        # Swallowed so the caller can re-raise the failure that brought us here,
        # but recorded: a rollback that fails is how a connection stays poisoned,
        # and a silent `pass` would leave nothing to read afterwards.
        log.debug("Rollback after a failed native import did not succeed", exc_info=True)


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
    cursor.execute(_NATIVE_HAND_LOOKUP_SQL.replace("%s", placeholder), (site_hand_no, SWC_SITE_ID))
    hand_ids = [row[0] for row in cursor.fetchall()]
    if not hand_ids:
        return None

    update = _NATIVE_RUN_IT_TWICE_SQL.replace("%s", placeholder)
    delete = _NATIVE_DELETE_BOARDS_SQL.replace("%s", placeholder)
    store = db.sql.query["store_boards"].replace("%s", placeholder)
    for hand_id in hand_ids:
        cursor.execute(update, (True, hand_id))
        cursor.execute(delete, (hand_id,))
        for row in rows:
            cursor.execute(store, [hand_id, *row])
    db.commit()
    return hand_ids[0]


#: Native units per displayed unit, by game type. The capture envelope says so of
#: itself (``metadata.money_unit == "room_native_integer"``) and per collection
#: (``native_units_per_display_unit``); the tournament scale is 1 because a
#: tournament chip is the unit, real money is counted in cents.
_NATIVE_UNITS_PER_DISPLAY_UNIT = {"ring": 100, "tour": 1}


def _displayed(value: Any, scale: int) -> str:
    """One native integer as the displayed amount Hand.py expects, or '0'.

    Decimal rather than float division: these become database cents, and 56/100
    has to be exactly 0.56.
    """
    try:
        return str(Decimal(str(value)) / scale)
    except (TypeError, ValueError, ArithmeticError):
        return "0"


def _scale_native_money(candidate: dict[str, Any], scale: int) -> None:
    """Rewrite a native envelope's money in displayed units, in place.

    The envelope counts real money in native integers -- cents -- while
    ``Hand.addPlayer``/``addBlind``/``addCollectPot`` take displayed currency and
    DerivedStats multiplies by 100 on the way to the database. Handing the native
    integers straight to the builder therefore inflated everything a hundredfold:
    a 2/4-cent blind was stored as 200/400, a 10.00 stack as 1000.00. Collections
    were worse than merely unscaled -- they carry no ``amount`` at all, so the
    builder fell back to ``amount_native`` and a 0.56 pot became 56.

    A tournament is left alone: there the native unit already is the chip.
    """
    _scale_keys(candidate.get("gametype"), ("sb", "bb", "ante"), scale)
    for player in candidate.get("players") or ():
        _scale_keys(player, ("starting_stack",), scale)
    for action in candidate.get("actions") or ():
        _scale_keys(action, ("amount", "to"), scale)

    # The room's own rendering is preferred where it exists: it is what the player
    # saw, and it needs no arithmetic to trust. A collection carries no ``amount``
    # of its own, which is why the builder reached for amount_native.
    #
    # ``returned`` is converted for symmetry rather than because anything reads it
    # -- the builder never looks at that key. Its money already reaches Hand.py as
    # the ``uncalled`` actions build_native_canonical_actions derived from it, and
    # the loop above scales those like any other action. Writing ``amount`` here
    # only means the key is already correct should a reader ever appear.
    for item in (*(candidate.get("collections") or ()), *(candidate.get("returned") or ())):
        if not isinstance(item, dict):
            continue
        displayed = item.get("amount_displayed")
        item["amount"] = str(displayed) if displayed is not None else _displayed(item.get("amount_native"), scale)


def _scale_keys(target: Any, keys: tuple[str, ...], scale: int) -> None:
    """Rewrite each present, non-zero key of ``target`` in displayed units."""
    if not isinstance(target, dict):
        return
    for key in keys:
        if target.get(key):
            target[key] = _displayed(target[key], scale)


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
        {**player, "starting_stack": player.get("starting_stack") or 0} for player in hand_data.get("players", [])
    ]
    # The envelope counts real money in native integers (cents); the generic
    # builder hands its amounts to Hand.py as displayed currency. Converting here
    # rather than in the builder keeps the HTTP capture path, whose units are its
    # own, out of it. An envelope that does not say what kind of table it is gets
    # the scale of 1, which is no conversion at all: rescaling money whose unit is
    # unknown would be worse than leaving it alone.
    game_type = (candidate.get("gametype") or {}).get("type")
    scale = _NATIVE_UNITS_PER_DISPLAY_UNIT.get(game_type or "", 1)
    if scale != 1:
        _scale_native_money(candidate, scale)
    return candidate


def _enrich_or_rollback(db: Any, hand_data: dict[str, Any], *, doinsert: bool) -> int | None:
    """Repair an existing hand's boards, undoing a partial write if that fails.

    The repair writes (UPDATE/DELETE/INSERT and a commit) before the import's own
    guarded block begins, so a failure here used to propagate with no rollback --
    leaving a PostgreSQL connection in an aborted transaction that every later
    retry and auto-import cycle on that same connection then failed on too.
    """
    if not doinsert:
        return None
    try:
        return _enrich_existing_native_boards(db, hand_data)
    except Exception:
        _rollback_quietly(db)
        raise


def _import_native_hand(db: Any, hand_data: dict[str, Any], *, doinsert: bool) -> HttpCaptureImportResult:
    repaired_hand_id = _enrich_or_rollback(db, hand_data, doinsert=doinsert)
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
        import_fpdb_hand(hand, db, file_id=_ensure_capture_file(db), doinsert=True)
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


def import_http_capture_directory(
    db: Any, directory: str | Path, *, doinsert: bool = True
) -> list[HttpCaptureImportResult]:
    """Import all normalized hand_*.json files from a capture directory."""

    capture_dir = Path(directory).expanduser()
    results = []
    for path in sorted(capture_dir.glob("hand_*.json")):
        results.append(import_http_capture_file(db, path, doinsert=doinsert))
    return results
