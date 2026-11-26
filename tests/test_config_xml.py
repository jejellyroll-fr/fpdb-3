"""The XML adapter callers move to before HUD_config.xml leaves minidom (#453).

Every behaviour is checked on both backends: a caller moved to the adapter must
not notice when the parser behind it switches.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import defusedxml.ElementTree as SafeET
import defusedxml.minidom
import pytest
from defusedxml import EntitiesForbidden

from fpdb_3_legacy import config_xml as cx

EXAMPLE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "HUD_config.xml.example"
COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<!-- before the root -->
<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="config.xsd">
    <general version="95" ui_language="fr"/>
    <sites>
        <!-- the room the HUD opens on -->
        <site name="PokerStars" enabled="True"><alias name="alice"/></site>
        <site name="Winamax" enabled="False"/>
    </sites>
    <stats>
        <ss name="holdem"><stat cell="(1,1)"/><stat cell="(1,2)"/></ss>
    </stats>
</config>
<!-- after the root: passwords are stored in clear text -->
"""


def _canonical(element) -> tuple:
    return (
        element.tag,
        tuple(element.attrib.items()),
        (element.text or "").strip(),
        tuple(_canonical(child) for child in element),
    )


def _meaning(text: str) -> tuple:
    return _canonical(SafeET.fromstring(text.encode("utf-8")))


@pytest.fixture(params=cx.BACKENDS)
def backend(request) -> str:
    return request.param


@pytest.fixture
def doc(backend):
    return cx.parse_string(SAMPLE, backend=backend)


def _site(doc, name):
    return next(site for site in cx.find_all(doc, "site") if cx.attr(site, "name") == name)


# --------------------------------------------------------------------------
# Reading and writing documents
# --------------------------------------------------------------------------


def test_the_backend_is_the_one_asked_for(doc, backend) -> None:
    assert cx.backend_of(doc) == backend
    assert cx.backend_of(cx.root(doc)) == backend


def test_the_default_backend_is_elementtree() -> None:
    assert cx.DEFAULT_BACKEND == cx.ETREE
    assert cx.backend_of(cx.parse_string(SAMPLE)) == cx.ETREE


def test_the_legacy_package_does_not_import_minidom() -> None:
    legacy = Path(__file__).resolve().parents[1] / "fpdb_3_legacy"
    imports_minidom = re.compile(r"^\s*(?:from\s+(?:defusedxml|xml\.dom)\.minidom|import\s+(?:defusedxml|xml\.dom)\.minidom)\b", re.MULTILINE)

    offenders = [path.relative_to(legacy).as_posix() for path in legacy.rglob("*.py") if imports_minidom.search(path.read_text(encoding="utf-8"))]

    assert offenders == []


def test_an_unknown_backend_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown XML backend"):
        cx.parse_string(SAMPLE, backend="lxml")


def test_a_document_is_written_back_with_the_same_meaning(doc) -> None:
    text = cx.to_xml(doc)

    assert text.startswith(cx.XML_DECLARATION)
    assert _meaning(text) == _meaning(SAMPLE)


def test_comments_survive_inside_and_outside_the_root(doc) -> None:
    text = cx.to_xml(doc)

    assert COMMENT.findall(text) == COMMENT.findall(SAMPLE)
    assert text.index("before the root") < text.index("<config")
    assert text.index("</config>") < text.index("after the root")


def test_a_namespace_prefix_is_written_back_as_it_was(doc) -> None:
    text = cx.to_xml(doc)

    assert 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' in text
    assert 'xsi:noNamespaceSchemaLocation="config.xsd"' in text


def test_a_file_parses_like_its_text(tmp_path, backend) -> None:
    path = tmp_path / "config.xml"
    path.write_text(SAMPLE, encoding="utf-8")

    assert _meaning(cx.to_xml(cx.parse_file(path, backend=backend))) == _meaning(SAMPLE)


def test_entity_expansion_is_refused(backend) -> None:
    laughs = '<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><x>&b;</x>'
    with pytest.raises(EntitiesForbidden):
        cx.parse_string(laughs, backend=backend)


