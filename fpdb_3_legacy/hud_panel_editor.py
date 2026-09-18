"""The model behind the Dynamic Panels tab (issue #309).

The rule engine of #298 is data: a panel name plus conditions in the analytics
filter vocabulary, with a sample threshold, a fallback and a priority. A user
should not have to hand-write that JSON, and an editor should not have to
re-invent what it means. This module is the half in between, and it is **Qt
free** on purpose: every question the tab asks -- which selectors exist, whether
two rules conflict, which rule wins for a context and *why*, what a stat choice
is and where a popup binds it, what an exported file looks like -- is answered
here, so it can be tested without a window and reused by ``tools/``.

Three commitments shape it:

* **The resolver is the authority.** A preview does not re-implement precedence:
  it asks :meth:`HudSituationResolver.matching_rules` for the order and
  :meth:`HudSituationResolver.resolve` for the panels, then explains the order in
  words. If the engine's precedence changes, the preview changes with it.
* **A condition name is never invented.** Every selector offered by the editor
  is checked against ``analytics_query.FILTERS`` (see :func:`selector_fields` and
  its test), so the tab cannot offer a condition the engine would refuse to
  evaluate -- and it cannot offer one it would evaluate *differently*.
* **An import never lies about what it could not read.** A document from a newer
  version imports, keeps what it does not understand, and reports it, rather
  than silently dropping half of a user's work.

The tab itself lives in ``modern_hud_preferences/main_dialog.py``; the CLI half
of the same feature is ``tools/hud_panels.py``. Units and the configuration
section: ``docs/dynamic-panels.md``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, NamedTuple

from fpdb_3_legacy import hud_situation as hs

# What the editor writes for a dimension the user has not constrained. Spelled
# out is not the same as absent: "ANY" is a choice, and an empty combo is a
# mistake the user cannot see.
ANY: Final = "ANY"

# The document kind and version of an exported panel document. A file carries
# its own kind so importing the wrong thing is an error and not a puzzle.
PANEL_DOCUMENT_KIND: Final = "fpdb-hud-panels"
PANEL_DOCUMENT_VERSION: Final = 1


# --------------------------------------------------------------------------- #
# The selector vocabulary.
# --------------------------------------------------------------------------- #


class SelectorField(NamedTuple):
    """One condition the editor can write, and how a user picks it.

    ``kind`` decides the widget: a ``set`` is a combo (with ``choices`` when the
    vocabulary is closed, a free text field when it is not), a ``bool`` is a
    three-state combo (true / false / unconstrained), a ``range`` takes two
    optional numbers. ``group`` is what the tab groups the widgets by, so the
    form reads as the hand it describes.
    """

    name: str
    label: str
    kind: str
    choices: tuple[str, ...] = ()
    group: str = ""


_POSITIONS: Final = ("BTN", "SB", "BB", "CO", "MP", "EP")
_TRUE_FALSE: Final = ("true", "false")

# The selectors the issue lists, plus the handful the shipped library already
# uses. The order is the form's order: table, then who, then the decision, then
# the stacks, then the money.
SELECTOR_FIELDS: Final[tuple[SelectorField, ...]] = (
    SelectorField("profile", "HUD profile", "set", group="Table"),
    SelectorField("site", "Site", "set", group="Table"),
    SelectorField("game", "Game", "set", group="Table"),
    SelectorField("limit", "Limit", "set", group="Table"),
    SelectorField("seats", "Table size", "set", group="Table"),
    SelectorField("tournament", "Tournament", "bool", _TRUE_FALSE, group="Table"),
    SelectorField("position", "Hero position", "set", _POSITIONS, group="Who"),
    SelectorField("opponent_position", "Opponent position", "set", _POSITIONS, group="Who"),
    SelectorField("in_position", "In position", "bool", _TRUE_FALSE, group="Who"),
    SelectorField("relative_position", "Seats after hero", "range", (), group="Who"),
    SelectorField("street", "Street", "set", hs.STREETS, group="Decision"),
    SelectorField("street_index", "Street index", "range", (), group="Decision"),
    SelectorField("pot_type", "Pot type", "set", hs.POT_TYPES, group="Decision"),
    SelectorField("action_faced", "Action faced", "set", ("bets", "raises", "calls", "checks"), group="Decision"),
    SelectorField("action_taken", "Action taken", "set", ("bets", "raises", "calls", "checks", "folds"), group="Decision"),
    SelectorField("role", "Role", "set", hs.ROLES, group="Decision"),
    SelectorField("is_preflop_aggressor", "Raised preflop", "bool", _TRUE_FALSE, group="Decision"),
    SelectorField("is_aggressor", "Aggressor", "bool", _TRUE_FALSE, group="Decision"),
    SelectorField("is_previous_aggressor", "Previous aggressor", "bool", _TRUE_FALSE, group="Decision"),
    SelectorField("facing_all_in", "Facing all-in", "bool", _TRUE_FALSE, group="Decision"),
    SelectorField("players_in_hand", "Players in hand", "range", (), group="Decision"),
    SelectorField("multiway", "Multiway", "bool", _TRUE_FALSE, group="Decision"),
    SelectorField("situation", "Situation label", "set", (), group="Decision"),
    SelectorField("situation_group", "Situation group", "set", (), group="Decision"),
    SelectorField("primary_situation", "Primary situation", "set", (), group="Decision"),
    SelectorField("stack_bucket", "Stack bucket", "set", ("short", "medium", "deep"), group="Stacks"),
    SelectorField("effective_stack_bb", "Effective stack (bb)", "range", (), group="Stacks"),
    SelectorField("spr", "SPR", "range", (), group="Stacks"),
    SelectorField("to_call", "To call (cents)", "range", (), group="Money"),
    SelectorField("facing_sizing_pct", "Sizing faced (% pot)", "range", (), group="Money"),
    SelectorField("bet_sizing_pct", "Own sizing (% pot)", "range", (), group="Money"),
    SelectorField("pot_before", "Pot before (cents)", "range", (), group="Money"),
)

# The range fields whose pair is `[null, 0]`-shaped and therefore decides
# whether a rule like "the raiser checked and it is on me" can be written.
_LOWER_OPEN: Final = ("relative_position", "players_in_hand", "spr", "effective_stack_bb")


def selector_fields() -> tuple[SelectorField, ...]:
    """Every selector the editor offers, in form order."""
    return SELECTOR_FIELDS


def selector_field(name: str) -> SelectorField | None:
    for entry in SELECTOR_FIELDS:
        if entry.name == name:
            return entry
    return None


def _text(value: Any, default: str = "") -> str:
    """The canonical spelling of a name, as the panel layer compares it."""
    text = str(value or "").strip()
    return text.casefold() if text else default


def fill_choices(fields: Iterable[SelectorField], **vocabularies: Sequence[str]) -> tuple[SelectorField, ...]:
    """The selectors with their open vocabularies filled from the running app.

    ``site``, ``game``, ``limit``, ``seats`` and the situation words are known
    only to the configuration and the situation model, so the tab passes them in
    rather than the editor guessing a list that another module owns.
    """
    filled: list[SelectorField] = []
    for entry in fields:
        values = vocabularies.get(entry.name)
        filled.append(entry._replace(choices=tuple(values)) if values is not None else entry)
    return tuple(filled)


# --------------------------------------------------------------------------- #
# A rule being edited.
# --------------------------------------------------------------------------- #


@dataclass
class PanelRuleDraft:
    """One rule as the editor holds it: selectors plus behaviour.

    Deliberately a *draft* of :class:`~fpdb_3_legacy.hud_situation.PanelRule`
    rather than a rule: a half-filled form is a normal state inside an editor
    and an error outside it, so the conversion is one explicit call
    (:meth:`to_rule`) that fails with the loader's own message.
    """

    panel: str = ""
    profile: str = "all"
    rule_id: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)
    min_sample: int = 0
    sample: str = "n"
    fallback: str = ""
    priority: int = 0
    enabled: bool = True
    section: str = ""
    label: str = ""
    description: str = ""

    @classmethod
    def from_rule(cls, rule: hs.PanelRule) -> PanelRuleDraft:
        """The draft of an existing rule, so editing starts from what it says."""
        return cls(
            panel=rule.panel,
            profile=rule.profile,
            rule_id=rule.rule_id,
            conditions={str(name): _copyable(value) for name, value in rule.when.items()},
            min_sample=rule.min_sample,
            sample=rule.sample,
            fallback=rule.fallback,
            priority=rule.priority,
            enabled=rule.enabled,
            section=rule.section,
            label=rule.label,
            description=rule.description,
        )

    def to_rule(self, order: int = 0) -> hs.PanelRule:
        """The rule this draft describes, validated by the loader.

        Raises the loader's ``ValueError`` -- an unknown condition name, an empty
        panel -- because the message a user gets from a failed save should be the
        message they would get from a hand-edited file.
        """
        return hs.PanelRule.from_mapping(self.as_mapping(), order)

    def as_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"panel": self.panel, "profile": self.profile or "all"}
        if self.rule_id:
            payload["id"] = self.rule_id
        if self.conditions:
            payload["when"] = dict(self.conditions)
        for key, value in (
            ("min_sample", self.min_sample),
            ("priority", self.priority),
            ("fallback", self.fallback),
            ("sample", "" if self.sample == "n" else self.sample),
            ("section", self.section),
            ("label", self.label),
            ("description", self.description),
        ):
            if value:
                payload[key] = value
        if not self.enabled:
            payload["enabled"] = False
        return payload

    def describe(self) -> str:
        """The rule in one line, the way the table shows it."""
        conditions = " ".join(f"{name}={readable(value)}" for name, value in sorted(self.conditions.items()))
        return f"{self.panel} ({conditions})" if conditions else f"{self.panel} (always)"

    @property
    def specificity(self) -> int:
        """How many conditions it states: the resolver's first precedence key."""
        return len(self.conditions)

    @property
    def name(self) -> str:
        return self.rule_id or f"{self.panel}@{self.specificity}"


