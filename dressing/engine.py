"""Harvest -> Strainer -> Dressing -> Bowl. All calculations are local."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from .policy import Policy
from .schema import Event, Payload, SHARE_KINDS


def window_start(as_of, days):
    """Include today and the preceding days - 1 dates in JST."""
    return as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)


def strain(payload: Payload, policy: Policy):
    """Deduplicate content per member; quotes supersede ordinary actions."""
    accepted = {}
    counters = {"outside_window": 0, "excluded_source": 0, "other_target": 0, "duplicate_content": 0}
    start = window_start(payload.as_of, policy.contribution_days)
    for event in sorted(payload.events, key=lambda item: (item.at, item.id)):
        if not start <= event.at <= payload.as_of:
            counters["outside_window"] += 1
            continue
        if event.source in policy.excluded_sources:
            counters["excluded_source"] += 1
            continue
        if event.source == "x" and event.target != "honoa":
            counters["other_target"] += 1
            continue
        key = (event.member_id, event.source, event.content_id)
        previous = accepted.get(key)
        if previous is not None:
            counters["duplicate_content"] += 1
            if event.kind == "honoa_quote" and previous.kind == "honoa_action":
                accepted[key] = event
            continue
        accepted[key] = event
    return tuple(accepted.values()), counters


def streak_days(events: list[Event], member, as_of) -> int:
    if member.demoted_at is None:
        return 0
    days = {event.at.date() for event in events if event.at >= member.demoted_at}
    today = as_of.date()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def evaluate(payload: Payload, policy: Policy) -> dict:
    selected, counters = strain(payload, policy)
    by_member = defaultdict(list)
    for event in selected:
        by_member[event.member_id].append(event)
    results = []
    for member in payload.members:
        events = by_member[member.id]
        shares = [event for event in events if event.kind in SHARE_KINDS]
        breakdown = {key: Decimal(0) for key in (
            "information", "lottery", "analysis", "diary", "non_card_bonus",
            "livepocket_bonus", "honoa_action", "honoa_quote",
        )}
        for event in events:
            if event.kind == "honoa_quote":
                breakdown[event.kind] += policy.weights["honoa_action"] * policy.weights["honoa_quote_multiplier"]
            else:
                breakdown[event.kind] += policy.weights[event.kind]
            if event.category == "other" and event.kind in SHARE_KINDS:
                breakdown["non_card_bonus"] += policy.weights["non_card_bonus"]
        livepocket_count = sum(
            event.source == "livepocket"
            and event.at >= window_start(payload.as_of, policy.livepocket_days)
            for event in shares
        )
        milestone = livepocket_count >= policy.livepocket_posts
        if milestone:
            breakdown["livepocket_bonus"] = policy.weights["livepocket_bonus"]
        streak = streak_days(shares, member, payload.as_of)
        results.append({
            "member_id": member.id,
            "score": float(sum(breakdown.values())),
            "breakdown": {key: float(value) for key, value in breakdown.items()},
            "signals": {
                "valid_shares": len(shares),
                "livepocket_posts": livepocket_count,
                "livepocket_milestone": milestone,
                "recovery_streak_days": streak,
            },
            "gear": {
                "current": member.gear,
                "gear2_recovery_candidate": member.gear == 1 and streak >= policy.recovery_days,
                "gear2_retention_satisfied": (
                    len(shares) >= policy.retention_shares if member.gear == 2 else None
                ),
                "review_required": True,
            },
        })
    results.sort(key=lambda row: (-row["score"], row["member_id"]))
    return {
        "policy_version": policy.version,
        "as_of": payload.as_of.isoformat(),
        "window_start": window_start(payload.as_of, policy.contribution_days).isoformat(),
        "timezone": "Asia/Tokyo",
        "features": {"guest_access": policy.guest_access},
        "filter_counts": counters,
        "ranking": results,
    }

