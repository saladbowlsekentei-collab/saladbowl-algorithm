"""Validate classified events before they enter the ranking pipeline."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re


JST = timezone(timedelta(hours=9), name="JST")
SHARE_KINDS = frozenset({"information", "lottery", "analysis", "diary"})
SOCIAL_KINDS = frozenset({"honoa_action", "honoa_quote"})
SOURCES = frozenset({"community", "livepocket", "joshin", "x"})
MAX_EVENTS = 10000
MAX_MEMBERS = 1000


class InputError(ValueError):
    """Invalid payload; the CLI returns a short error without echoing input."""


@dataclass(frozen=True)
class Member:
    id: str
    gear: int
    demoted_at: datetime | None = None


@dataclass(frozen=True)
class Event:
    id: str
    member_id: str
    at: datetime
    kind: str
    source: str
    content_id: str
    category: str
    target: str | None = None


@dataclass(frozen=True)
class Payload:
    as_of: datetime
    members: tuple[Member, ...]
    events: tuple[Event, ...]


def _object(value, required, optional, label):
    if not isinstance(value, dict):
        raise InputError(f"{label}: expected an object")
    if not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise InputError(f"{label}: unexpected or missing fields")


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", value):
        raise InputError(f"{label}: expected a short identifier")
    return value


def parse_time(value, label):
    if not isinstance(value, str) or len(value) > 40 or "T" not in value:
        raise InputError(f"{label}: expected an ISO 8601 timestamp with timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError("timezone required")
        result = result.astimezone(JST)
        if not 2000 <= result.year <= 9998:
            raise ValueError("unsupported year")
        return result
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{label}: expected an ISO 8601 timestamp with timezone") from exc


def parse_payload(raw) -> Payload:
    _object(raw, {"as_of", "members", "events"}, set(), "payload")
    as_of = parse_time(raw["as_of"], "as_of")
    if not isinstance(raw["members"], list) or len(raw["members"]) > MAX_MEMBERS:
        raise InputError("members: expected a list of at most 1000 members")
    members = []
    member_ids = set()
    for row in raw["members"]:
        _object(row, {"id", "gear"}, {"demoted_at"}, "member")
        member_id = _identifier(row["id"], "member.id")
        if member_id in member_ids:
            raise InputError("members: duplicate member ID")
        if type(row["gear"]) is not int or row["gear"] not in {1, 2, 3, 4}:
            raise InputError("member.gear: expected an integer from 1 to 4")
        demoted_at = None
        if "demoted_at" in row:
            demoted_at = parse_time(row["demoted_at"], "member.demoted_at")
            if demoted_at > as_of or row["gear"] != 1:
                raise InputError("member.demoted_at: requires gear 1 and a past timestamp")
        members.append(Member(member_id, row["gear"], demoted_at))
        member_ids.add(member_id)
    if not isinstance(raw["events"], list) or len(raw["events"]) > MAX_EVENTS:
        raise InputError("events: expected a list of at most 10000 events")
    events = []
    seen = {}
    for row in raw["events"]:
        _object(row, {"id", "member_id", "at", "kind", "source", "content_id", "category"}, {"target"}, "event")
        event_id = _identifier(row["id"], "event.id")
        member_id = _identifier(row["member_id"], "event.member_id")
        if member_id not in member_ids:
            raise InputError("event.member_id: unknown member")
        if not isinstance(row["kind"], str) or row["kind"] not in SHARE_KINDS | SOCIAL_KINDS:
            raise InputError("event.kind: unknown kind")
        if not isinstance(row["source"], str) or row["source"] not in SOURCES:
            raise InputError("event.source: unknown source")
        kind, source, category = row["kind"], row["source"], row["category"]
        if not isinstance(category, str) or category not in {"cards", "other", "none"}:
            raise InputError("event.category: unknown category")
        social = kind in SOCIAL_KINDS
        if social != (source == "x"):
            raise InputError("event: social events must use source x exclusively")
        if source == "livepocket" and kind != "lottery":
            raise InputError("event: livepocket requires kind lottery")
        target = row.get("target")
        if social:
            _identifier(target, "event.target")
            if category != "none":
                raise InputError("event: social events require category none")
        elif "target" in row:
            raise InputError("event.target: only supported on social events")
        if kind == "diary" and category != "none":
            raise InputError("event: diary requires category none")
        if kind in {"information", "lottery", "analysis"} and category == "none":
            raise InputError("event: information events require cards or other")
        event = Event(event_id, member_id, parse_time(row["at"], "event.at"), kind, source,
                      _identifier(row["content_id"], "event.content_id"), category, target)
        if event_id in seen:
            if event != seen[event_id]:
                raise InputError("events: conflicting duplicate event ID")
            continue
        seen[event_id] = event
        events.append(event)
    return Payload(as_of, tuple(members), tuple(events))