def _copyable(value: Any) -> Any:
    """A condition value the editor can hold and mutate on its own."""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def readable(value: Any) -> str:
    """A condition value as a user reads it, for a table cell or a tooltip."""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


# --------------------------------------------------------------------------- #
# Conflicts.
# --------------------------------------------------------------------------- #


class RuleIssue(NamedTuple):
    """One problem with the rule set, attached to the row it is about.

    ``row`` (not ``index``) because a ``NamedTuple`` field may not shadow the
    tuple method of that name, and a table row is what it is in any case.
    """

    row: int
    severity: str  # "error" | "duplicate" | "warning"
    message: str


def rule_issues(rules: Sequence[hs.PanelRule], panels: Iterable[str] = ()) -> tuple[RuleIssue, ...]:
    """Every problem the loader and the resolver know about, per rule index.

    The warnings come from :func:`hud_situation.rule_warnings`, which is the same
    check ``tools/hud_panels.py --validate`` reports, so the tab cannot disagree
    with the command line about what is wrong with a rule set.
    """
    resolver = hs.HudSituationResolver(rules)
    by_rule = {id(rule): index for index, rule in enumerate(rules)}
    issues: list[RuleIssue] = []
    for warning in hs.rule_warnings(resolver, panels):
        issues.append(RuleIssue(by_rule.get(id(warning.rule), -1), warning.severity, warning.message))
    issues.extend(duplicate_issues(rules))
    return tuple(issues)


