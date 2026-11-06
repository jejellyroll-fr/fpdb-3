from xml.dom.minidom import Document, parseString

import pytest

from fpdb_3_legacy.Configuration import Config, RawHands, RawTourneys


def test_edit_fav_seat_creates_missing_fav_nodes() -> None:
    # A site config may ship <fav> nodes for only some table sizes (CoinPoker had
    # 2/6/9/10). Editing a preferred seat for a missing size (a 5-max table) must
    # create the node, not silently drop the choice.
    xml = (
        "<FreePokerToolsConfig><supported_sites>"
        '<site site_name="CoinPoker" enabled="False">'
        '<fav max="2" fav_seat="0"/><fav max="6" fav_seat="0"/>'
        "</site></supported_sites></FreePokerToolsConfig>"
    )
    config = Config()
    config.doc = parseString(xml)

    config.edit_fav_seat(
        "CoinPoker", "True",
        seat2_dict="0", seat3_dict="0", seat4_dict="0", seat5_dict="3",
        seat6_dict="0", seat7_dict="0", seat8_dict="0", seat9_dict="0", seat10_dict="0",
    )

    site = config.get_site_node("CoinPoker")
    favs = {f.getAttribute("max"): f.getAttribute("fav_seat") for f in site.getElementsByTagName("fav")}
    assert favs["5"] == "3"  # was missing, now created and persisted
    assert set(favs) == {"2", "3", "4", "5", "6", "7", "8", "9", "10"}
    assert site.getAttribute("enabled") == "True"


# Test for increment_position
def test_increment_position_valid() -> None:
    config = Config()
    assert config.increment_position("(0,0)") == "(1,1)"
    assert config.increment_position("( 0 , 0 )") == "(1,1)"
    assert config.increment_position("(2,3)") == "(3,4)"
    assert config.increment_position("(5,5)") == "(6,6)"


def test_increment_position_invalid_format() -> None:
    config = Config()
    with pytest.raises(AssertionError):
        config.increment_position("0,0")
    with pytest.raises(AssertionError):
        config.increment_position("(0,0")
    with pytest.raises(AssertionError):
        config.increment_position("0,0)")
    with pytest.raises(AssertionError):
        config.increment_position("(one,0)")


def test_increment_position_negative_values() -> None:
    config = Config()
    with pytest.raises(AssertionError):
        config.increment_position("(-1,0)")
    with pytest.raises(AssertionError):
        config.increment_position("(0,-1)")


@pytest.mark.parametrize("config_class", [RawHands, RawTourneys])
def test_raw_history_compression_is_validated_independently(config_class) -> None:
    doc = Document()
    node = doc.createElement("raw")
    node.setAttribute("save", "all")
    node.setAttribute("compression", "invalid")

    raw_history = config_class(node)

    assert raw_history.save == "all"
    assert raw_history.compression == "none"


@pytest.fixture
def cfg_fixture():
    # Create instance
    config = Config()
    doc = Document()

    # Crate stat set
    statset = doc.createElement("ss")
    statset.setAttribute("name", "hud_test")

    stat = doc.createElement("stat")
    stat.setAttribute("_rowcol", "(1,1)")
    stat.setAttribute("_stat_name", "vpip")

    statset.appendChild(stat)

    doc.appendChild(statset)

    config.doc = doc
    return config


def test_edit_hud(cfg_fixture) -> None:
    # call function edit_hud with test data
    cfg_fixture.edit_hud(
        hud_name="hud_test",
        position="(0,0)",
        stat_name="pfr",
        click="True",
        hudcolor="#F44336",
        hudprefix="P",
        hudsuffix="S",
        popup="default",
        stat_hicolor="#000000",
        stat_hith="high",
        stat_locolor="#FFFFFF",
        stat_loth="low",
        tip="Some tip",
    )

    # Get modified node
    statset_node = cfg_fixture.doc.getElementsByTagName("ss")[0]
    stat_node = statset_node.getElementsByTagName("stat")[0]

    # checks
    assert stat_node.getAttribute("_stat_name") == "pfr"
    assert stat_node.getAttribute("click") == "True"
    assert stat_node.getAttribute("hudcolor") == "#F44336"
    assert stat_node.getAttribute("hudprefix") == "P"
    assert stat_node.getAttribute("hudsuffix") == "S"
    assert stat_node.getAttribute("popup") == "default"
    assert stat_node.getAttribute("stat_hicolor") == "#000000"
    assert stat_node.getAttribute("stat_hith") == "high"
    assert stat_node.getAttribute("stat_locolor") == "#FFFFFF"
    assert stat_node.getAttribute("stat_loth") == "low"
    assert stat_node.getAttribute("tip") == "Some tip"
