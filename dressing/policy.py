"""One source of truth for weights, windows, and release metadata."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import tomllib


DEFAULT_PATH = Path(__file__).resolve().parent.parent / "settings.toml"
WEIGHT_KEYS = frozenset({
    "information", "lottery", "analysis", "diary", "non_card_bonus",
    "livepocket_bonus", "honoa_action", "honoa_quote_multiplier",
})


@dataclass(frozen=True)
class Policy:
    version: str
    contribution_days: int
    livepocket_days: int
    recovery_days: int
    livepocket_posts: int
    retention_shares: int
    weights: dict[str, Decimal]
    excluded_sources: frozenset[str]
    guest_access: str


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{name}: unexpected or missing settings")


def _positive_int(value, name):
    if type(value) is not int or not 1 <= value <= 365:
        raise ValueError(f"{name}: expected an integer between 1 and 365")
    return value


def load_policy(path=DEFAULT_PATH) -> Policy:
    with Path(path).open("rb") as stream:
        raw = tomllib.load(stream)
    _keys(raw, {"version", "windows", "thresholds", "weights", "filters", "features"}, "policy")
    version = raw["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version: expected a semantic version")
    _keys(raw["windows"], {"contribution_days", "livepocket_days", "recovery_days"}, "windows")
    windows = {key: _positive_int(value, key) for key, value in raw["windows"].items()}
    if max(windows["livepocket_days"], windows["recovery_days"]) > windows["contribution_days"]:
        raise ValueError("contribution_days must cover the other windows")
    _keys(raw["thresholds"], {"livepocket_posts", "retention_shares"}, "thresholds")
    thresholds = {key: _positive_int(value, key) for key, value in raw["thresholds"].items()}
    _keys(raw["weights"], WEIGHT_KEYS, "weights")
    weights = {}
    for key, value in raw["weights"].items():
        if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,4})?", value):
            raise ValueError(f"{key}: expected a nonnegative decimal string")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{key}: invalid weight") from exc
        if not number.is_finite() or number > 1000000:
            raise ValueError(f"{key}: invalid weight")
        weights[key] = number
    if weights["honoa_quote_multiplier"] < 1:
        raise ValueError("honoa_quote_multiplier must be at least 1")
    _keys(raw["filters"], {"excluded_sources"}, "filters")
    sources = raw["filters"]["excluded_sources"]
    if not isinstance(sources, list) or any(
        not isinstance(source, str) or source not in {"community", "livepocket", "joshin", "x"}
        for source in sources
    ):
        raise ValueError("excluded_sources: unknown source")
    _keys(raw["features"], {"guest_access"}, "features")
    if raw["features"]["guest_access"] != "planned":
        raise ValueError("guest_access: this release supports planned status only")
    return Policy(version, **windows, **thresholds, weights=weights,
                  excluded_sources=frozenset(sources), guest_access="planned")