def duplicate_issues(rules: Sequence[hs.PanelRule]) -> tuple[RuleIssue, ...]:
    """Every rule whose selector another rule already claimed.

    Ordered by index, and reported on *both* rules of the pair: which one "wins"
    depends on file order, and a user reordering the list is exactly the person
    who has to see both halves.
    """
    issues: list[RuleIssue] = []
    seen: dict[tuple[Any, ...], int] = {}
    for index, rule in enumerate(rules):
        selector = rule.selector()
        first = seen.get(selector)
        if first is None:
            seen[selector] = index
            continue
        issues.append(RuleIssue(index, "duplicate", f"rule {_rule_label(rule)} has the same selector as rule #{first + 1}"))
        issues.append(
            RuleIssue(first, "duplicate", f"rule {_rule_label(rule)} has the same selector as rule #{first + 1}")
        )
    return tuple(issues)


def _rule_label(rule: hs.PanelRule) -> str:
    return rule.rule_id or rule.panel


def issues_by_index(rules: Sequence[hs.PanelRule], panels: Iterable[str] = ()) -> dict[int, tuple[RuleIssue, ...]]:
    """The issues of :func:`rule_issues`, grouped for a table row."""
    grouped: dict[int, list[RuleIssue]] = {}
    for issue in rule_issues(rules, panels):
        grouped.setdefault(issue.row, []).append(issue)
    return {index: tuple(entries) for index, entries in grouped.items()}


