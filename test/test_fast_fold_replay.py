"""Raw Winamax FastFold replay contract tests.

The fixture deliberately keeps the original log lines.  The parser output is a
derived assertion, so changes to batching or event ordering cannot silently
change the capture contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from fpdb_3_legacy.winamax_live_log_reader import WinamaxLiveLogReader

FIXTURE = Path(__file__).parent / "fixtures" / "winamax_fastfold" / "macos_escape_replay.json"


def test_raw_winamax_fastfold_replay_reconstructs_one_table() -> None:
    capture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    updates = []
    reader = WinamaxLiveLogReader(on_table_update=updates.append)

    for line in capture["raw_log"]:
        reader.process_line(line, notify=False)
    reader._flush_pending()

    assert len(updates) == 1
    update = updates[0]
    assert update.table_no == capture["expected"]["table_no"]
    assert update.hand_id == capture["expected"]["hand_id"]
    assert update.hero == capture["expected"]["hero"]
    assert update.ring == capture["expected"]["ring"]
