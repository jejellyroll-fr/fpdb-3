"""Turn a live capture on, for tests about what follows the user's yes (#451)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy import live_capture_consent
from fpdb_3_legacy.live_capture_consent import Mechanism


def turned_on(monkeypatch: pytest.MonkeyPatch, directory: Path, *mechanisms: Mechanism) -> Path:
    """Answer yes to ``mechanisms`` in a file of ``directory``, and make fpdb read that file."""
    answers = directory / live_capture_consent.CONSENT_NAME
    for mechanism in mechanisms:
        live_capture_consent.accept(mechanism, answers)
    monkeypatch.setattr(live_capture_consent, "consent_path", lambda *_args, **_kwargs: answers)
    return answers