# --------------------------------------------------------------------------- #
# The preview.
# --------------------------------------------------------------------------- #


class RuleOutcome(NamedTuple):
    """What happened to one rule in one context, and in one sentence why."""

    rule: hs.PanelRule
    panel: str
    matched: bool
    shown: bool
    suppressed: bool
    reason: str


class Preview(NamedTuple):
    """The production resolver's answer, plus the explanation of it."""

    context: hs.HudSituationContext
    selection: hs.PanelSelection
    outcomes: tuple[RuleOutcome, ...]
    winner: hs.PanelRule | None
    profile: str
    enabled: bool
    notes: tuple[str, ...]

    def describe(self) -> str:
        """The preview as the text a label shows."""
        lines = [f"profile: {self.profile}" + ("" if self.enabled else "  (dynamic panels disabled)")]
        lines.append("context: " + self.context.describe())
        lines.append(self.selection.describe())
        if self.notes:
            lines.extend(self.notes)
        return "\n".join(lines)


def preview(
    conditions: Mapping[str, Any],
    rules: Sequence[hs.PanelRule],
    *,
    profile: str | None = None,
    fallback: str = "",
    samples: Mapping[str, Any] | None = None,
    panels: Iterable[str] = (),
    enabled: bool = True,
) -> Preview:
    """Resolve ``conditions`` with the production resolver, and explain it.

    ``conditions`` is a mapping in the engine's filter vocabulary -- what the
    editor's selectors write. The panels, the withheld ones and the fallback are
    the resolver's own answer; the per-rule reasons are derived from the same
    two keys the resolver sorts by, so a rule the preview calls the loser is a
    rule that lost.
    """
    context = hs.HudSituationContext.from_filters(conditions)
    resolver = hs.HudSituationResolver(rules, fallback=fallback, enabled=enabled)
    selection = resolver.resolve(context, profile, samples=samples)
    ordered = resolver.matching_rules(context, profile)
    winner = ordered[0] if ordered else None
    shown = set(selection.panels)
    notes: list[str] = []
    outcomes: list[RuleOutcome] = []
    for rule in resolver.rules:
        outcomes.append(_outcome(rule, ordered, winner, context, selection, samples, shown, profile, enabled))
    if not resolver.rules:
        notes.append("no rules at all: the static HUD is drawn, the preview shows nothing")
    elif not enabled:
        notes.append("dynamic panels are off, so no rule is consulted at all")
    elif not ordered and not fallback:
        notes.append("no rule matches and no fallback is set: every panel stays hidden")
    if selection.suppressed:
        notes.append("withheld for sample: " + ", ".join(selection.suppressed))
    unknown = _unknown_panels(selection, panels)
    if unknown:
        notes.append("no block carries: " + ", ".join(unknown))
    return Preview(
        context=context,
        selection=selection,
        outcomes=tuple(outcomes),
        winner=winner,
        profile=_text(profile, "all"),
        enabled=bool(selection.enabled),
        notes=tuple(notes),
    )


