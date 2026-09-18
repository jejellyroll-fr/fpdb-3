#!/usr/bin/env python3
"""Inspect, validate and enable the context-aware HUD panel rules (#298).

The HUD keeps drawing its static grid until a ``<hud_panel_rules>`` section
turns dynamic panels on. This tool is how a user gets there without writing
JSON by hand:

* ``--list`` / ``--show`` print the shipped library and which panels each rule
  can put on screen;
* ``--resolve`` runs the resolver on a context given on the command line, so a
  rule can be checked before it reaches a table;
* ``--validate`` reports what loads but cannot do what it says (a panel no block
  carries, a fallback that is its own panel, two rules with one selector);
* ``--enable`` prints the one-line section to paste into ``HUD_config.xml``,
  and ``--export`` writes the rules as JSON.

Examples::

    python tools/hud_panels.py --list
    python tools/hud_panels.py --show srp-cbet-ip
    python tools/hud_panels.py --resolve --street flop --pot-type single_raised --in-position
    python tools/hud_panels.py --resolve --street turn --facing-sizing-pct 25 --sample n=120
    python tools/hud_panels.py --validate --panels "core,srp_cbet_ip,overbet_river"
    python tools/hud_panels.py --enable --profile holdring_modern
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpdb_3_legacy import hud_situation as hs  # noqa: E402


def _samples(values: list[str] | None) -> dict[str, int]:
    """``--sample n=120`` pairs into a sample mapping."""
    samples: dict[str, int] = {}
    for entry in values or []:
        name, sep, value = entry.partition("=")
        if not sep:
            raise SystemExit(f"--sample must read name=value, got {entry!r}")
        try:
            samples[name.strip()] = int(value)
        except ValueError:
            raise SystemExit(f"--sample value must be an integer, got {entry!r}") from None
    return samples


def _context(args: argparse.Namespace) -> hs.HudSituationContext:
    context = hs.HudSituationContext(
        in_position=_in_position_flag(args),
        street=args.street or "preflop",
        street_index=hs.STREETS.index(args.street) if args.street in hs.STREETS else 0,
        pot_type=args.pot_type or "",
        position=args.position or "",
        opponent_position=args.opponent_position or "",
        role=args.role or "",
        effective_stack_bb=args.stack or 0,
        facing_action=args.action_faced or "",
        facing_sizing_bp=(args.facing_sizing_pct or 0) * 100,
        sizing_bp=(args.sizing_pct or 0) * 100,
        to_call=args.to_call if args.to_call is not None else 0,
        players_in_hand=args.players or 0,
        is_preflop_aggressor=bool(args.is_preflop_aggressor),
        is_aggressor=bool(args.is_aggressor),
        labels=tuple(args.label or ()),
    )
    return context.normalized()


def _in_position_flag(args: argparse.Namespace) -> bool | None:
    """The three-state position flag: in, out, or unknown."""
    if args.in_position and args.out_of_position:
        raise SystemExit("--in-position and --out-of-position are mutually exclusive")
    if args.in_position:
        return True
    if args.out_of_position:
        return False
    return None


def _cmd_list(resolver: hs.HudSituationResolver) -> int:
    for rule in resolver.rules:
        name = rule.rule_id or rule.panel
        print(f"{name:<26} -> {rule.panel:<24} profile={rule.profile:<12} priority={rule.priority}")
        for condition, value in rule.when.items():
            print(f"    {condition} = {json.dumps(value, default=str)}")
    print(f"\nfallback panel: {resolver.fallback or '(none)'}")
    return 0


def _cmd_show(resolver: hs.HudSituationResolver, name: str) -> int:
    for rule in resolver.rules:
        if name not in (rule.rule_id, rule.panel):
            continue
        print(f"rule {rule.rule_id or '(unnamed)'}")
        print(f"  panel       : {rule.panel}")
        print(f"  profile     : {rule.profile}")
        print(f"  priority    : {rule.priority}")
        print(f"  conditions  : {json.dumps(dict(rule.when), indent=4, default=str)}")
        print(f"  min_sample  : {rule.min_sample or '(none)'} (from {rule.sample})")
        print(f"  fallback    : {rule.fallback or '(none)'}")
        print(f"  enabled     : {rule.enabled}")
        if rule.substitutions:
            print(f"  substitutions: {json.dumps(dict(rule.substitutions))}")
        if rule.description:
            print(f"  description : {rule.description}")
        return 0
    raise SystemExit(f"Unknown rule or panel {name!r}; try --list")


def _cmd_resolve(resolver: hs.HudSituationResolver, args: argparse.Namespace) -> int:
    context = _context(args)
    selection = resolver.resolve(context, args.profile, samples=_samples(args.sample))
    print(f"context : {context.describe()}")
    print(f"profile : {selection.profile} (enabled={selection.enabled})")
    print(f"panels  : {', '.join(selection.panels) or '(none)'}")
    for panel in selection.panels:
        rule = selection.decided_by(panel)
        print(f"  {panel:<24} <- {rule.rule_id if rule else 'fallback'}")
    if selection.suppressed:
        print(f"withheld: {', '.join(selection.suppressed)} (below min_sample)")
    return 0


def _cmd_validate(resolver: hs.HudSituationResolver, args: argparse.Namespace) -> int:
    panels = [name.strip() for name in (args.panels or "").split(",") if name.strip()]
    warnings = hs.validate_rules(resolver, panels)
    for warning in warnings:
        print(f"warning: {warning}")
    duplicates = resolver.duplicate_selectors()
    for selector in duplicates:
        print(f"duplicate selector: {selector!r}")
    print(f"{len(resolver.rules)} rule(s), {len(warnings)} warning(s)")
    return 0 if not warnings else 1


def _cmd_enable(args: argparse.Namespace) -> int:
    """Print the section that turns the shipped library on."""
    attributes = ['enabled="true"', 'source="builtin"']
    if args.fallback:
        attributes.append(f'fallback="{args.fallback}"')
    print("<hud_panel_rules " + " ".join(attributes) + ">")
    print("</hud_panel_rules>")
    if args.profile:
        print(
            f"\n# Rules are scoped per profile: add profile=\"{args.profile}\" to a\n"
            "# <hud_panel_rule> to keep a rule to that profile only, or edit the\n"
            "# shipped library and point source= at your own directory."
        )
    return 0


def _cmd_export(resolver: hs.HudSituationResolver, args: argparse.Namespace) -> int:
    target = Path(args.export)
    hs.save_rules(resolver.rules, target, fallback=resolver.fallback)
    print(f"wrote {len(resolver.rules)} rule(s) to {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", action="append", default=[], help="extra rule directory (repeatable)")
    parser.add_argument("--list", action="store_true", help="list every rule")
    parser.add_argument("--show", metavar="RULE", help="show one rule by id or panel")
    parser.add_argument("--resolve", action="store_true", help="resolve the panels for a context")
    parser.add_argument("--validate", action="store_true", help="report suspicious rules")
    parser.add_argument("--enable", action="store_true", help="print the HUD_config.xml section")
    parser.add_argument("--export", metavar="PATH", help="write the rules as JSON")
    parser.add_argument("--panels", help="comma-separated block labels, for --validate")
    parser.add_argument("--profile", help="HUD profile to scope the rules to")
    parser.add_argument("--fallback", help="fallback panel when nothing matches")
    parser.add_argument("--sample", action="append", help="sample override, e.g. n=120")
    # The context flags.
    parser.add_argument("--street", choices=hs.STREETS)
    parser.add_argument("--pot-type", choices=hs.POT_TYPES)
    parser.add_argument("--position")
    parser.add_argument("--opponent-position")
    parser.add_argument("--role", choices=hs.ROLES)
    parser.add_argument("--stack", type=int, help="effective stack in big blinds")
    parser.add_argument("--players", type=int, help="players dealt in")
    parser.add_argument("--action-faced", help="the action the seat is facing")
    parser.add_argument("--facing-sizing-pct", type=int)
    parser.add_argument("--sizing-pct", type=int)
    parser.add_argument("--to-call", type=int)
    parser.add_argument("--label", action="append", help="a situation label (repeatable)")
    parser.add_argument("--in-position", action="store_true")
    parser.add_argument("--out-of-position", action="store_true")
    parser.add_argument("--is-preflop-aggressor", action="store_true")
    parser.add_argument("--is-aggressor", action="store_true")
    args = parser.parse_args(argv)

    resolver = hs.load_default_resolver(args.dir)
    if args.fallback:
        resolver = hs.HudSituationResolver(resolver.rules, fallback=args.fallback)

    if args.enable:
        return _cmd_enable(args)
    if args.export:
        return _cmd_export(resolver, args)
    if args.validate:
        return _cmd_validate(resolver, args)
    if args.show:
        return _cmd_show(resolver, args.show)
    if args.resolve:
        return _cmd_resolve(resolver, args)
    return _cmd_list(resolver)


if __name__ == "__main__":
    raise SystemExit(main())