def test_a_new_document_has_only_its_root(backend) -> None:
    doc = cx.new_document("fpdb_hud_package", backend=backend)

    assert cx.tag_of(cx.root(doc)) == "fpdb_hud_package"
    assert cx.children(doc) == []
    assert _meaning(cx.to_xml(doc)) == ("fpdb_hud_package", (), "", ())


def test_an_element_is_written_without_what_follows_it(doc) -> None:
    site = _site(doc, "PokerStars")

    text = cx.to_xml(site)

    assert text.startswith("<site ")
    assert text.endswith("</site>")
    assert _meaning(text) == (
        "site",
        (("name", "PokerStars"), ("enabled", "True")),
        "",
        (("alias", (("name", "alice"),), "", ()),),
    )
    # and the document still has the whitespace after it
    assert _meaning(cx.to_xml(doc)) == _meaning(SAMPLE)


def test_the_shipped_template_round_trips(backend) -> None:
    source = EXAMPLE.read_text(encoding="utf-8")

    text = cx.to_xml(cx.parse_file(EXAMPLE, backend=backend))

    assert _meaning(text) == _meaning(source)
    assert COMMENT.findall(text) == COMMENT.findall(source)


def test_elementtree_writes_the_template_with_the_same_meaning() -> None:
    written = cx.to_xml(cx.parse_file(EXAMPLE))

    assert _meaning(written) == _meaning(EXAMPLE.read_text(encoding="utf-8"))
    assert COMMENT.findall(written) == COMMENT.findall(EXAMPLE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Finding elements
# --------------------------------------------------------------------------


def test_find_all_from_a_document_counts_the_root(doc) -> None:
    assert [cx.tag_of(node) for node in cx.find_all(doc, "config")] == ["config"]


def test_find_all_returns_descendants_in_document_order(doc) -> None:
    assert [cx.attr(site, "name") for site in cx.find_all(doc, "site")] == ["PokerStars", "Winamax"]
    assert [cx.attr(stat, "cell") for stat in cx.find_all(doc, "stat")] == ["(1,1)", "(1,2)"]


def test_find_all_from_an_element_leaves_the_element_out(doc) -> None:
    sites = cx.find_first(doc, "sites")

    assert cx.find_all(sites, "sites") == []
    assert len(cx.find_all(sites, "alias")) == 1


def test_the_wildcard_finds_elements_and_never_comments(doc) -> None:
    # On ElementTree, iter("*") also yields the comments a ConfigDocument keeps.
    expected = ["config", "general", "sites", "site", "alias", "site", "stats", "ss", "stat", "stat"]

    assert [cx.tag_of(node) for node in cx.find_all(doc, "*")] == expected
    assert [cx.tag_of(node) for node in cx.find_all(cx.find_first(doc, "sites"), "*")] == ["site", "alias", "site"]
    assert cx.tag_of(cx.find_first(cx.root(doc), "*")) == "general"


def test_find_first_gives_none_when_there_is_none(doc) -> None:
    assert cx.find_first(doc, "missing") is None


def test_children_are_elements_only(doc) -> None:
    sites = cx.find_first(doc, "sites")

    assert [cx.attr(child, "name") for child in cx.children(sites)] == ["PokerStars", "Winamax"]
    assert [cx.tag_of(child) for child in cx.children(doc)] == ["general", "sites", "stats"]
    assert cx.children(sites, "alias") == []


# --------------------------------------------------------------------------
# Attributes
# --------------------------------------------------------------------------


def test_a_missing_attribute_reads_as_the_default(doc) -> None:
    site = _site(doc, "Winamax")

    assert cx.attr(site, "screen_name") == ""
    assert cx.attr(site, "screen_name", "nobody") == "nobody"
    assert cx.has_attr(site, "enabled")
    assert not cx.has_attr(site, "screen_name")


def test_set_attr_writes_the_text_of_the_value(doc) -> None:
    site = _site(doc, "Winamax")

    cx.set_attr(site, "seats", 6)
    cx.set_attr(site, "enabled", True)

    assert cx.attr(site, "seats") == "6"
    assert cx.attr(site, "enabled") == "True"


def test_values_that_need_escaping_come_back_whole(doc, backend) -> None:
    awkward = "Zoë \"Z\" <&> 'q' C:\\Hands & more"
    cx.set_attr(_site(doc, "Winamax"), "screen_name", awkward)

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)

    assert cx.attr(_site(reread, "Winamax"), "screen_name") == awkward