def _outcome(
    rule: hs.PanelRule,
    ordered: Sequence[hs.PanelRule],
    winner: hs.PanelRule | None,
    context: hs.HudSituationContext,
    selection: hs.PanelSelection,
    samples: Mapping[str, Any] | None,
    shown: set[str],
    profile: str | None,
    enabled: bool,
) -> RuleOutcome:
    panel = rule.panel_for(context)
    # The reasons are ordered from the rule's own reasons outwards: whether the
    # rule is off, whether this profile is its profile, whether the feature is
    # on at all. Anything else reports the wrong cause first.
    if not rule.enabled:
        return RuleOutcome(rule, panel, False, False, False, "disabled")
    if _profile_excluded(rule, profile):
        return RuleOutcome(rule, panel, False, False, False, f"scoped to profile {rule.profile!r}")
    if not enabled:
        return RuleOutcome(rule, panel, False, False, False, "dynamic panels are disabled")
    if not selection.enabled:
        return RuleOutcome(rule, panel, False, False, False, "this HUD profile has no panel rules")
    failure = _first_failure(rule, context)
    if failure is not None:
        return RuleOutcome(rule, panel, False, False, False, failure)
    if rule.suppressed(context, samples):
        value = rule.sample_value(context, samples)
        sample = "no sample" if value is None else f"{rule.sample}={value}"
        return RuleOutcome(rule, panel, True, False, True, f"withheld: {sample} < min_sample {rule.min_sample}")
    if panel not in shown:
        return RuleOutcome(rule, panel, True, False, False, _lost_reason(rule, ordered, context))
    if winner is not None and rule is winner:
        return RuleOutcome(rule, panel, True, True, False, f"won on specificity ({rule.specificity} conditions)")
    return RuleOutcome(rule, panel, True, True, False, f"also shown ({_lost_reason(rule, ordered, context)})")


def _profile_excluded(rule: hs.PanelRule, profile: str | None) -> bool:
    """Whether the rule's profile scope keeps it out of ``profile``."""
    if profile is None:
        return False
    return not hs.profile_matches(rule.profile, _text(profile, "all"))


def _first_failure(rule: hs.PanelRule, context: hs.HudSituationContext) -> str | None:
    """The first condition that did not hold, said the way a user reads it."""
    values = context.filters()
    for name, expected in rule.when.items():
        if hs.condition_matches(name, expected, context):
            continue
        actual = values.get(name, "nothing")
        return f"condition {name}={readable(expected)} does not hold (context has {readable(actual)})"
    return None


def _lost_reason(rule: hs.PanelRule, ordered: Sequence[hs.PanelRule], context: hs.HudSituationContext) -> str:
    """Why a matching rule did not put its panel on screen.

    The three keys in the resolver's order, named: whoever is above it beat it on
    one of them. ``ordered`` is the resolver's own ordering, so this cannot
    invent a precedence of its own.
    """
    for better in ordered:
        if better is rule:
            continue
        if better.panel_for(context) == rule.panel_for(context):
            continue
        if (better.specificity, better.priority) > (rule.specificity, rule.priority):
            if better.specificity != rule.specificity:
                return f"outranked by {_rule_label(better)} ({better.specificity} conditions vs {rule.specificity})"
            if better.priority != rule.priority:
                return f"outranked by {_rule_label(better)} (priority {better.priority} vs {rule.priority})"
            break
    # Its panel is not shown but nothing outranks it on the first two keys: the
    # rule that named the same panel with better order did.
    same_panel = next((other for other in ordered if other.panel_for(context) == rule.panel_for(context) and other is not rule), None)
    if same_panel is not None:
        return f"a second rule names {rule.panel_for(context)!r}: {_rule_label(same_panel)} wins on order"
    return f"panel {rule.panel_for(context)!r} is replaced by a later rule with the same name"


