"""Turn real hand-history files into fixtures that name nobody (#735).

A parser fixture has to stay in the room's own format, byte for byte, or it no
longer tests the parser: only the names may change. The names are not guessed
with patterns of our own -- the room's fpdb converter reads each file and says
who sat at the table and who the hero was, so every room fpdb parses is covered
the day it is. A few things a converter never reports are added per room:
names in tournament summaries, and account tokens such as Unibet's
``name[Unibet_<hex>]``.

The names are the seats the converter reads, so a player who sits out a whole
hand is renamed too. The hero becomes ``Hero`` and the others ``alice``,
``bob``, ... in the order they first appear, consistently across every file of
one run (and of later runs given the same mapping file). A file the converter
cannot read completely is refused: a dropped hand's names would survive
unnoticed. Before anything is written the result is parsed again: it must give
the same hands, with exactly the renamed players, and no real name or token may
survive anywhere in it or in its file name. Otherwise nothing is written.

The real-to-fake mapping is written to ``--map``, which must lie outside the
repository: it is the one file that undoes the anonymisation.

    python tools/anonymize_hh.py --room Unibet --map ~/hh-maps/unibet.json \\
        --out tests/fixtures/hands/unibet  path/to/export.txt  path/to/folder
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy.Configuration import Config  # noqa: E402  # pylint: disable=wrong-import-position
from fpdb_3_legacy.Hand import Hand  # noqa: E402  # pylint: disable=wrong-import-position
from fpdb_3_legacy.parser_registry import get_parser_class  # noqa: E402  # pylint: disable=wrong-import-position

HERO = "Hero"
FAKE_NAMES = (
    "alice",
    "bob",
    "carol",
    "dave",
    "erin",
    "frank",
    "grace",
    "heidi",
    "ivan",
    "judy",
    "mallory",
    "niaj",
    "olivia",
    "peggy",
    "rupert",
    "sybil",
    "trent",
    "victor",
    "walter",
)
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class RoomExtras:
    """What a room's converter does not report but a file may still carry."""

    # Lines naming players outside the hands: tournament summaries.
    summary_names: tuple[re.Pattern[str], ...] = ()
    # Player names in room events the converter does not add to the seating.
    event_names: tuple[re.Pattern[str], ...] = ()
    # An account token: a match's "TOKEN" group is replaced wherever it occurs.
    token: re.Pattern[str] | None = None
    # What a fake token's "TOKEN" group becomes, given its number (1, 2, ...).
    fake_token: str = "{:016x}"


ROOMS: dict[str, RoomExtras] = {
    "Unibet": RoomExtras(
        summary_names=(
            re.compile(r"^[0-9]+:\s(?P<NAME>.+?)\sfinished\b", re.MULTILINE),
            re.compile(r"^-:\s(?P<NAME>.+?)\sstill_playing\b", re.MULTILINE),
            re.compile(r"^(?P<NAME>\S+?)\sfinished\sthe\stournament\b", re.MULTILINE),
        ),
        token=re.compile(r"Unibet_(?P<TOKEN>[0-9a-fA-F]{8,})"),
    ),
    "Winamax": RoomExtras(summary_names=(re.compile(r"^Player\s:\s(?P<NAME>.+?)\s*$", re.MULTILINE),)),
    "PokerStars": RoomExtras(
        event_names=(re.compile(r"^(?P<NAME>.+?) joins the table at seat #\d+\s*$", re.MULTILINE),),
    ),
}


@dataclass
class Mapping:
    """Real names and tokens to fake ones, shared by every file of a run."""

    names: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Mapping:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(names=dict(data.get("names", {})), tokens=dict(data.get("tokens", {})))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"names": self.names, "tokens": self.tokens}, indent=2) + "\n", encoding="utf-8")

    def add_name(self, real: str, *, hero: bool = False) -> None:
        if not real.strip():
            return
        if real in self.names and self.names[real] != real:
            return
        if hero:
            self.names[real] = HERO
            return
        # A fake name is never one a real player goes by.
        taken = set(self.names.values()) | set(self.names) | {real}
        fake = next((name for name in FAKE_NAMES if name not in taken), None)
        n = 0
        while fake is None or fake in taken:
            n += 1
            fake = f"player{n}"
        self.names[real] = fake

    def add_token(self, real: str, template: str) -> None:
        if real not in self.tokens:
            self.tokens[real] = template.format(len(self.tokens) + 1)


