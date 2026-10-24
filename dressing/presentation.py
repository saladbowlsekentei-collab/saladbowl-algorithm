"""Render the published policy table from the same configuration as the engine."""

from .policy import Policy


def number(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def policy_table(policy: Policy) -> str:
    w = policy.weights
    rows = [
        ("通常の情報共有", f"+{number(w['information'])} / 件"),
        ("抽選リンク", f"+{number(w['lottery'])} / 件"),
        ("Joshin", "情報評価の対象外。共有件数・連続投稿日にも含めない" if "joshin" in policy.excluded_sources else "情報評価の対象"),
        ("ライポケ", f"直近{policy.livepocket_days}日で{policy.livepocket_posts}件以上 → +{number(w['livepocket_bonus'])}。期間内に1回加算"),
        ("考察系の投稿", f"+{number(w['analysis'])} / 件"),
        ("カード以外の商材", f"情報・抽選リンク・考察の点数に +{number(w['non_card_bonus'])} / 件"),
        ("日記", f"+{number(w['diary'])} / 件"),
        ("ホノアへのアクション", f"+{number(w['honoa_action'])} / 投稿"),
        ("ホノアの引用ツイート", f"通常アクションの{number(w['honoa_quote_multiplier'])}倍（+{number(w['honoa_action'] * w['honoa_quote_multiplier'])} / 投稿）"),
        ("ギア1 → ギア2の復帰", f"ギア1に落ちた後、{policy.recovery_days}日連続で有効な共有 → 復帰候補"),
        ("ギア2の維持", f"直近{policy.contribution_days}日間に{policy.retention_shares}回以上の有効な共有"),
        ("ゲスト制度", "準備中。採点・ギア判定への接続は今後の拡張"),
    ]
    return "\n".join(["| 入力・条件 | 評価 |", "|---|---|", *[f"| {label} | {value} |" for label, value in rows]])