def _unknown_panels(selection: hs.PanelSelection, panels: Iterable[str]) -> tuple[str, ...]:
    """Panels the selection shows that no block in the configuration carries."""
    known = {_text(panel) for panel in panels}
    if not known or not selection.enabled:
        return ()
    return tuple(
        panel
        for panel in selection.panels
        if not any(hs.panel_matches_block(panel, {"id": name}) or _text(name) == _text(panel) for name in known)
    )


# --------------------------------------------------------------------------- #
# Import and export.
# --------------------------------------------------------------------------- #


class ImportedDocument(NamedTuple):
    """What a document held, and what of it could not be placed."""

    rules: tuple[hs.PanelRule, ...]
    fallback: str
    stats: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    document: dict[str, Any]


def export_document(
    rules: Iterable[hs.PanelRule],
    *,
    fallback: str = "",
    stats: Iterable[Mapping[str, Any]] = (),
    description: str = "",
) -> dict[str, Any]:
    """A rule set as one portable document, validated before it leaves.

    The rule list is the same shape ``hud_situation.parse_rules`` reads, so an
    exported file is a rule file with a header rather than a second format. The
    ``stats`` half carries the analytics-backed choices a profile binds, which is
    what makes a shared setup a setup and not just a panel layout.
    """
    document: dict[str, Any] = {
        "kind": PANEL_DOCUMENT_KIND,
        "schema_version": hs.PANEL_SCHEMA_VERSION,
        "fallback": fallback,
        "rules": [rule.as_dict() for rule in rules],
    }
    if description:
        document["description"] = description
    entries = [dict(entry) for entry in stats]
    if entries:
        document["stats"] = entries
    # Round-trip through the loader: a document that cannot be read back is not
    # exportable, and finding that out at export time is what makes the format
    # trustworthy at import time.
    parse_document(document)
    return document


def parse_document(document: Any) -> tuple[list[hs.PanelRule], str, list[dict[str, Any]]]:
    """Read a panel document, refusing what cannot be honoured.

    A bare rule file (``{"schema_version": 1, "rules": [...]}``) is accepted, so
    the export of ``tools/hud_panels.py`` and the editor's own export are the
    same input. A document naming another ``kind`` is refused: importing a popup
    pack as panels would otherwise fail later, somewhere less explainable.
    """
    if not isinstance(document, Mapping):
        raise ValueError("A panel document must be a JSON object")
    kind = document.get("kind")
    if kind is not None and kind != PANEL_DOCUMENT_KIND:
        raise ValueError(f"Not a panel document: kind is {kind!r}, expected {PANEL_DOCUMENT_KIND!r}")
    rules, fallback = hs.parse_rules(document, "the document")
    stats: list[dict[str, Any]] = []
    for entry in document.get("stats", []) or []:
        if not isinstance(entry, Mapping) or not str(entry.get("name", "")).strip():
            raise ValueError("Every stat entry in a panel document needs a 'name'")
        stats.append({str(key): value for key, value in entry.items()})
    return rules, fallback, stats


def import_document(document: Any, *, known_stats: Iterable[str] = ()) -> ImportedDocument:
    """Read a document and report the parts this build cannot place.

    Unknown stats and a newer stat format are **warnings, not failures**: a user
    importing a file from a later build keeps their rules, and is told which
    stat bindings this build does not know rather than losing them silently.
    """
    rules, fallback, stats = parse_document(document)
    warning_list: list[str] = []
    warnings_seen: list[str] = []
    if isinstance(document, Mapping):
        version = document.get("schema_version", hs.PANEL_SCHEMA_VERSION)
        if isinstance(version, int) and version < hs.PANEL_SCHEMA_VERSION:
            warning_list.append(f"document schema {version} is older than {hs.PANEL_SCHEMA_VERSION}; read as current")
    known = {str(name) for name in known_stats}
    for entry in stats:
        name = str(entry["name"])
        if known and name not in known:
            warnings_seen.append(f"stat {name!r} is not known to this build")
    return ImportedDocument(
        rules=tuple(rules),
        fallback=fallback,
        stats=tuple(stats),
        warnings=tuple(warning_list + warnings_seen),
        document=dict(document) if isinstance(document, Mapping) else {},
    )