def _decode(raw: bytes) -> tuple[bytes, str, str]:
    """Split a file into its BOM, its text and the codec that reads it back."""
    if raw.startswith(BOM):
        return BOM, raw[len(BOM) :].decode("utf-8"), "utf-8"
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b"", raw.decode("utf-16"), "utf-16"
    for codec in ("utf-8", "cp1252"):
        try:
            return b"", raw.decode(codec), codec
        except UnicodeDecodeError:
            continue
    raise ValueError("unreadable file")


def _name_pattern(name: str, *, filename: bool = False) -> re.Pattern[str]:
    # Screen names carry letters, digits, "-" and "_": a name must not match
    # inside a longer one ("Jo" in "Jo128"). In a file name, though, "_" and
    # "-" are separators: "hands_Jo.txt" must not keep "Jo".
    boundary = r"[0-9A-Za-z]" if filename else r"[\w-]"
    return re.compile(rf"(?<!{boundary}){re.escape(name)}(?!{boundary})")


def _temp_config(directory: Path) -> Config:
    """A throwaway configuration: never the user's own HUD_config.xml."""
    shutil.copy(REPO / "HUD_config.xml.example", directory / "HUD_config.xml")
    config = Config(file=str(directory / "HUD_config.xml"))
    config.dir_database = str(directory)
    return config


@dataclass
class Parsed:
    """What a converter made of one file."""

    hands: list
    # Every name the converter seated, in order. A cash player who sits out
    # the whole hand is seated, then removed from ``hand.players``: their name
    # is in the file all the same.
    seated: list[str]
    # Hands the converter could not read (errors and partial hands): their
    # players may appear nowhere else.
    failed: int

    def players(self) -> list[tuple[str, bool]]:
        """Each seated player once, in order, with whether they are the hero."""
        seen = dict.fromkeys(self.seated, False)
        for hand in self.hands:
            if hand.hero:
                seen[hand.hero] = True
        return list(seen.items())


def _parse(converter, config: Config, path: Path) -> Parsed:
    seated: list[str] = []
    add_player = Hand.addPlayer

    def record(hand, seat, name, *args, **kwargs):
        seated.append(name)
        return add_player(hand, seat, name, *args, **kwargs)

    Hand.addPlayer = record  # type: ignore[assignment]
    try:
        parser = converter(config=config, in_path=str(path), autostart=True)
    finally:
        Hand.addPlayer = add_player  # type: ignore[assignment]
    failed = int(getattr(parser, "numErrors", 0) or 0) + int(getattr(parser, "numPartial", 0) or 0)
    return Parsed(parser.getProcessedHands(), list(dict.fromkeys(seated)), failed)


@dataclass
class Result:
    source: Path
    target: Path
    hands: int


