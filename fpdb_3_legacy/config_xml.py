"""The few XML operations fpdb's configuration code needs, on minidom or ElementTree (#453).

``HUD_config.xml`` is read and written through ``minidom`` today. #453 moves it
to ``ElementTree``. Callers move first, file by file, from the DOM API to the
functions below; each one accepts a minidom node or an ElementTree element, so a
migrated caller behaves the same before and after the parser itself switches.

On the ElementTree side, a :class:`ConfigDocument` stands for the document. It
keeps what minidom kept and a bare ElementTree loses:

- comments, inside the root and outside it (the warning that email passwords
  are stored in clear text sits after ``</FreePokerToolsConfig>``);
- namespace prefixes, so ``xsi:noNamespaceSchemaLocation`` is written back as
  such rather than as ``ns0:``.

Parsing goes through ``defusedxml`` on both sides: no entity expansion, no DTD
retrieval, no external resources.
"""

from __future__ import annotations

import copy

# ElementTree builds and writes the trees; nothing here parses with it. Every
# parse goes through defusedxml (parse_string, parse_file).
import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405  # nosemgrep
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import defusedxml.ElementTree
import defusedxml.minidom

MINIDOM = "minidom"
ETREE = "etree"
BACKENDS = (MINIDOM, ETREE)

# What parse_file / parse_string build when the caller does not say. The switch
# of #453 is this one value.
DEFAULT_BACKEND = MINIDOM

XML_DECLARATION = '<?xml version="1.0" ?>'

# What parsing a malformed file raises on ElementTree (minidom raises
# xml.parsers.expat.ExpatError); defusedxml's refusals are DefusedXmlException.
ParseError = ET.ParseError

# Prefixes ElementTree has replaced by "{uri}" in the attribute names it read, so
# that callers can keep writing "xsi:noNamespaceSchemaLocation" on either backend.
# Process-wide, like ElementTree's own register_namespace: a prefix the files
# declare names the same namespace everywhere they use it.
_PREFIX_URIS: dict[str, str] = {"xml": "http://www.w3.org/XML/1998/namespace"}

Node = Any  # a minidom Document or Element, a ConfigDocument, or an ElementTree Element


@dataclass(eq=False)
class ConfigDocument:
    """An XML document on ElementTree that keeps its comments and namespace prefixes."""

    root: ET.Element
    before_root: list[Any] = field(default_factory=list)
    after_root: list[Any] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)


class _Builder:
    """A parser target that keeps what ElementTree drops: top-level comments and namespace prefixes."""

    def __init__(self) -> None:
        self._tree = ET.TreeBuilder(insert_comments=True, insert_pis=True)
        self._depth = 0
        self._root_seen = False
        self.before_root: list[Any] = []
        self.after_root: list[Any] = []
        self.namespaces: dict[str, str] = {}

    def _outside(self, node: Any) -> None:  # a comment or a processing instruction
        (self.after_root if self._root_seen else self.before_root).append(node)

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self._depth += 1
        self._root_seen = True
        return self._tree.start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self._depth -= 1
        return self._tree.end(tag)

    def data(self, text: str) -> None:
        # Whitespace between top-level nodes has nowhere to live, as in minidom.
        if self._depth:
            self._tree.data(text)

    def comment(self, text: str) -> ET.Element | None:
        if self._depth:
            return self._tree.comment(text)
        self._outside(ET.Comment(text))
        return None

    def pi(self, target: str, text: str | None = None) -> ET.Element | None:
        if self._depth:
            return self._tree.pi(target, text)
        self._outside(ET.ProcessingInstruction(target, text))
        return None

    def start_ns(self, prefix: str, uri: str) -> None:
        self.namespaces.setdefault(prefix, uri)

    def close(self) -> ET.Element:
        return self._tree.close()


# --------------------------------------------------------------------------
# Reading and writing documents
# --------------------------------------------------------------------------


def _check_backend(backend: str | None) -> str:
    chosen = DEFAULT_BACKEND if backend is None else backend
    if chosen not in BACKENDS:
        msg = f"Unknown XML backend {chosen!r}; expected one of {BACKENDS}"
        raise ValueError(msg)
    return chosen


def _parse_etree(data: bytes | str) -> ConfigDocument:
    builder = _Builder()
    parser = defusedxml.ElementTree.XMLParser(target=builder)
    parser.feed(data)
    root = parser.close()
    for prefix, uri in builder.namespaces.items():
        if prefix:
            _PREFIX_URIS.setdefault(prefix, uri)
    return ConfigDocument(root, builder.before_root, builder.after_root, builder.namespaces)


def parse_string(text: bytes | str, *, backend: str | None = None) -> Node:
    """A document from XML text."""
    if _check_backend(backend) == MINIDOM:
        return defusedxml.minidom.parseString(text)
    return _parse_etree(text)


