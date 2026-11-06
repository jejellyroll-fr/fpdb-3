"""Inspect, validate and export the declarative popup packs (#299).

A pack is data: ``popup_packs.d/*.json`` describing a hierarchy of HUD popups --
class, rows, labels and submenu links -- validated against the live stat
catalogue (native ``Stats.py`` functions plus the declarative descriptors) and
compiled into the popup objects the HUD reads. This tool answers what ships and
what a link costs, without opening the HUD:

    python tools/popup_packs.py --list
    python tools/popup_packs.py --show preflop --samples
    python tools/popup_packs.py --validate
    python tools/popup_packs.py --export-xml srp_turn
    python tools/popup_packs.py --link-into holdring_modern --pack analytics

Nothing is written: ``--export-xml`` prints the ``<pu>`` element for
``HUD_config.xml``, and ``--link-into`` prints the one ``<pu_stat>`` row that
points an existing popup at a pack's root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy import popup_packs as packs  # noqa: E402


def _registry(extra_dirs: list[str]) -> packs.PackRegistry:
    return packs.load_default_registry(extra_dirs)


def _list(registry: packs.PackRegistry) -> int:
    for name in registry.names():
        pack = registry.get(name)
        print(f"{name}: {pack.description or '(no description)'} [root {pack.root}, {len(pack.nodes)} popup(s)]")
    if not registry.names():
        print("no popup packs found")
    return 0


def _validate(registry: packs.PackRegistry, dirs: list[str]) -> int:
    warnings = registry.validate()
    popups = len(registry.all_nodes())
    print(f"{len(registry.names())} pack(s), {popups} popup(s) valid")
    for warning in warnings:
        print(f"  warning: {warning}")
    if not dirs:
        print(f"packaged directory: {packs.default_packs_dir()}")
    return 0


def _show(registry: packs.PackRegistry, name: str, with_samples: bool) -> int:
    """Show a pack's tree, or one popup of any pack by its own name."""
    for pack_name in registry.names():
        pack = registry.get(pack_name)
        if name in pack.nodes:
            print(packs.format_node(pack.nodes[name], with_samples=with_samples))
            return 0
    print(packs.format_pack(registry.get(name), with_samples=with_samples))
    return 0


def _export_xml(registry: packs.PackRegistry, names: list[str]) -> int:
    """Print the ``<pu>`` elements for a popup of any pack, or a pack's root."""
    for wanted in names:
        for pack_name in registry.names():
            pack = registry.get(pack_name)
            if wanted in pack.nodes:
                print(pack.nodes[wanted].to_xml())
                break
        else:
            raise SystemExit(f"No pack has a popup named {wanted!r}")
    return 0


def _link_into(registry: packs.PackRegistry, popup: str, pack_name: str) -> int:
    """Print the row that points an existing popup at a pack's root."""
    pack = registry.get(pack_name)
    print(f"Add this row to the <pu pu_name={popup!r}> element in HUD_config.xml:")
    print(f'    <pu_stat pu_stat_name="{pack.label_text()}" pu_stat_submenu="{pack.root}"/>')
    print(f"Or, at runtime, call popup_packs.link_pack(config, {popup!r}, pack).")
    return 0


def main() -> int:
    args = _parse_args()
    registry = _registry(args.dir)
    if args.list:
        return _list(registry)
    if args.show:
        return _show(registry, args.show, args.samples)
    if args.validate:
        return _validate(registry, args.dir)
    if args.export_xml:
        return _export_xml(registry, args.export_xml)
    if args.link_into:
        if not args.pack:
            raise SystemExit("--link-into needs --pack")
        return _link_into(registry, args.link_into, args.pack)
    raise SystemExit("give --list, --show, --validate, --export-xml or --link-into")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", action="append", default=[], help="extra pack directory (repeatable)")
    parser.add_argument("--list", action="store_true", help="list every known pack")
    parser.add_argument("--show", metavar="PACK", default=None, help="print one pack's popup tree")
    parser.add_argument("--samples", action="store_true", help="with --show, include the sample column")
    parser.add_argument("--validate", action="store_true", help="load and check every pack, reporting warnings")
    parser.add_argument("--export-xml", dest="export_xml", action="append", default=[], help="popup name (repeatable)")
    parser.add_argument("--link-into", dest="link_into", metavar="POPUP", default=None, help="an existing popup")
    parser.add_argument("--pack", default=None, help="with --link-into, the pack to point at")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
