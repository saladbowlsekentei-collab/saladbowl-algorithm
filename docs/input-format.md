# 入力形式

`python -m dressing <input.json>` は、1つの JSON オブジェクトを受け取ります。
エラー時の終了コードは `2`、成功時は `0` です。

```json
{
  "as_of": "2026-10-23T20:00:00+09:00",
  "members": [{"id": "member-a", "gear": 2}],
  "events": [{
    "id": "post-1",
    "member_id": "member-a",
    "at": "2026-10-23T12:00:00+09:00",
    "kind": "analysis",
    "source": "community",
    "content_id": "article-1",
    "category": "other"
  }]
}
```

## 共通の条件

- 時刻はタイムゾーン付きの ISO 8601。`Z` と `+09:00` などのオフセットを受け付け、JST にそろえます。
- ID は英数字で始まり、英数字・`_`・`.`・`:`・`-` の96文字以内。
- 入力は最大4 MiB、メンバーは最大1,000件、イベントは最大10,000件。
- 未定義フィールド、未知のメンバー参照、重複するメンバーID、タイムゾーンのない時刻はエラー。
- JSON の重複キーと `NaN` / `Infinity` はエラー。
- 同一イベントID・同一内容の再投入は1件にまとめます。同一IDで内容が異なる場合はエラー。

## members

| フィールド | 型 | 内容 |
|---|---|---|
| `id` | string | 集計内で一意のメンバー識別子 |
| `gear` | integer | 現在のギア。1〜4 |
| `demoted_at` | string / 省略可 | ギア1に落ちた時刻。ギア1でのみ指定でき、評価時刻より未来は不可 |

`demoted_at` がないメンバーは復帰判定の対象外です。ギア2の維持判定は、現在のギアが2のメンバーにのみ返します。それ以外は `null` です。

## events

| フィールド | 型 | 内容 |
|---|---|---|
| `id` | string | イベント自体の一意な識別子 |
| `member_id` | string | `members` に登録された識別子 |
| `at` | string | 投稿日時 |
| `kind` | string | 下表の投稿種別 |
| `source` | string | `community` / `livepocket` / `joshin` / `x` |
| `content_id` | string | 元の情報・記事・抽選ページ・X投稿を表す識別子 |
| `category` | string | `cards` / `other` / `none` |
| `target` | string / 条件付き | Xアクションの対象。`honoa` を評価する |

| `kind` | 用途 | 条件 |
|---|---|---|
| `information` | 情報共有 | category は `cards` または `other` |
| `lottery` | 抽選リンク共有 | category は `cards` または `other` |
| `analysis` | 考察 | category は `cards` または `other` |
| `diary` | 日記 | category は `none` |
| `honoa_action` | ホノアへの通常アクション | source は `x`、category は `none`、target 必須 |
| `honoa_quote` | ホノアの投稿の引用 | source は `x`、category は `none`、target 必須 |

`source=livepocket` は `kind=lottery` と組み合わせます。
`source=x` はアクション・引用にのみ使用します。
`source=joshin` のイベントは評価の前に除外します。本文の単語検索による分類は行いません。

`content_id` は同じ元情報に対して同じ値を付けます。ライポケでは同じ抽選ページ、Xでは同じ投稿に対して、再共有時も同じ値を使います。
`id` だけを変えても、同一メンバー・情報源・`content_id` の再共有は増点しません。
別のメンバーによる共有は別々に評価します。

## 出力

- `policy_version`: 使用した設定の版。
- `as_of`, `window_start`, `timezone`: 評価時刻と集計期間。
- `filter_counts`: 期間外・除外情報源・対象外アクション・内容重複の除外数。完全一致のイベント再送は入力検証時に統合済み。
- `ranking`: 点数の降順。同点はメンバーIDの辞書順。
- `ranking[].breakdown`: 各加点の内訳。
- `ranking[].signals`: 共有件数、ライポケ件数・達成、復帰の連続日数。
- `ranking[].gear`: 現在のギア、ギア2復帰候補、ギア2維持条件の充足、確認の要否。
- `features.guest_access`: ゲスト機能の状態。

ライポケの達成ボーナスは既存のリンク点数への加算です。カード以外の加点も基本点への加算です。
計算には十進数を使用し、出力は JSON の数値です。