def parse_file(path: str | Path, *, backend: str | None = None) -> Node:
    """A document from an XML file."""
    if _check_backend(backend) == MINIDOM:
        return defusedxml.minidom.parse(str(path))
    return _parse_etree(Path(path).read_bytes())


def new_document(root_tag: str, *, backend: str | None = None) -> Node:
    """An empty document whose root element is ``root_tag``."""
    if _check_backend(backend) == MINIDOM:
        return defusedxml.minidom.parseString(f"<{root_tag}/>")
    return ConfigDocument(ET.Element(root_tag))


def backend_of(node: Node) -> str:
    """The backend a node belongs to."""
    return MINIDOM if _is_dom(node) else ETREE


def _is_dom(node: Node) -> bool:
    # Every DOM node has a nodeType; ElementTree elements and ConfigDocument do not.
    return hasattr(node, "nodeType")


def _element_xml(element: ET.Element) -> str:
    # tostring writes the tail too: the whitespace after an element is not part of it.
    tail, element.tail = element.tail, None
    try:
        return ET.tostring(element, encoding="unicode")
    finally:
        element.tail = tail


def to_xml(node: Node) -> str:
    """A document (with its XML declaration) or one element, as text."""
    if _is_dom(node):
        return node.toxml()
    if isinstance(node, ConfigDocument):
        for prefix, uri in node.namespaces.items():
            if prefix:
                ET.register_namespace(prefix, uri)
        parts = [XML_DECLARATION]
        parts.extend(_element_xml(top) for top in node.before_root)
        parts.append(_element_xml(node.root))
        parts.extend(_element_xml(top) for top in node.after_root)
        return "".join(parts)
    return _element_xml(node)


def to_bytes(doc: Node, encoding: str = "utf-8") -> bytes:
    """A document as encoded bytes, its XML declaration naming the encoding (``toxml(encoding=...)``)."""
    if _is_dom(doc):
        return doc.toxml(encoding=encoding)
    body = to_xml(doc).removeprefix(XML_DECLARATION)
    return f'<?xml version="1.0" encoding="{encoding}"?>{body}'.encode(encoding)


def to_pretty_xml(doc: Node, indent: str = "    ") -> str:
    """A document built without layout whitespace, one element per line (``toprettyxml``)."""
    if _is_dom(doc):
        return doc.toprettyxml(indent=indent)
    laid_out = copy.deepcopy(root(doc))
    ET.indent(laid_out, space=indent)
    return f"{XML_DECLARATION}\n{_element_xml(laid_out)}\n"


def canonical(node: Node) -> Any:
    """An element as data: its tag, its sorted attributes and its children, layout whitespace aside.

    Text counts once stripped and comments not at all, so two elements that say
    the same thing compare equal however they are indented, on either backend.
    """
    node = _element(node)
    if _is_dom(node):
        parts: list[Any] = []
        for child in node.childNodes:
            if child.nodeType == child.TEXT_NODE:
                parts.append(child.data.strip())
            elif child.nodeType == child.ELEMENT_NODE:
                parts.append(canonical(child))
        return (node.tagName, tuple(sorted(attributes(node).items())), tuple(part for part in parts if part))
    parts = [(node.text or "").strip()]
    for child in node:
        if _is_element(child):
            parts.append(canonical(child))
        parts.append((child.tail or "").strip())
    return (node.tag, tuple(sorted(attributes(node).items())), tuple(part for part in parts if part))


# --------------------------------------------------------------------------
# Finding elements
# --------------------------------------------------------------------------


def root(doc: Node) -> Node:
    """The root element of a document."""
    if isinstance(doc, ConfigDocument):
        return doc.root
    return doc.documentElement


def _element(node: Node) -> Node:
    """``node`` itself, or the root element when it is a document."""
    if isinstance(node, ConfigDocument):
        return node.root
    if _is_dom(node) and node.nodeType == node.DOCUMENT_NODE:
        return node.documentElement
    return node


def _is_element(node: Any) -> bool:
    # ElementTree comments and processing instructions are elements whose tag is a function.
    return isinstance(node.tag, str)


def find_all(node: Node, tag: str) -> list[Node]:
    """Every element named ``tag`` below ``node``, in document order (``getElementsByTagName``).

    For a document, the root element counts; for an element, the element itself does not.
    ``"*"`` matches every element, and never a comment or a processing instruction.
    """
    if _is_dom(node):
        return list(node.getElementsByTagName(tag))
    if isinstance(node, ConfigDocument):
        return [found for found in node.root.iter(tag) if _is_element(found)]
    return [found for found in node.iter(tag) if found is not node and _is_element(found)]


