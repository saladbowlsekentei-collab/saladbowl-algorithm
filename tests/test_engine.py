import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import unittest

from dressing import InputError, evaluate, load_policy, parse_payload


def event(event_id="p1", *, kind="information", source="community",
          at="2026-10-23T12:00:00+09:00", category="cards", content_id=None, member_id="member-a", target=None):
    result = dict(id=event_id, member_id=member_id, at=at, kind=kind,
                  source=source, content_id=content_id or event_id, category=category)
    if target is not None:
        result["target"] = target
    return result


def payload(events=(), *, gear=2, demoted_at=None, as_of="2026-10-23T20:00:00+09:00"):
    member = {"id": "member-a", "gear": gear}
    if demoted_at is not None:
        member["demoted_at"] = demoted_at
    return {"as_of": as_of, "members": [member], "events": list(events)}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def evaluate(self, raw):
        return evaluate(parse_payload(raw), self.policy)

    def row(self, raw):
        return self.evaluate(raw)["ranking"][0]

    def test_information_has_positive_score(self):
        row = self.row(payload([event()]))
        self.assertEqual(row["score"], 13.5)
        self.assertEqual(row["signals"]["valid_shares"], 1)
        self.assertTrue(row["gear"]["gear2_retention_satisfied"])

    def test_analysis_outweighs_plain_information(self):
        analysis = self.row(payload([event(kind="analysis")]))
        plain = self.row(payload([event()]))
        self.assertEqual(analysis["score"], 75)
        self.assertGreater(analysis["score"], plain["score"])

    def test_other_merchandise_adds_bonus_to_analysis(self):
        row = self.row(payload([event(kind="analysis", category="other")]))
        self.assertEqual(row["score"], 102)
        self.assertEqual(row["breakdown"]["non_card_bonus"], 27)

    def test_diary_counts_as_shared_contribution(self):
        row = self.row(payload([event(kind="diary", category="none")]))
        self.assertEqual(row["score"], 39)
        self.assertTrue(row["gear"]["gear2_retention_satisfied"])

    def test_joshin_is_not_information_even_with_high_weight_kind(self):
        raw = payload([event(source="joshin", kind="analysis", category="other")])
        result = self.evaluate(raw)
        self.assertEqual(result["ranking"][0]["score"], 0)
        self.assertFalse(result["ranking"][0]["gear"]["gear2_retention_satisfied"])
        self.assertEqual(result["filter_counts"]["excluded_source"], 1)

    def lottery_events(self, count):
        return [event(f"p{i}", kind="lottery", source="livepocket") for i in range(count)]

    def test_livepocket_threshold_is_ten(self):
        nine = self.row(payload(self.lottery_events(9)))
        ten = self.row(payload(self.lottery_events(10)))
        self.assertFalse(nine["signals"]["livepocket_milestone"])
        self.assertTrue(ten["signals"]["livepocket_milestone"])
        self.assertEqual(ten["score"], 210)
        self.assertEqual(ten["score"] - nine["score"], 88.5)

    def test_livepocket_bonus_is_not_repeated_every_ten(self):
        row = self.row(payload(self.lottery_events(20)))
        self.assertEqual(row["breakdown"]["livepocket_bonus"], 75)
        self.assertEqual(row["score"], 345)

    def test_ten_copies_of_one_link_do_not_reach_milestone(self):
        posts = [event(f"p{i}", source="livepocket", kind="lottery", content_id="same-page") for i in range(10)]
        result = self.evaluate(payload(posts))
        self.assertEqual(result["ranking"][0]["signals"]["livepocket_posts"], 1)
        self.assertFalse(result["ranking"][0]["signals"]["livepocket_milestone"])
        self.assertEqual(result["filter_counts"]["duplicate_content"], 9)

    def test_old_lottery_does_not_complete_threshold(self):
        posts = self.lottery_events(10)
        posts[0]["at"] = "2026-10-09T23:59:59+09:00"
        self.assertFalse(self.row(payload(posts))["signals"]["livepocket_milestone"])

    def test_fourteen_day_window_includes_start_midnight(self):
        posts = [
            event("before", at="2026-10-09T23:59:59+09:00"),
            event("boundary", at="2026-10-10T00:00:00+09:00"),
            event("now", at="2026-10-23T20:00:00+09:00"),
            event("future", at="2026-10-23T20:00:01+09:00"),
        ]
        result = self.evaluate(payload(posts))
        self.assertEqual(result["ranking"][0]["signals"]["valid_shares"], 2)
        self.assertEqual(result["filter_counts"]["outside_window"], 2)
        self.assertEqual(result["window_start"], "2026-10-10T00:00:00+09:00")

    def test_utc_timestamp_uses_japanese_date(self):
        row = self.row(payload([event(at="2026-10-09T15:00:00Z")]))
        self.assertEqual(row["signals"]["valid_shares"], 1)

    def test_calendar_window_across_month_and_year(self):
        for as_of, expected in [
            ("2026-11-01T12:00:00+09:00", "2026-10-19T00:00:00+09:00"),
            ("2027-01-01T12:00:00+09:00", "2026-12-19T00:00:00+09:00"),
            ("2028-03-01T12:00:00+09:00", "2028-02-17T00:00:00+09:00"),
        ]:
            with self.subTest(as_of=as_of):
                self.assertEqual(self.evaluate(payload(as_of=as_of))["window_start"], expected)

    def social(self, kind="honoa_action", **kwargs):
        return event(kind=kind, source="x", category="none", target="honoa", **kwargs)

    def test_quote_is_exactly_twice_regular_action(self):
        action = self.row(payload([self.social()]))
        quote = self.row(payload([self.social("honoa_quote")]))
        self.assertEqual(action["score"], 1)
        self.assertEqual(quote["score"], action["score"] * 2)

    def test_same_post_quote_replaces_action(self):
        posts = [self.social(event_id="action", content_id="post"),
                 self.social("honoa_quote", event_id="quote", content_id="post")]
        row = self.row(payload(posts))
        self.assertEqual(row["score"], 2)
        self.assertEqual(row["breakdown"]["honoa_action"], 0)

    def test_social_actions_do_not_keep_gear_two(self):
        row = self.row(payload([self.social("honoa_quote")]))
        self.assertFalse(row["gear"]["gear2_retention_satisfied"])
        self.assertEqual(row["signals"]["valid_shares"], 0)

    def test_other_social_target_is_not_scored(self):
        post = self.social()
        post["target"] = "someone-else"
        self.assertEqual(self.row(payload([post]))["score"], 0)

    def recovery_posts(self, days):
        return [event(f"day-{day}", at=f"2026-10-{day:02}T12:00:00+09:00") for day in days]

    def recovery(self, posts, demoted="2026-10-18T00:00:00+09:00"):
        return self.row(payload(posts, gear=1, demoted_at=demoted))

    def test_five_consecutive_days_after_demotion_qualify(self):
        row = self.recovery(self.recovery_posts(range(19, 24)))
        self.assertEqual(row["signals"]["recovery_streak_days"], 5)
        self.assertTrue(row["gear"]["gear2_recovery_candidate"])
        self.assertIsNone(row["gear"]["gear2_retention_satisfied"])

    def test_four_days_do_not_qualify(self):
        self.assertFalse(self.recovery(self.recovery_posts(range(20, 24)))["gear"]["gear2_recovery_candidate"])

    def test_gap_breaks_recovery_streak(self):
        row = self.recovery(self.recovery_posts([18, 19, 21, 22, 23]))
        self.assertEqual(row["signals"]["recovery_streak_days"], 3)
        self.assertFalse(row["gear"]["gear2_recovery_candidate"])

    def test_five_posts_on_one_day_are_not_five_days(self):
        row = self.recovery([event(f"post-{i}") for i in range(5)])
        self.assertEqual(row["signals"]["recovery_streak_days"], 1)
        self.assertFalse(row["gear"]["gear2_recovery_candidate"])

    def test_posts_before_demotion_do_not_count(self):
        row = self.recovery(self.recovery_posts(range(19, 24)), demoted="2026-10-19T13:00:00+09:00")
        self.assertEqual(row["signals"]["recovery_streak_days"], 4)
        self.assertFalse(row["gear"]["gear2_recovery_candidate"])

    def test_yesterdays_completed_streak_still_qualifies(self):
        self.assertTrue(self.recovery(self.recovery_posts(range(18, 23)))["gear"]["gear2_recovery_candidate"])

    def test_old_completed_streak_is_not_current(self):
        row = self.recovery(self.recovery_posts(range(17, 22)), demoted="2026-10-16T00:00:00+09:00")
        self.assertEqual(row["signals"]["recovery_streak_days"], 0)
        self.assertFalse(row["gear"]["gear2_recovery_candidate"])

    def test_joshin_cannot_bridge_recovery_gap(self):
        posts = self.recovery_posts(range(19, 24))
        posts[2]["source"] = "joshin"
        self.assertEqual(self.recovery(posts)["signals"]["recovery_streak_days"], 2)

    def test_no_demotion_timestamp_means_no_recovery(self):
        row = self.row(payload(self.recovery_posts(range(19, 24)), gear=1))
        self.assertFalse(row["gear"]["gear2_recovery_candidate"])

    def test_single_share_on_oldest_day_keeps_gear_two(self):
        row = self.row(payload([event(at="2026-10-10T00:00:00+09:00")]))
        self.assertTrue(row["gear"]["gear2_retention_satisfied"])

    def test_share_before_oldest_day_does_not_keep_gear_two(self):
        row = self.row(payload([event(at="2026-10-09T23:59:59+09:00")]))
        self.assertFalse(row["gear"]["gear2_retention_satisfied"])

    def test_other_gears_have_no_retention_decision(self):
        for gear in (1, 3, 4):
            with self.subTest(gear=gear):
                row = self.row(payload([event()], gear=gear))
                self.assertIsNone(row["gear"]["gear2_retention_satisfied"])
                self.assertFalse(row["gear"]["gear2_recovery_candidate"])
                self.assertEqual(row["gear"]["current"], gear)

    def test_replayed_event_is_idempotent(self):
        raw = payload([event()])
        self.assertEqual(self.evaluate(raw), self.evaluate(payload([event(), event()])))

    def test_input_order_does_not_change_results(self):
        posts = self.lottery_events(10) + [self.social("honoa_quote", event_id="q"), event("a", kind="analysis")]
        expected = self.evaluate(payload(posts))
        rng = random.Random(7)
        for _ in range(15):
            rng.shuffle(posts)
            self.assertEqual(self.evaluate(payload(posts)), expected)

    def test_deduplication_does_not_cross_members(self):
        raw = payload([event(content_id="same"), event("p2", member_id="member-b", content_id="same")])
        raw["members"].append({"id": "member-b", "gear": 2})
        result = self.evaluate(raw)
        self.assertEqual([row["score"] for row in result["ranking"]], [13.5, 13.5])
        self.assertEqual([row["member_id"] for row in result["ranking"]], ["member-a", "member-b"])

    def test_input_is_not_mutated(self):
        raw = payload([event()])
        original = copy.deepcopy(raw)
        self.evaluate(raw)
        self.assertEqual(raw, original)

    def test_empty_members_and_events(self):
        raw = {"as_of": "2026-10-23T20:00:00+09:00", "members": [], "events": []}
        result = self.evaluate(raw)
        self.assertEqual(result["ranking"], [])
        self.assertEqual(result["features"]["guest_access"], "planned")

    def test_published_example_matches_expected_output(self):
        root = Path(__file__).resolve().parent.parent
        raw = json.loads((root / "examples/sample.json").read_text(encoding="utf-8"))
        expected = json.loads((root / "examples/expected.json").read_text(encoding="utf-8"))
        self.assertEqual(self.evaluate(raw), expected)


