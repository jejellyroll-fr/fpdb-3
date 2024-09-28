import pytest
from unittest.mock import MagicMock, patch
from xml.dom.minidom import Document
import sys


from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from Configuration import *


# Test pour increment_position
def test_increment_position_valid():
    config = Config()
    assert config.increment_position("(0,0)") == "(1,1)"
    assert config.increment_position("(2,3)") == "(3,4)"
    assert config.increment_position("(5,5)") == "(6,6)"


def test_increment_position_invalid_format():
    config = Config()
    with pytest.raises(AssertionError):
        config.increment_position("0,0")
    with pytest.raises(AssertionError):
        config.increment_position("(0,0")
    with pytest.raises(AssertionError):
        config.increment_position("0,0)")


def test_increment_position_negative_values():
    config = Config()
    with pytest.raises(AssertionError):
        config.increment_position("(-1,0)")
    with pytest.raises(AssertionError):
        config.increment_position("(0,-1)")


@pytest.fixture
def config():
    # Création d'une instance de la classe Config avec un document XML vide
    config = Config()
    doc = Document()

    # Création d'un stat set
    statset = doc.createElement("ss")
    statset.setAttribute("name", "hud_test")

    stat = doc.createElement("stat")
    stat.setAttribute("_rowcol", "(1,1)")
    stat.setAttribute("_stat_name", "vpip")

    statset.appendChild(stat)

    doc.appendChild(statset)

    config.doc = doc
    return config


def test_edit_hud(config):
    # Appel de la fonction edit_hud avec des valeurs de test
    config.edit_hud(
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

    # Récupérer le noeud modifié
    statset_node = config.doc.getElementsByTagName("ss")[0]
    stat_node = statset_node.getElementsByTagName("stat")[0]

    # Vérifier que les attributs ont été correctement modifiés
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