def find_first(node: Node, tag: str) -> Node | None:
    """The first element named ``tag`` below ``node``, or None."""
    found = find_all(node, tag)
    return found[0] if found else None


def children(node: Node, tag: str | None = None) -> list[Node]:
    """The element children of ``node`` (no text, no comments), optionally only those named ``tag``.

    A document's children are its root element's.
    """
    node = _element(node)
    if _is_dom(node):
        found = [child for child in node.childNodes if child.nodeType == child.ELEMENT_NODE]
        return [child for child in found if tag is None or child.tagName == tag]
    return [child for child in node if _is_element(child) and (tag is None or child.tag == tag)]


def tag_of(node: Node) -> str:
    """An element's name."""
    return node.tagName if _is_dom(node) else node.tag


# --------------------------------------------------------------------------
# Attributes
# --------------------------------------------------------------------------


# Attribute names are written as in the file on both backends: "xsi:noNamespaceSchemaLocation",
# never ElementTree's "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation".


def _etree_name(name: str) -> str:
    """ElementTree's key for an attribute name that may carry a known prefix."""
    prefix, colon, local = name.partition(":")
    uri = _PREFIX_URIS.get(prefix) if colon else None
    return f"{{{uri}}}{local}" if uri else name


def _file_name(key: str) -> str:
    """An ElementTree attribute key as the file writes it."""
    if not key.startswith("{"):
        return key
    uri, _, local = key[1:].partition("}")
    prefix = next((prefix for prefix, known in _PREFIX_URIS.items() if known == uri), None)
    return f"{prefix}:{local}" if prefix else key


def attr(node: Node, name: str, default: str = "") -> str:
    """An attribute's value, or ``default`` when the element has none (``getAttribute`` gives "")."""
    if _is_dom(node):
        return node.getAttribute(name) if node.hasAttribute(name) else default
    return node.get(_etree_name(name), default)


def has_attr(node: Node, name: str) -> bool:
    if _is_dom(node):
        return node.hasAttribute(name)
    return _etree_name(name) in node.attrib


def set_attr(node: Node, name: str, value: object) -> None:
    """Set an attribute; the value is written as ``str(value)``."""
    if _is_dom(node):
        node.setAttribute(name, str(value))
    else:
        node.set(_etree_name(name), str(value))


def del_attr(node: Node, name: str) -> None:
    """Remove an attribute if the element has it."""
    if _is_dom(node):
        if node.hasAttribute(name):
            node.removeAttribute(name)
    else:
        node.attrib.pop(_etree_name(name), None)


def attributes(node: Node) -> dict[str, str]:
    """All attributes, in the order the element holds them, named as in the file.

    minidom also lists namespace declarations (``xmlns:xsi``) as attributes;
    ElementTree keeps them apart, on the document.
    """
    if _is_dom(node):
        return dict(node.attributes.items())
    return {_file_name(key): value for key, value in node.attrib.items()}


# --------------------------------------------------------------------------
# Changing the tree
# --------------------------------------------------------------------------


def create_element(doc: Node, tag: str, attrs: Mapping[str, object] | None = None) -> Node:
    """A new element owned by ``doc``, not yet in the tree."""
    if _is_dom(doc):
        element = doc.createElement(tag)
    else:
        element = ET.Element(tag)
    for name, value in (attrs or {}).items():
        set_attr(element, name, value)
    return element


def _last_whitespace(node: ET.Element) -> str | None:
    """The text before ``node``'s closing tag."""
    kids = list(node)
    return kids[-1].tail if kids else node.text


def _set_last_whitespace(node: ET.Element, text: str | None) -> None:
    kids = list(node)
    if kids:
        kids[-1].tail = text
    else:
        node.text = text


def append(doc: Node, parent: Node, child: Node, *, indent: str | None = None) -> Node:
    """Add ``child`` as the last child of ``parent``, after ``indent`` whitespace when given.

    A document as ``parent`` means its root element. A ``child`` already in the
    tree moves: it leaves its current place, as minidom's ``appendChild`` does.

    On ElementTree the whitespace that closed ``parent`` keeps closing it, so an
    appended element lines up with its siblings instead of hugging the closing tag.
    """
    parent = _element(parent)
    if _is_dom(parent):
        if indent is not None:
            parent.appendChild(doc.createTextNode(indent))
        parent.appendChild(child)
        return child
    if parent_of(doc, child) is not None:
        remove(doc, child)
    if indent is not None:
        # The new element takes over the closing whitespace; the indent goes before it.
        closing = _last_whitespace(parent)
        _set_last_whitespace(parent, indent)
        child.tail = closing
    parent.append(child)
    return child