def save_document(document: Mapping[str, Any], path: str | Path) -> Path:
    """Write a panel document, after checking it can be read back."""
    parse_document(document)
    target = Path(path)
    target.write_text(json.dumps(dict(document), indent=2, default=str) + "\n", encoding="utf-8")
    return target


def load_document(path: str | Path) -> dict[str, Any]:
    """Read a panel document from disk, validated."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    parse_document(document)
    return dict(document)


# --------------------------------------------------------------------------- #
# The stat picker.
# --------------------------------------------------------------------------- #


class StatChoice(NamedTuple):
    """One stat a user can put in a block, with what it will do to the HUD.

    The fields are the ones the issue asks the picker to show: the name, the
    filters it applies, the display format, the sample threshold, and where a
    popup already binds it.
    """

    name: str
    source: str  # "registry" | "analytics"
    label: str
    fmt: str
    sample: str
    filters: Mapping[str, Any]
    min_sample: int
    category: str
    popup_packs: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()

    def describe(self) -> str:
        """The choice in one line, the way the picker's list shows it."""
        parts = [f"{self.label} [{self.source}]"]
        if self.filters:
            parts.append("filters: " + " ".join(f"{name}={readable(value)}" for name, value in sorted(self.filters.items())))
        if self.fmt:
            parts.append(f"fmt: {self.fmt}")
        if self.min_sample:
            parts.append(f"min sample: {self.min_sample}")
        if self.sample:
            parts.append(f"sample: {self.sample}")
        if self.popup_packs:
            parts.append("popups: " + ", ".join(self.popup_packs))
        if self.blocks:
            parts.append("blocks: " + ", ".join(self.blocks))
        return " | ".join(parts)


def choice_key(choice: StatChoice) -> str:
    """A stat choice's identity: a registry stat and a declarative one can share
    a name, and the two mean different things -- one is a column of the cache,
    the other a query over the analytics rows."""
    return f"{choice.source}:{choice.name}"


def registry_choices(registry: Any = None) -> tuple[StatChoice, ...]:
    """The column-backed stats the HUD already draws, from the StatRegistry."""
    from fpdb_3_legacy.stat_registry import get_registry  # noqa: PLC0415 - keeps this module import-light

    registry = registry if registry is not None else get_registry()
    choices = []
    for descriptor in registry.all():
        choices.append(
            StatChoice(
                name=descriptor.name,
                source="registry",
                label=descriptor.label or descriptor.name,
                fmt=descriptor.fmt,
                sample=descriptor.sample,
                filters={},
                min_sample=0,
                category=descriptor.category,
            )
        )
    return tuple(choices)


def analytics_choices(registry: Any = None) -> tuple[StatChoice, ...]:
    """The declarative stats of #306, with the query each one applies."""
    from fpdb_3_legacy import analytics_definitions  # noqa: PLC0415

    registry = registry if registry is not None else analytics_definitions.get_registry()
    choices = []
    for definition in registry.all():
        display = definition.display
        choices.append(
            StatChoice(
                name=definition.name,
                source="analytics",
                label=_label(display.label) or definition.name,
                fmt=display.fmt,
                sample="opportunities",
                filters=_definition_filters(definition, registry),
                min_sample=display.min_sample,
                category=display.category,
            )
        )
    return tuple(choices)


