import json
import os
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "expected"

class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return f"D:{o}"
        return super().default(o)

def _decimal_hook(obj):
    res = {}
    for k, v in obj.items():
        if isinstance(v, str) and v.startswith("D:"):
            res[k] = Decimal(v[2:])
        elif isinstance(v, list):
            res[k] = [
                _decimal_hook(item) if isinstance(item, dict) else (
                    Decimal(item[2:]) if isinstance(item, str) and item.startswith("D:") else item
                ) for item in v
            ]
        elif isinstance(v, dict):
            res[k] = _decimal_hook(v)
        else:
            res[k] = v
    return res

TOLERANCES = {
    "rit.equity_player": Decimal("0.15"),  # EV/Monte Carlo variance allowed for RIT
    "pots.side": Decimal("0.01"),  # float division noise tolerance
}

def _tolerance(path: str) -> Decimal:
    for key, tol in TOLERANCES.items():
        if key in path:
            return tol
    return Decimal("0.00")  # Strict 0 tolerance by default

def deep_diff(x, y, path=""):
    """Pure-python recursive deep diff between structured objects with targeted tolerances."""
    diffs = []
    if type(x) is not type(y):
        return [f"{path}: type mismatch ({type(x).__name__} vs {type(y).__name__})"]
        
    if isinstance(x, dict):
        x_keys = set(x.keys())
        y_keys = set(y.keys())
        
        for k in sorted(x_keys - y_keys):
            diffs.append(f"{path}.{k}: missing in actual" if path else f"{k}: missing in actual")
        for k in sorted(y_keys - x_keys):
            diffs.append(f"{path}.{k}: extra in actual" if path else f"{k}: extra in actual")
            
        for k in sorted(x_keys & y_keys):
            diffs.extend(deep_diff(x[k], y[k], f"{path}.{k}" if path else k))
            
    elif isinstance(x, (list, tuple)):
        if "pots.side" in path:
            x_sorted = sorted(x)
            y_sorted = sorted(y)
            if len(x_sorted) != len(y_sorted):
                diffs.append(f"{path}: length mismatch ({len(x_sorted)} vs {len(y_sorted)})")
            for i in range(min(len(x_sorted), len(y_sorted))):
                diffs.extend(deep_diff(x_sorted[i], y_sorted[i], f"{path}[{i}]"))
        else:
            if len(x) != len(y):
                diffs.append(f"{path}: length mismatch ({len(x)} vs {len(y)})")
            for i in range(min(len(x), len(y))):
                diffs.extend(deep_diff(x[i], y[i], f"{path}[{i}]"))
            
    elif isinstance(x, Decimal) and isinstance(y, Decimal):
        tol = _tolerance(path)
        if abs(x - y) > tol:
            diffs.append(f"{path}: value mismatch ({x} vs {y})")
    elif isinstance(x, (float, int)) and isinstance(y, (float, int)):
        tol = float(_tolerance(path))
        if abs(x - y) > tol:
            diffs.append(f"{path}: value mismatch ({x} vs {y})")
    else:
        if x != y:
            diffs.append(f"{path}: value mismatch ({repr(x)} vs {repr(y)})")
            
    return diffs

class SnapshotIO:
    def path(self, entry_id, room):
        return ROOT / room / f"{entry_id}.expected.json"

    def load(self, entry_id, room):
        p = self.path(entry_id, room)
        if not p.exists():
            return None
        return json.loads(p.read_text(), object_hook=_decimal_hook)

    def save(self, entry_id, room, data):
        p = self.path(entry_id, room)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, sort_keys=True, cls=_DecimalEncoder))

    def load_hands(self, entry_id, room):
        data = self.load(entry_id, room)
        if data is None:
            return None
        if isinstance(data, dict) and set(data.keys()) == {"hands"}:
            return data["hands"]
        return [data]

    def is_multi_hand_snapshot(self, entry_id, room):
        data = self.load(entry_id, room)
        return isinstance(data, dict) and set(data.keys()) == {"hands"}

    def save_hands(self, entry_id, room, hands):
        if len(hands) == 1:
            self.save(entry_id, room, hands[0])
        else:
            self.save(entry_id, room, {"hands": hands})

    def diff(self, expected, actual):
        if expected is None:
            return []
        return deep_diff(expected, actual)

    def fmt(self, diff):
        return "\nSnapshot diff:\n" + "\n".join(diff) if diff else "(empty)"
