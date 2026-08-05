#!/usr/bin/env python3
"""Regression tests for the iPoker skin identity of a converter.

The skin follows from the file path, but only determineGameType() resolved it,
and that runs solely when there is a hand to parse. On a pass that read no new
hands the converter kept the site name the Importer passed in -- the site that
owns the watched directory in the config -- so the auto-import journal reported a
PMU Poker file as "Redbet Poker (no changes)".
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.iPoker.skins.pmu import PMUIPoker

_PMU_PATH = (
    "/Users/x/Library/Containers/fr.pmu.poker.macos/Data/Library/Application Support/"
    "PMU PLAY/hero/History/Data/Tournaments/5868861084.xml"
)
_UNKNOWN_PATH = "/Users/x/History/Data/Tournaments/5868861084.xml"


def _converter(cls, path):
    # sitename is what Importer._import_hh_file passes: the config site owning the
    # watched directory, which for an iPoker skin is not the skin itself.
    return cls(
        MagicMock(),
        in_path=path,
        index=0,
        autostart=False,
        starsArchive=False,
        ftpArchive=False,
        sitename="Redbet Poker",
    )


def test_skin_is_resolved_without_parsing_a_hand():
    hhc = _converter(PMUIPoker, _PMU_PATH)

    assert hhc.sitename == "PMU Poker"


def test_unknown_path_keeps_the_configured_site_name():
    # No skin indicator in the path: the configured name is the best answer we have,
    # so it must not be overwritten with the generic "iPoker".
    hhc = _converter(iPoker, _UNKNOWN_PATH)

    assert hhc.sitename == "Redbet Poker"


def test_stdin_input_keeps_the_configured_site_name():
    hhc = _converter(iPoker, "-")

    assert hhc.sitename == "Redbet Poker"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