def test_del_attr_removes_it_and_ignores_one_that_is_not_there(doc) -> None:
    site = _site(doc, "Winamax")

    cx.del_attr(site, "enabled")
    cx.del_attr(site, "never_there")

    assert cx.attributes(site) == {"name": "Winamax"}


def test_a_prefixed_attribute_is_read_and_written_by_its_file_name(doc, backend) -> None:
    # ElementTree stores it as "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation".
    config = cx.root(doc)
    name = "xsi:noNamespaceSchemaLocation"

    assert cx.attr(config, name) == "config.xsd"
    assert cx.has_attr(config, name)
    assert cx.attributes(config)[name] == "config.xsd"

    cx.set_attr(config, name, "other.xsd")
    text = cx.to_xml(doc)

    assert text.count("noNamespaceSchemaLocation") == 1, "setting it must not add a second one"
    assert cx.attr(cx.root(cx.parse_string(text, backend=backend)), name) == "other.xsd"

    cx.del_attr(config, name)
    assert not cx.has_attr(config, name)
    assert "noNamespaceSchemaLocation" not in cx.to_xml(doc)


def test_attributes_keep_their_order(doc) -> None:
    cx.set_attr(_site(doc, "PokerStars"), "screen_name", "alice")

    assert list(cx.attributes(_site(doc, "PokerStars"))) == ["name", "enabled", "screen_name"]


# --------------------------------------------------------------------------
# Changing the tree
# --------------------------------------------------------------------------


def test_an_appended_element_is_written_with_its_attributes(doc, backend) -> None:
    sites = cx.find_first(doc, "sites")
    created = cx.create_element(doc, "site", {"name": "Betclic", "enabled": False})

    assert cx.append(doc, sites, created, indent="\n        ") is created

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)
    assert [cx.attr(site, "name") for site in cx.find_all(reread, "site")] == ["PokerStars", "Winamax", "Betclic"]
    assert cx.attributes(_site(reread, "Betclic")) == {"name": "Betclic", "enabled": "False"}


def test_an_indented_element_lines_up_with_its_siblings_on_elementtree() -> None:
    doc = cx.parse_string(SAMPLE, backend=cx.ETREE)
    sites = cx.find_first(doc, "sites")

    cx.append(doc, sites, cx.create_element(doc, "site", {"name": "Betclic"}), indent="\n        ")

    text = cx.to_xml(doc)
    assert '<site name="Winamax" enabled="False" />\n        <site name="Betclic" />\n    </sites>' in text


def test_an_element_appended_to_an_empty_parent(doc, backend) -> None:
    ss = cx.find_first(doc, "ss")
    cx.clear(doc, ss)

    cx.append(doc, ss, cx.create_element(doc, "stat", {"cell": "(1,1)"}), indent="\n")

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)
    assert [cx.attr(stat, "cell") for stat in cx.find_all(reread, "stat")] == ["(1,1)"]


def test_text_lays_out_a_section_with_elementtree() -> None:
    written = []
    for which in cx.BACKENDS:
        document = cx.parse_string(SAMPLE, backend=which)
        stats = cx.find_first(document, "stats")
        cx.clear(document, stats)
        for name in ("a", "b"):
            cx.append_text(document, stats, "\n        ")
            cx.append(document, stats, cx.create_element(document, "ss", {"name": name}))
        cx.append_text(document, stats, "\n    ")
        cx.append_text(document, document, "\n    ")
        cx.append(document, document, cx.create_element(document, "hud_profile_rules"))
        written.append(cx.to_xml(document).replace(" />", "/>"))

    assert '<stats>\n        <ss name="a"/>\n        <ss name="b"/>\n    </stats>' in written[0]
    assert "\n    <hud_profile_rules/></config>" in written[0]