class InputTests(unittest.TestCase):
    def assert_invalid(self, raw):
        with self.assertRaises(InputError):
            parse_payload(raw)

    def test_unknown_members_are_rejected(self):
        self.assert_invalid(payload([event(member_id="unknown")]))

    def test_duplicate_member_ids_are_rejected(self):
        raw = payload()
        raw["members"] *= 2
        self.assert_invalid(raw)

    def test_conflicting_duplicate_event_id_is_rejected(self):
        self.assert_invalid(payload([event(), event(kind="analysis")]))

    def test_invalid_gears_are_rejected(self):
        for gear in (True, False, 0, 5, "2", 2.0, None, []):
            with self.subTest(gear=gear):
                self.assert_invalid(payload(gear=gear))

    def test_invalid_dates_are_rejected(self):
        for at in ("2026-10-23T12:00:00", "2026-10-23", "2026-02-30T00:00:00Z", None, "garbage"):
            with self.subTest(at=at):
                self.assert_invalid(payload([event(at=at)]))

    def test_unknown_event_kinds_sources_and_categories_are_rejected(self):
        for key, value in (("kind", []), ("kind", "unknown"), ("source", {}), ("source", "unknown"), ("category", "unknown")):
            with self.subTest(key=key, value=value):
                post = event()
                post[key] = value
                self.assert_invalid(payload([post]))

    def test_unknown_fields_are_rejected(self):
        raw = payload([event()])
        raw["events"][0]["extra"] = "unexpected"
        self.assert_invalid(raw)

    def test_social_event_requires_target(self):
        self.assert_invalid(payload([event(kind="honoa_quote", source="x", category="none")]))

    def test_source_and_kind_must_match(self):
        for post in (event(source="livepocket"), event(source="x"), event(kind="honoa_action", target="honoa", category="none")):
            self.assert_invalid(payload([post]))

    def test_demotion_cannot_be_in_future_or_on_other_gear(self):
        self.assert_invalid(payload(gear=1, demoted_at="2026-10-24T00:00:00+09:00"))
        self.assert_invalid(payload(gear=2, demoted_at="2026-10-20T00:00:00+09:00"))

    def test_diary_cannot_claim_merchandise_bonus(self):
        self.assert_invalid(payload([event(kind="diary", category="other")]))

    def test_input_count_limit_is_enforced(self):
        self.assert_invalid(payload([event()] * 10001))


if __name__ == "__main__":
    unittest.main()

