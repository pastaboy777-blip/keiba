"""1日分の南関ズブ穴候補を『R別 本命＋2番手』の統一表(Markdown)で出力する。

predict_nankan.py の v2ズブ穴ロジック(騎手質+地力+先行)をそのまま使い、
指定した範囲の各レースについて 本命(v2 1位)・2番手(2位) と主因を1枚の表にまとめる。
出力は「南関競馬予想 その3」で確定した標準フォーマットに統一している。

v2ランキングは想定馬場で順位が変わらない設計のため、--baba は表示用ラベルにだけ効く。
オッズ未開放(想定人気が未掲載)の先のレースでも出せる。確定レースが無い時は
タイム足切りを行わない(=その3の出力と一致)。

実行例:
    python3 scripts/zubu_table.py --date 2026-06-26 --place 浦和 --baba 不 --from 5
    python3 scripts/zubu_table.py --date 2026-06-26 --place 浦和 --from 5 --out notes/2026-06-26_urawa.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))           # scripts/ (predict_nankan)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E

import predict_nankan as pn

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# 主因の表示順(上から優先して最大2つ採用)。タグ中のキーワード→表示ラベル。
REASON_PRIORITY = [
    ("乗替", "乗替"),
    ("間隔あけ", "間隔明け"),
    ("前で運べる", "前で運べる"),
    ("純持続型", "純持続"),
    ("連闘", "連闘"),
    ("中1-2週", "詰め"),
    ("距離短縮", "距離短縮"),
    ("上がり遅い", "上がり遅"),
    ("上がりやや遅", "上がり遅"),
    ("場替わり", "場替わり"),
]


def circ(n) -> str:
    return CIRCLED[n - 1] if isinstance(n, int) and 1 <= n <= len(CIRCLED) else str(n)


def jockey_from_tags(tags) -> str | None:
    """『上位騎手(笹川翼・3着内53%)』タグから騎手名を取り出す。"""
    for t in tags:
        if t.startswith("上位騎手("):
            return t[len("上位騎手("):].split("・")[0]
    return None


def shuin_summary(tags, *, max_reasons: int = 2) -> str:
    """主因を『騎手・理由1・理由2』に要約する(その3の主因列の体裁)。"""
    jk = jockey_from_tags(tags)
    joined = "・".join(tags)
    reasons: list[str] = []
    for key, label in REASON_PRIORITY:
        if key in joined and label not in reasons:
            reasons.append(label)
        if len(reasons) >= max_reasons:
            break
    parts = ([jk] if jk else []) + reasons
    return "・".join(parts) if parts else "—"


def emph(jockey: str | None, top_jockey: str | None) -> bool:
    """本命の主因騎手が当日の最多軸騎手なら太字にする(その3の強調)。"""
    return bool(jockey and top_jockey and jockey == top_jockey)


def main() -> None:
    ap = argparse.ArgumentParser(description="南関 1日分 ズブ穴 統一表(Markdown)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--baba", choices=list(pn.BABA_FULL), default="不",
                    help="想定馬場ラベル(v2順位は不変。既定=不良)")
    ap.add_argument("--from", dest="from_r", type=int, default=1, help="開始R(既定1)")
    ap.add_argument("--to", dest="to_r", type=int, default=12, help="終了R(既定12)")
    ap.add_argument("--pop-min", type=int, default=6,
                    help="ズブ穴の人気しきい値(この人気以下が対象。既定6)")
    ap.add_argument("--out", default=None, help="出力先Markdownパス(未指定なら標準出力)")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-02.jsonl", "data/samples/nankan_2026-03.jsonl",
        "data/samples/nankan_2026-04.jsonl", "data/samples/nankan_2026-05.jsonl",
        "data/samples/nankan_2026-06.jsonl"])
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient()
    idx = client.get(pn.CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))
    if not races:
        raise SystemExit(f"{args.date} {args.place} のレースが見つかりません。")

    jrates = pn.jockey_top3_from_samples(args.samples)
    trainers = pn.trainer_stats_from_samples(args.samples)
    v2_stats = pn.zubu_v2_stats_from_samples(args.samples, pop_min=args.pop_min)

    collected = []  # (rno, dist_label, picks)
    for rno in sorted(races):
        if rno < args.from_r or rno > args.to_r:
            continue
        card = P.parse_card_page(client.get(pn.CARD_URL.format(race_id=races[rno])), races[rno])
        jockeys = E.jockey_stats_from_card(card)
        # オッズ未開放の先のレースは確定タイムが無く足切りしない(その3と一致)→ target_time=None
        picks = pn.zubu_ana_picks(
            card, jockeys, target_time=None, jockey_rates=jrates,
            pop_min=args.pop_min, bias="front", baba=args.baba,
            v2_stats=v2_stats, v2_weights=pn.ZUBU_V2_WEIGHTS)
        dist_label = f"{card.surface}{card.distance}"
        collected.append((rno, dist_label, picks))

    # 当日の最多軸騎手(本命の主因騎手で最頻)を太字対象にする
    from collections import Counter
    jc = Counter()
    for _rno, _d, picks in collected:
        if picks:
            jk = jockey_from_tags(picks[0][2])
            if jk:
                jc[jk] += 1
    top_jockey, top_jockey_n = (jc.most_common(1)[0] if jc else (None, 0))

    lines = []
    lines.append(f"## {int(ymd[4:6])}/{int(ymd[6:8])} {args.place} ズブ穴候補"
                 f"（{pn.BABA_FULL[args.baba]}想定・{args.from_r}R以降）")
    lines.append("")
    lines.append("| R | 距離 | 本命 | v2 | 主因 | 2番手 |")
    lines.append("|---|---|---|---|---|---|")

    headline = []  # (rno, honmei_str, v2)
    for rno, dist, picks in collected:
        if not picks:
            lines.append(f"| {rno}R | {dist} | 該当なし | — | — | — |")
            continue
        e1, v1, t1 = picks[0]
        jk1 = jockey_from_tags(t1)
        honmei = f"{circ(e1.umaban)}{e1.horse_name}"
        honmei_disp = f"**{honmei}**" if emph(jk1, top_jockey) else honmei
        v1_disp = f"**+{v1:.2f}**" if emph(jk1, top_jockey) else f"+{v1:.2f}"
        cause = shuin_summary(t1)
        cause_disp = cause.replace(top_jockey, f"**{top_jockey}**") if (
            top_jockey and emph(jk1, top_jockey)) else cause
        if len(picks) > 1:
            e2, v2, _t2 = picks[1]
            second = f"{circ(e2.umaban)}{e2.horse_name}(+{v2:.2f})"
        else:
            second = "—"
        lines.append(f"| {rno}R | {dist} | {honmei_disp} | {v1_disp} | {cause_disp} | {second} |")
        headline.append((rno, honmei, v1))

    # ★高評価: v2上位の本命と、最多軸騎手の本数
    headline.sort(key=lambda x: -x[2])
    lines.append("")
    lines.append(f"### ★ 高評価（{top_jockey or '—'}の軸が濃い）" if top_jockey
                 else "### ★ 高評価")
    if len(headline) >= 2:
        a, b = headline[0], headline[1]
        lines.append(f"- **{a[0]}R {a[1]}（+{a[2]:.2f}）／ {b[0]}R {b[1]}（+{b[2]:.2f}）** "
                     f"← 本日の頭抜け")
    tier = [h for h in headline[2:] if h[2] >= 2.4]
    if tier:
        lines.append("- " + " ／ ".join(f"{r}R {n}（+{v:.2f}）" for r, n, v in tier))
    if top_jockey and top_jockey_n >= 2:
        axis_rs = [f"{rno}R" for rno, _d, picks in collected
                   if picks and jockey_from_tags(picks[0][2]) == top_jockey]
        lines.append(f"- {top_jockey}の軸が{top_jockey_n}本（{'・'.join(axis_rs)}）"
                     f"＝陣営本気サイン濃厚")

    out = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"書き出し: {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