def test_text_in_an_empty_parent(doc) -> None:
    sites = cx.find_first(doc, "sites")
    cx.clear(doc, sites)

    cx.append_text(doc, sites, "\n    ")

    assert "<sites>\n    </sites>" in cx.to_xml(doc)


def test_append_to_a_document_appends_to_its_root(doc) -> None:
    cx.append(doc, doc, cx.create_element(doc, "session_guard", {"max_loss": "5"}))

    assert [cx.tag_of(child) for child in cx.children(doc)] == ["general", "sites", "stats", "session_guard"]


def test_appending_an_element_already_in_the_tree_moves_it(doc, backend) -> None:
    # minidom's appendChild moves a node; ElementTree's append would hold it twice.
    cx.append(doc, cx.find_first(doc, "stats"), _site(doc, "PokerStars"), indent="\n        ")

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)
    assert [cx.attr(site, "name") for site in cx.find_all(reread, "site")] == ["Winamax", "PokerStars"]
    assert [cx.attr(site, "name") for site in cx.children(cx.find_first(reread, "sites"))] == ["Winamax"]
    assert [cx.tag_of(child) for child in cx.children(cx.find_first(reread, "stats"))] == ["ss", "site"]


def test_appending_a_sibling_to_its_own_parent_reorders_it(doc, backend) -> None:
    sites = cx.find_first(doc, "sites")

    cx.append(doc, sites, _site(doc, "PokerStars"))

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)
    assert [cx.attr(site, "name") for site in cx.find_all(reread, "site")] == ["Winamax", "PokerStars"]


def test_insert_before_puts_the_element_ahead_of_its_reference(doc, backend) -> None:
    # A new skin's <hhc> goes ahead of its converter's existing one (#733).
    sites = cx.find_first(doc, "sites")
    cx.insert_before(doc, sites, cx.create_element(doc, "site", {"name": "Betfair"}), _site(doc, "Winamax"))

    text = cx.to_xml(doc)
    reread = cx.parse_string(text, backend=backend)
    assert [cx.attr(site, "name") for site in cx.find_all(reread, "site")] == ["PokerStars", "Betfair", "Winamax"]
    if backend == "etree":
        # Each sibling keeps a line of its own.
        assert '<site name="Betfair" />' in text or '<site name="Betfair"/>' in text
        assert not re.search(r'name="Betfair" ?/><site', text)


def test_insert_before_the_first_child(doc, backend) -> None:
    sites = cx.find_first(doc, "sites")
    cx.insert_before(doc, sites, cx.create_element(doc, "site", {"name": "Betfair"}), _site(doc, "PokerStars"))

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)
    assert [cx.attr(site, "name") for site in cx.find_all(reread, "site")] == ["Betfair", "PokerStars", "Winamax"]


@pytest.mark.parametrize("name", ["PokerStars", "Winamax"])
def test_a_removed_element_leaves_its_siblings(doc, backend, name) -> None:
    cx.remove(doc, _site(doc, name))

    reread = cx.parse_string(cx.to_xml(doc), backend=backend)
    assert [cx.attr(site, "name") for site in cx.find_all(reread, "site")] == [
        other for other in ("PokerStars", "Winamax") if other != name
    ]
    assert COMMENT.findall(cx.to_xml(doc)) == COMMENT.findall(SAMPLE)


def test_the_root_cannot_be_removed_on_elementtree() -> None:
    doc = cx.parse_string(SAMPLE, backend=cx.ETREE)
    with pytest.raises(ValueError, match="root"):
        cx.remove(doc, cx.root(doc))