class Anonymizer:
    def __init__(self, room: str, mapping: Mapping, workdir: Path) -> None:
        self.room = room
        self.extras = ROOMS.get(room, RoomExtras())
        self.converter = get_parser_class(room)
        self.mapping = mapping
        self.config = _temp_config(workdir)
        self.workdir = workdir

    def _summary_name_matches(self, text: str) -> list:
        return [match for pattern in self.extras.summary_names for match in pattern.finditer(text)]

    def _event_name_matches(self, text: str) -> list:
        return [match for pattern in self.extras.event_names for match in pattern.finditer(text)]

    def _rename_player_keys(self, players: dict) -> dict:
        """Rename player keys while leaving card data untouched."""
        return {self.mapping.names.get(name, name): cards for name, cards in players.items()}

    def collect(self, path: Path, hero: str | None) -> Parsed:
        """Learn the names and tokens of one file; returns what the converter made of it."""
        parsed = _parse(self.converter, self.config, path)
        _, text, _ = _decode(path.read_bytes())
        summaries = self._summary_name_matches(text)
        event_names = self._event_name_matches(text)
        # A summary the converter's own isSummary() misses (Winamax writes
        # "Tournament summary", not " Tournament Summary ") registers as a
        # failed hand; recognise it by its summary lines before rejecting.
        is_summary = bool(summaries) and not parsed.hands
        if parsed.failed and not is_summary:
            # A hand the converter drops is a hand whose names it never reads.
            msg = f"{path.name}: {parsed.failed} hand(s) could not be read; remove them or fix the converter first"
            raise ValueError(msg)
        players = parsed.players()
        if hero:
            players = [(name, name == hero or is_hero) for name, is_hero in players]
        for name, is_hero in players:
            self.mapping.add_name(name, hero=is_hero)
        for match in summaries:
            name = match.group("NAME")
            stripped = name
            if self.extras.token is not None:
                stripped = re.sub(rf"\[{self.extras.token.pattern}\]$", "", name)
            # A room whose tokens mark the hero marks them in summaries too.
            self.mapping.add_name(stripped, hero=stripped == hero or stripped != name)
        for match in event_names:
            name = match.group("NAME")
            self.mapping.add_name(name, hero=name == hero)
        if not parsed.hands and not summaries:
            msg = f"{path.name}: neither a hand nor a tournament summary this room's tools recognise"
            raise ValueError(msg)
        if self.extras.token is not None:
            for match in self.extras.token.finditer(text):
                self.mapping.add_token(match.group("TOKEN"), self.extras.fake_token)
        return parsed

    def rewrite(self, text: str, *, filename: bool = False) -> str:
        # One pass each, longest first: replacing names one after another would
        # rename again a name another one had just become.
        if self.mapping.tokens:
            tokens = "|".join(re.escape(real) for real in sorted(self.mapping.tokens, key=len, reverse=True))
            text = re.sub(tokens, lambda match: self.mapping.tokens[match.group(0)], text)
        if self.mapping.names:
            names = "|".join(re.escape(real) for real in sorted(self.mapping.names, key=len, reverse=True))
            boundary = r"[0-9A-Za-z]" if filename else r"[\w-]"
            text = re.sub(rf"(?<!{boundary})(?:{names})(?!{boundary})", lambda match: self.mapping.names[match.group(0)], text)
        return text

    def leftovers(self, text: str, *, filename: bool = False) -> list[str]:
        fakes = set(self.mapping.names.values())
        found = [
            real for real in self.mapping.names if real not in fakes and _name_pattern(real, filename=filename).search(text)
        ]
        fake_tokens = set(self.mapping.tokens.values())
        found += [real for real in self.mapping.tokens if real not in fake_tokens and real in text]
        return found

    def anonymize(self, source: Path, target: Path, parsed: Parsed) -> Result:
        bom, text, codec = _decode(source.read_bytes())
        rewritten = self.rewrite(text)
        left = self.leftovers(rewritten)
        if left:
            msg = f"{source.name}: {len(left)} real name(s) or token(s) would survive"
            raise ValueError(msg)
        staged = self.workdir / target.name
        staged.write_bytes(bom + rewritten.encode(codec))
        again = _parse(self.converter, self.config, staged)
        is_summary = bool(self._summary_name_matches(rewritten)) and not again.hands
        expected = [{self.mapping.names.get(player[1], player[1]) for player in hand.players} for hand in parsed.hands]
        expected_gametypes = [hand.gametype for hand in parsed.hands]
        expected_boards = [hand.board for hand in parsed.hands]
        expected_holecards = [
            {street: self._rename_player_keys(players) for street, players in hand.holecards.items()}
            for hand in parsed.hands
        ]
        expected_discards = [
            {street: self._rename_player_keys(players) for street, players in hand.discards.items()}
            for hand in parsed.hands
        ]
        expected_winning_hands = [self._rename_player_keys(hand.winningHand) for hand in parsed.hands]
        expected_actions = [
            {
                street: [
                    (self.mapping.names.get(action[0], action[0]), *action[1:])
                    if isinstance(action, tuple) and action
                    else action
                    for action in actions
                ]
                for street, actions in hand.actions.items()
            }
            for hand in parsed.hands
        ]
        no_failed_hands = not again.failed or is_summary
        same_players = [{player[1] for player in hand.players} for hand in again.hands] == expected
        same_seated_players = again.seated == [self.mapping.names.get(name, name) for name in parsed.seated]
        same_gametypes = [hand.gametype for hand in again.hands] == expected_gametypes
        same_actions = [hand.actions for hand in again.hands] == expected_actions
        same_boards = [hand.board for hand in again.hands] == expected_boards
        same_holecards = [hand.holecards for hand in again.hands] == expected_holecards
        same_discards = [hand.discards for hand in again.hands] == expected_discards
        same_winning_hands = [hand.winningHand for hand in again.hands] == expected_winning_hands
        if not all(
            (
                no_failed_hands,
                same_players,
                same_seated_players,
                same_gametypes,
                same_actions,
                same_boards,
                same_holecards,
                same_discards,
                same_winning_hands,
            )
        ):
            msg = f"{source.name}: the anonymised file no longer parses into the same hands, players, game types, actions and cards"
            raise ValueError(msg)
        return Result(source, target, len(again.hands))