def insert_before(doc: Node, parent: Node, child: Node, reference: Node) -> Node:
    """Add ``child`` to ``parent`` just before its child ``reference``.

    On ElementTree the new element takes the whitespace that preceded
    ``reference``, and ``reference`` keeps it, so both line up with their
    siblings. A ``child`` already in the tree moves, as minidom's does.
    """
    parent = _element(parent)
    if _is_dom(parent):
        parent.insertBefore(child, reference)
        return child
    if parent_of(doc, child) is not None:
        remove(doc, child)
    siblings = list(parent)
    index = siblings.index(reference)
    child.tail = siblings[index - 1].tail if index else parent.text
    parent.insert(index, child)
    return child


def append_text(doc: Node, parent: Node, text: str) -> None:
    """Add ``text`` after the last child of ``parent`` (minidom's ``appendChild(createTextNode(text))``).

    Used for the whitespace that lays a section out: the line break and indent
    before each child, and the one before the closing tag.
    """
    parent = _element(parent)
    if _is_dom(parent):
        parent.appendChild(doc.createTextNode(text))
        return
    _set_last_whitespace(parent, (_last_whitespace(parent) or "") + text)


def parent_of(doc: Node, node: Node) -> Node | None:
    """The element holding ``node``, or None for the root."""
    if _is_dom(node):
        parent = node.parentNode
        return None if parent is None or parent.nodeType == parent.DOCUMENT_NODE else parent
    for candidate in root(doc).iter():
        for child in candidate:
            if child is node:
                return candidate
    return None


def remove(doc: Node, node: Node) -> None:
    """Take ``node`` out of the tree.

    On ElementTree, what followed it takes the place of the whitespace that preceded it.
    """
    if _is_dom(node):
        node.parentNode.removeChild(node)
        return
    parent = parent_of(doc, node)
    if parent is None:
        msg = "The root element cannot be removed"
        raise ValueError(msg)
    siblings = list(parent)
    index = siblings.index(node)
    if index:
        siblings[index - 1].tail = node.tail
    else:
        parent.text = node.tail
    parent.remove(node)


def clear(doc: Node, node: Node) -> None:
    """Remove every child of ``node``: elements, text and comments. Its attributes stay."""
    del doc
    if _is_dom(node):
        while node.firstChild is not None:
            node.removeChild(node.firstChild)
        return
    for child in list(node):
        node.remove(child)
    node.text = None


def clone_document(doc: Node) -> Node:
    """A deep copy of a whole document, the comments around its root included."""
    if _is_dom(doc):
        return doc.cloneNode(True)
    return copy.deepcopy(doc)


def prepend(doc: Node, parent: Node, children: list[Node]) -> None:
    """Put ``children``, in order, before everything ``parent`` holds (its leading text included)."""
    parent = _element(parent)
    if _is_dom(parent):
        first = parent.firstChild
        for child in children:
            parent.insertBefore(child, first)
        return
    lead, parent.text = parent.text, None
    for index, child in enumerate(children):
        if parent_of(doc, child) is not None:
            remove(doc, child)
        child.tail = None
        parent.insert(index, child)
    if children:
        children[-1].tail = lead
    else:
        parent.text = lead


def replace_root(doc: Node, new_root: Node) -> None:
    """Make ``new_root`` (an element of ``doc``'s backend, not in the tree) the document's root."""
    if _is_dom(doc):
        doc.replaceChild(new_root, doc.documentElement)
        return
    doc.root = new_root


def import_node(doc: Node, node: Node) -> Node:
    """A deep copy of ``node`` (from any document of the same backend) that ``doc`` can hold."""
    if _is_dom(doc):
        return doc.importNode(node, True)
    copied = copy.deepcopy(node)
    copied.tail = None
    return copied


def preceding_comment(doc: Node, node: Node) -> Node | None:
    """The comment written immediately above ``node`` (only whitespace between), or None."""
    if _is_dom(node):
        sibling = node.previousSibling
        while sibling is not None and sibling.nodeType == sibling.TEXT_NODE and not sibling.data.strip():
            sibling = sibling.previousSibling
        if sibling is not None and sibling.nodeType == sibling.COMMENT_NODE:
            return sibling
        return None
    parent = parent_of(doc, node)
    siblings = doc.before_root + [doc.root] if parent is None else list(parent)
    index = next(i for i, sibling in enumerate(siblings) if sibling is node)
    if not index:
        return None
    previous = siblings[index - 1]
    if previous.tag is not ET.Comment or (previous.tail or "").strip():
        return None
    return previous


def document_comments(doc: Node) -> list[str]:
    """The text of each comment outside the root element, above it then below it, in file order."""
    if _is_dom(doc):
        return [node.data for node in doc.childNodes if node.nodeType == node.COMMENT_NODE]
    return [node.text or "" for node in doc.before_root + doc.after_root if node.tag is ET.Comment]