def test_clear_removes_the_children_and_keeps_the_attributes(doc) -> None:
    ss = cx.find_first(doc, "ss")

    cx.clear(doc, ss)

    assert cx.children(ss) == []
    assert cx.attributes(ss) == {"name": "holdem"}
    assert '<ss name="holdem"' in cx.to_xml(doc)


def test_parent_of(doc) -> None:
    site = _site(doc, "PokerStars")

    assert cx.tag_of(cx.parent_of(doc, site)) == "sites"
    assert cx.parent_of(doc, cx.root(doc)) is None


def test_elementtree_elements_keep_the_legacy_dom_behaviour() -> None:
    element = cx.ConfigElement("site", {"name": "before"})

    assert element
    assert not element.hasChildNodes()
    element.attributes.item(0).value = "after"
    assert element.getAttribute("name") == "after"
    assert 'name="after"' in element.toxml()


def test_deepcopy_preserves_config_element_type_and_parent_links() -> None:
    doc = cx.parse_string(SAMPLE)

    copied = deepcopy(doc)
    site = next(node for node in copied.root.iter("site") if node.get("name") == "PokerStars")

    assert isinstance(copied.root, cx.ConfigElement)
    assert isinstance(site, cx.ConfigElement)
    assert site.parentNode is copied.root.find("sites")


def test_elementtree_element_can_be_imported_into_a_caller_owned_dom() -> None:
    target = defusedxml.minidom.parseString("<target/>")
    source = cx.parse_string(SAMPLE)
    site = cx.find_first(source, "site")

    imported = cx.import_node(target, site)
    target.documentElement.appendChild(imported)

    assert imported.ownerDocument is target
    assert imported.getAttribute("name") == "PokerStars"
    assert imported.firstChild.tagName == "alias"
    assert cx.parent_of(target, imported) is target.documentElement


def test_dom_element_can_be_imported_into_an_elementtree_document() -> None:
    source = defusedxml.minidom.parseString('<profile><ss name="copied"/></profile>')
    target = cx.new_document("package")

    imported = target.importNode(source.documentElement, True)
    target.root.appendChild(imported)

    assert cx.tag_of(imported) == "profile"
    assert cx.attr(cx.find_first(imported, "ss"), "name") == "copied"
    assert imported.parentNode is target.root


def test_a_cloned_document_is_written_the_same_and_edited_apart(doc, backend) -> None:
    clone = cx.clone_document(doc)

    assert cx.backend_of(clone) == backend
    assert cx.to_xml(clone) == cx.to_xml(doc)
    cx.set_attr(_site(clone, "PokerStars"), "name", "Changed")
    cx.remove(clone, _site(clone, "Winamax"))
    assert [cx.attr(site, "name") for site in cx.find_all(doc, "site")] == ["PokerStars", "Winamax"]
    assert COMMENT.findall(cx.to_xml(clone)) == COMMENT.findall(SAMPLE)


def test_an_imported_node_is_a_copy(backend) -> None:
    source = cx.parse_string(SAMPLE, backend=backend)
    target = cx.new_document("package", backend=backend)

    copied = cx.import_node(target, cx.find_first(source, "ss"))
    cx.append(target, cx.root(target), copied)
    cx.set_attr(copied, "name", "renamed")

    assert cx.attr(cx.find_first(source, "ss"), "name") == "holdem"
    assert [cx.attr(stat, "cell") for stat in cx.find_all(target, "stat")] == ["(1,1)", "(1,2)"]
    assert _meaning(cx.to_xml(target))[3][0][1] == (("name", "renamed"),)


def test_preceding_comment_finds_the_comment_written_above(doc) -> None:
    comment = cx.preceding_comment(doc, _site(doc, "PokerStars"))

    assert comment is not None
    assert "the room the HUD opens on" in cx.to_xml(comment)
    assert cx.preceding_comment(doc, _site(doc, "Winamax")) is None
    assert cx.preceding_comment(doc, cx.find_first(doc, "general")) is None