def _inputs(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in (".txt", ".xml"))
        elif path.is_file():
            files.append(path)
        else:
            msg = f"no such file or folder: {path}"
            raise SystemExit(msg)
    return files


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO)
    except ValueError:
        return False
    return True


def run(room: str, inputs: list[Path], out: Path, map_path: Path, hero: str | None = None) -> list[Result]:
    """Anonymise ``inputs`` into ``out``; writes nothing unless every file passes."""
    if _inside_repo(map_path):
        msg = f"the mapping undoes the anonymisation: keep it outside the repository, not at {map_path}"
        raise SystemExit(msg)
    files = _inputs(inputs)
    mapping = Mapping.load(map_path)
    with tempfile.TemporaryDirectory() as tmp:
        anonymizer = Anonymizer(room, mapping, Path(tmp))
        parsed = {path: anonymizer.collect(path, hero) for path in files}
        results = []
        for path in files:
            name = anonymizer.rewrite(path.name, filename=True)
            left = anonymizer.leftovers(name, filename=True)
            if left:
                msg = f"{path.name}: {len(left)} real name(s) or token(s) would survive in the output file name"
                raise ValueError(msg)
            results.append(anonymizer.anonymize(path, out / name, parsed[path]))
        if len({result.target for result in results}) != len(results):
            raise SystemExit("two inputs would be written to the same file name")
        out.mkdir(parents=True, exist_ok=True)
        for result in results:
            shutil.copyfile(Path(tmp) / result.target.name, result.target)
    mapping.save(map_path)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", type=Path, help="hand-history files or folders (.txt, .xml)")
    parser.add_argument("--room", required=True, help="the fpdb converter's name, e.g. Unibet, Winamax, PokerStars")
    parser.add_argument("--out", required=True, type=Path, help="folder the anonymised files are written to")
    parser.add_argument("--map", required=True, type=Path, help="real-to-fake mapping (JSON), outside the repository")
    parser.add_argument("--hero", help="the hero's real name, when the files do not say")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        results = run(args.room, args.inputs, args.out, args.map.expanduser(), args.hero)
    except ValueError as error:
        print(f"Nothing written: {error}", file=sys.stderr)
        return 1
    for result in results:
        print(f"{result.hands:>5} hands  {result.source.name} -> {result.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
