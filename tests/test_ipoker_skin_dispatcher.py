"""Contract tests for the typed iPoker skin registry."""

import pytest

from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.iPoker.dispatcher import IPOKER_SKINS, IPokerSkin, get_parser_class_for_skin


@pytest.mark.parametrize("skin", IPOKER_SKINS, ids=lambda skin: skin.module_name)
def test_registered_ipoker_skin_loads_its_parser(skin: IPokerSkin) -> None:
    parser_class = get_parser_class_for_skin(skin)

    assert issubclass(parser_class, iPoker)
    assert parser_class.__name__ == skin.class_name


def test_ipoker_skin_registry_keys_are_unique() -> None:
    assert len({skin.site_name for skin in IPOKER_SKINS}) == len(IPOKER_SKINS)
    assert len({skin.module_name for skin in IPOKER_SKINS}) == len(IPOKER_SKINS)


def test_missing_skin_uses_base_ipoker_parser() -> None:
    assert get_parser_class_for_skin(None) is iPoker