def test_a_comment_can_be_carried_to_another_document(backend) -> None:
    source = cx.parse_string(SAMPLE, backend=backend)
    target = cx.new_document("config", backend=backend)
    comment = cx.preceding_comment(source, _site(source, "PokerStars"))

    cx.append(target, cx.root(target), cx.import_node(target, comment))

    assert "<!-- the room the HUD opens on -->" in cx.to_xml(target)


def test_document_comments_are_the_ones_outside_the_root(backend) -> None:
    text = "<!-- above -->\n<package><!-- inside --><ss/></package>\n<!-- below -->"

    assert cx.document_comments(cx.parse_string(text, backend=backend)) == [" above ", " below "]
    assert cx.document_comments(cx.parse_string("<package/>", backend=backend)) == []


def test_bytes_name_their_encoding(doc, backend) -> None:
    data = cx.to_bytes(doc)

    assert data.startswith(b'<?xml version="1.0" encoding="utf-8"?>')
    reread = cx.parse_string(data, backend=backend)
    assert _meaning(cx.to_xml(reread)) == _meaning(cx.to_xml(doc))


def test_pretty_xml_puts_one_element_per_line(backend) -> None:
    package = cx.new_document("package", backend=backend)
    section = cx.append(package, cx.root(package), cx.create_element(package, "ss", {"name": "mine"}))
    cx.append(package, section, cx.create_element(package, "stat", {"_stat_name": "vpip"}))

    text = cx.to_pretty_xml(package, indent="  ")

    assert text.replace(" />", "/>") == (
        '<?xml version="1.0" ?>\n<package>\n  <ss name="mine">\n    <stat _stat_name="vpip"/>\n  </ss>\n</package>\n'
    )
    assert "\n" not in cx.to_xml(package), "laying the text out leaves the document as it was"


def test_canonical_ignores_layout_and_comments() -> None:
    tight = '<pu b="2" a="1"><pu_stat pu_stat_name="vpip"/>text</pu>'
    loose = '<pu a="1" b="2">\n  <!-- note -->\n  <pu_stat pu_stat_name="vpip"/>\n  text\n</pu>'
    forms = [
        cx.canonical(cx.root(cx.parse_string(text, backend=backend)))
        for backend in cx.BACKENDS
        for text in (tight, loose)
    ]

    assert all(form == forms[0] for form in forms)
    assert forms[0] == ("pu", (("a", "1"), ("b", "2")), (("pu_stat", (("pu_stat_name", "vpip"),), ()), "text"))


def test_canonical_tells_different_content_apart(backend) -> None:
    first = cx.root(cx.parse_string('<pu><pu_stat pu_stat_name="vpip"/></pu>', backend=backend))
    second = cx.root(cx.parse_string('<pu><pu_stat pu_stat_name="pfr"/></pu>', backend=backend))

    assert cx.canonical(first) != cx.canonical(second)


def test_prepend_puts_children_before_the_leading_text() -> None:
    written = []
    for backend in cx.BACKENDS:
        document = cx.parse_string("<s>\n  <old/>\n</s>", backend=backend)
        section = cx.root(document)
        cx.prepend(document, section, [cx.create_element(document, "a"), cx.create_element(document, "b")])
        written.append(cx.to_xml(section).replace(" />", "/>"))

    assert written[0] == "<s><a/><b/>\n  <old/>\n</s>"


def test_prepend_into_an_empty_element(backend) -> None:
    document = cx.parse_string("<s/>", backend=backend)

    cx.prepend(document, cx.root(document), [cx.create_element(document, "a")])

    assert cx.to_xml(cx.root(document)).replace(" />", "/>") == "<s><a/></s>"


def test_a_root_snapshot_can_be_put_back(doc, backend) -> None:
    before = cx.to_xml(doc)
    snapshot = cx.import_node(doc, cx.root(doc))

    cx.remove(doc, _site(doc, "PokerStars"))
    cx.replace_root(doc, snapshot)

    assert cx.to_xml(doc) == before
    assert cx.backend_of(doc) == backend
    assert [cx.attr(site, "name") for site in cx.find_all(doc, "site")] == ["PokerStars", "Winamax"]