def _definition_filters(definition: Any, registry: Any) -> dict[str, Any]:
    """The filters a definition really applies, fragments included.

    A definition's own ``filters`` is half the story: the other half is inherited
    from its fragments, and that is the half a user cannot see. Showing only the
    own half would let a picker describe a stat as "all flops" when it is only
    the ones with a c-bet in front.
    """
    from fpdb_3_legacy import analytics_definitions  # noqa: PLC0415

    merged: dict[str, Any] = {}
    try:
        merged.update(analytics_definitions.expand_fragments(definition.fragments, registry.fragments))
    except (AttributeError, KeyError, TypeError, ValueError):
        # The fragments are a description, not the value: a registry that cannot
        # expand them still gets a picker, just with the explicit half shown.
        pass
    merged.update(definition.filters)
    return merged


def _label(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("en") or next(iter(value.values()), ""))
    return str(value or "")


def stat_choices(
    *,
    config: Any = None,
    packs: Any = None,
    registry: Any = None,
    analytics: Any = None,
) -> tuple[StatChoice, ...]:
    """Every stat a block can hold: the column-backed ones, then the analytics.

    ``packs`` is the popup-pack registry of #299 and ``config`` the loaded
    configuration; together they answer "where does a popup already bind this",
    which is the question a user asks before adding a second copy of it.
    """
    choices = list(registry_choices(registry)) + list(analytics_choices(analytics))
    bound = _popup_bindings(packs) if packs is not None else {}
    blocks = _block_bindings(config) if config is not None else {}
    return tuple(
        choice._replace(popup_packs=bound.get(choice.name, ()), blocks=blocks.get(choice.name, ()))
        for choice in choices
    )


def _popup_bindings(packs: Any) -> dict[str, tuple[str, ...]]:
    """Which packs bind each stat, from the pack registry."""
    bound: dict[str, list[str]] = {}
    try:
        nodes = packs.all_nodes()
    except (AttributeError, TypeError):
        return {}
    for node in nodes:
        for entry in node.entries:
            name = str(entry.stat)
            if name and node.name not in bound.setdefault(name, []):
                bound[name].append(node.name)
    return {name: tuple(names) for name, names in bound.items()}


def _block_bindings(config: Any) -> dict[str, tuple[str, ...]]:
    """Which block of the loaded configuration already holds each stat.

    Read off the DOM rather than the parsed stat sets: the ``<stat>`` nodes are
    what round-trips, and a block a user has not saved yet is not worth
    reporting as a binding.
    """
    document = getattr(config, "doc", None)
    if document is None:
        return {}
    bound: dict[str, list[str]] = {}
    for node in document.getElementsByTagName("stat"):
        name = str(node.getAttribute("_stat_name") or node.getAttribute("name") or "").strip()
        if not name:
            continue
        block = _enclosing_block(node)
        label = ""
        if block is not None:
            label = str(block.getAttribute("label") or block.getAttribute("id") or "").strip()
        if label and label not in bound.setdefault(name, []):
            bound[name].append(label)
    return {name: tuple(labels) for name, labels in bound.items()}


def _enclosing_block(node: Any) -> Any:
    parent = node.parentNode
    while parent is not None:
        if getattr(parent, "localName", None) == "block":
            return parent
        parent = parent.parentNode
    return None


def stat_entry_attributes(choice: StatChoice, *, grid: tuple[int, int] | None = None) -> dict[str, Any]:
    """What to write into a ``<stat>`` node for one choice.

    The three extra attributes are the whole point of the picker: a stat that
    comes from a declarative definition says so, says which definition, and
    carries its own format and sample threshold, so the configuration is
    self-describing instead of depending on what the code knew that day. The HUD
    ignores attributes it does not know, and the round-trip keeps them, which is
    what the issue asks for.
    """
    attributes: dict[str, Any] = {"name": choice.name}
    if grid is not None:
        # The grid position stays a number: it is a cell, and the editor's model
        # compares it against the block's rows and columns.
        attributes["row"], attributes["col"] = int(grid[0]), int(grid[1])
    if choice.source == "analytics":
        attributes["data_source"] = "analytics"
        attributes["data_definition"] = choice.name
        if choice.fmt:
            attributes["data_format"] = choice.fmt
        if choice.min_sample:
            attributes["data_min_sample"] = str(choice.min_sample)
    return attributes
