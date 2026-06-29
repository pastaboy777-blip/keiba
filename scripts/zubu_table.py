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

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.core import features as F

import predict_nankan as pn

# 前志向の脚質しきい値。senkou_power がこれ以上=前で運びたい馬。
FRONT_TH = 0.2
# 前で運びたい馬がこの数以上いると、ハイペースで前崩れ→差し有利と判定する。
PACE_FRONT_CROWD = 3
# 差し展開のとき v2 に乗せる脚質補正の強さ(差し馬=senkou負を加点・前馬を減点)。
PACE_SASHI_K = 1.5
# 持続戦しきい値: 当日前半のラスト失速(ラスト1F−区間ベスト)の平均がこれ以上なら持続戦の日。
# 持続戦=瞬発(キレ)が使えない→差し判定でも後方一気は割引し好位寄せに補正(鉄則8)。
SUSTAIN_FADE = 0.8
# 持続戦の好位寄せ強度=差し繰り上げ係数に掛ける割引率(小さいほど後方を消し好位を残す)。
# 距離で可変(鉄則8精緻化・船橋6/28で学習): 短距離はコーナーがきつく後方は届かない→強く好位寄せ。
# 中距離は直線/コーナーに余裕があり持続戦でも後方一気が差し込む→割引を弱め後方を残す。
SUSTAIN_K_SPRINT = 0.3   # 〜1300m
SUSTAIN_K_MILE = 0.7     # 1400m〜
SUSTAIN_DIST_TH = 1400
PERF_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/"

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


def measure_sustained(client, races, through: int):
    """当日の前半(through Rまで)の完了レースのラップから持続戦かを実測する。

    ラスト失速 = ラスト1F − 残り800m以降の区間ベスト1F。平均が SUSTAIN_FADE 以上なら
    『持続戦の日』(瞬発が使えない)。戻り値 (平均ラスト失速 or None, 判定本数)。
    """
    import pace_day as PD                      # 遅延import(楽天ラップ取得)
    fades = []
    for rno in sorted(races):
        if rno > through:
            break
        try:
            html = client.get(PERF_URL + races[rno])
            laps = PD.parse_laps(html)
        except Exception:  # noqa: BLE001
            continue
        if len(laps) >= 4:
            fades.append(round(laps[-1] - min(laps[-4:]), 2))
    if not fades:
        return None, 0
    return round(sum(fades) / len(fades), 2), len(fades)


def main() -> None:
    ap = argparse.ArgumentParser(description="南関 1日分 ズブ穴 統一表(Markdown)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(ALL_CODES), required=True,
                    help="南関4場 または 地方場(笠松/名古屋/園田/高知/佐賀 等。"
                         "※地方はv2が南関学習のため転移性低=実験的)")
    ap.add_argument("--baba", choices=list(pn.BABA_FULL), default="不",
                    help="想定馬場ラベル(v2順位は不変。既定=不良)")
    ap.add_argument("--from", dest="from_r", type=int, default=1, help="開始R(既定1)")
    ap.add_argument("--to", dest="to_r", type=int, default=12, help="終了R(既定12)")
    ap.add_argument("--bias", choices=["front", "sashi", "pace"], default="front",
                    help="脚質バイアス: front=前残り(既定) / sashi=差し有利 / "
                         "pace=展開オート(前で運びたい馬が多いR→ハイペース前崩れ→差しに切替)")
    ap.add_argument("--pop-min", type=int, default=6,
                    help="ズブ穴の人気しきい値(この人気以下が対象。既定6)")
    ap.add_argument("--draw", choices=["all", "inner"], default="all",
                    help="all=枠不問 / inner=内〜中枠のみ(馬番<=頭数の約6割)。"
                         "笠松等のタイト前残り馬場で内が残る傾向に合わせる")
    ap.add_argument("--sustained", choices=["auto", "on", "off"], default="auto",
                    help="持続戦補正(鉄則8): on/auto=差し判定でも後方一気を割引し好位寄せ。"
                         "auto=当日前半ラップのラスト失速平均で自動実測(>=0.8でON)")
    ap.add_argument("--sustained-through", type=int, default=4,
                    help="持続戦のauto実測に使う前半R数(既定4)")
    ap.add_argument("--out", default=None, help="出力先Markdownパス(未指定なら標準出力)")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-02.jsonl", "data/samples/nankan_2026-03.jsonl",
        "data/samples/nankan_2026-04.jsonl", "data/samples/nankan_2026-05.jsonl",
        "data/samples/nankan_2026-06.jsonl"])
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient()
    idx = client.get(pn.CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[args.place]))
    if not races:
        raise SystemExit(f"{args.date} {args.place} のレースが見つかりません。")

    jrates = pn.jockey_top3_from_samples(args.samples)
    trainers = pn.trainer_stats_from_samples(args.samples)
    v2_stats = pn.zubu_v2_stats_from_samples(args.samples, pop_min=args.pop_min)

    # 持続戦の判定(鉄則8)。auto=当日前半ラップで実測 / on=強制 / off=無効。
    sustain_fade, sustain_n = (None, 0)
    if args.sustained == "off":
        sustained = False
    elif args.sustained == "on":
        sustained = True
    else:  # auto
        sustain_fade, sustain_n = measure_sustained(client, races, args.sustained_through)
        sustained = sustain_fade is not None and sustain_fade >= SUSTAIN_FADE

    collected = []  # (rno, dist_label, picks, bias, front_n)
    for rno in sorted(races):
        if rno < args.from_r or rno > args.to_r:
            continue
        card = P.parse_card_page(client.get(pn.CARD_URL.format(race_id=races[rno])), races[rno])
        jockeys = E.jockey_stats_from_card(card)
        # 展開判定: 前で運びたい馬(senkou>=FRONT_TH)の頭数を数える
        front_n = 0
        for e in card.entries:
            if e.umaban is None:
                continue
            if F.senkou_power(E.past_runs_to_records(e)) >= FRONT_TH:
                front_n += 1
        if args.bias == "pace":
            # 前が多い=ハイペースで前崩れ→差し。短距離は2頭でも崩れやすいので感度UP。
            # 多頭数(実力拮抗で前が競る)もハイペース要因として閾値を下げる。
            crowd = PACE_FRONT_CROWD
            if card.distance and card.distance <= 1300:
                crowd = 2                       # 短距離(1200等)=前2頭でも前崩壊
            elif card.field_size and card.field_size >= 14:
                crowd = max(2, PACE_FRONT_CROWD - 1)   # 多頭数=拮抗で前が競る
            bias = "sashi" if front_n >= crowd else "front"
        else:
            bias = args.bias
        # 持続戦補正(鉄則8): 差し判定でも持続戦の日は後方一気が届かない→好位寄せ。
        # 差し繰り上げ(PACE_SASHI_K)を弱め、好位の持続型を残す。割引率は距離で可変。
        sashi_k = PACE_SASHI_K
        if bias == "sashi" and sustained:
            short = card.distance and card.distance < SUSTAIN_DIST_TH
            sashi_k = PACE_SASHI_K * (SUSTAIN_K_SPRINT if short else SUSTAIN_K_MILE)
        # オッズ未開放の先のレースは確定タイムが無く足切りしない(その3と一致)→ target_time=None
        picks = pn.zubu_ana_picks(
            card, jockeys, target_time=None, jockey_rates=jrates,
            pop_min=args.pop_min, bias=bias, baba=args.baba,
            v2_stats=v2_stats, v2_weights=pn.ZUBU_V2_WEIGHTS)
        # 差し展開: v2ランキングに脚質補正を乗せて差し馬を繰り上げる(前崩れ前提)。
        # v2素点はそのまま表示し、並び順だけ展開で組み替える(透明性のため別管理)。
        if bias == "sashi" and picks:
            def _adj(item, _k=sashi_k):
                e, v2, _t = item
                return v2 - _k * F.senkou_power(E.past_runs_to_records(e))
            picks = sorted(picks, key=_adj, reverse=True)
        # 内〜中枠フィルタ: 馬番が頭数の約6割以内の馬だけ残す(タイト前残り馬場向け)
        if args.draw == "inner" and card.field_size:
            thr = round(card.field_size * 0.6)
            picks = [p for p in picks if p[0].umaban and p[0].umaban <= thr]
        dist_label = f"{card.surface}{card.distance}"
        collected.append((rno, dist_label, picks, bias, front_n))

    # 当日の最多軸騎手(本命の主因騎手で最頻)を太字対象にする
    from collections import Counter
    jc = Counter()
    for _rno, _d, picks, _b, _f in collected:
        if picks:
            jk = jockey_from_tags(picks[0][2])
            if jk:
                jc[jk] += 1
    top_jockey, top_jockey_n = (jc.most_common(1)[0] if jc else (None, 0))

    pace_on = args.bias == "pace"
    lines = []
    lines.append(f"## {int(ymd[4:6])}/{int(ymd[6:8])} {args.place} ズブ穴候補"
                 f"（{pn.BABA_FULL[args.baba]}想定・{args.from_r}R以降"
                 f"{'・展開オート' if pace_on else ''}"
                 f"{'・差し優先' if args.bias == 'sashi' else ''}"
                 f"{'・持続戦→好位寄せ' if sustained else ''}"
                 f"{'・内〜中枠' if args.draw == 'inner' else ''}）")
    if sustained:
        meas = (f"前半{sustain_n}R平均ラスト失速 {sustain_fade:+.2f}秒"
                if sustain_fade is not None else "手動指定")
        lines.append("")
        lines.append(f"> ★持続戦の日({meas})＝瞬発が使えない。"
                     f"差し判定でも後方一気を割引し**好位の持続型**を厚くしています(鉄則8)。")
    lines.append("")
    head_cols = "| R | 距離 | " + ("展開 | " if pace_on else "") + "本命 | v2 | 主因 | 2番手 |"
    sep = "|---|---|" + ("---|" if pace_on else "") + "---|---|---|---|"
    lines.append(head_cols)
    lines.append(sep)

    headline = []  # (rno, honmei_str, v2)
    for rno, dist, picks, bias, front_n in collected:
        if pace_on:
            if bias == "sashi":
                pace_cell = f"差し→好位(前{front_n})" if sustained else f"差し(前{front_n})"
            else:
                pace_cell = f"前残り(前{front_n})"
        else:
            pace_cell = None
        pc = f"{pace_cell} | " if pace_on else ""
        if not picks:
            lines.append(f"| {rno}R | {dist} | {pc}該当なし | — | — | — |")
            continue
        e1, v1, t1 = picks[0]
        jk1 = jockey_from_tags(t1)
        honmei = f"{circ(e1.umaban)}{e1.horse_name}"
        honmei_disp = f"**{honmei}**" if emph(jk1, top_jockey) else honmei
        v1_disp = f"**{v1:+.2f}**" if emph(jk1, top_jockey) else f"{v1:+.2f}"
        cause = shuin_summary(t1)
        cause_disp = cause.replace(top_jockey, f"**{top_jockey}**") if (
            top_jockey and emph(jk1, top_jockey)) else cause
        if len(picks) > 1:
            e2, v2, _t2 = picks[1]
            second = f"{circ(e2.umaban)}{e2.horse_name}({v2:+.2f})"
        else:
            second = "—"
        lines.append(f"| {rno}R | {dist} | {pc}{honmei_disp} | {v1_disp} "
                     f"| {cause_disp} | {second} |")
        headline.append((rno, honmei, v1))

    # ★高評価: v2上位の本命と、最多軸騎手の本数
    headline.sort(key=lambda x: -x[2])
    lines.append("")
    lines.append(f"### ★ 高評価（{top_jockey or '—'}の軸が濃い）" if top_jockey
                 else "### ★ 高評価")
    if len(headline) >= 2:
        a, b = headline[0], headline[1]
        lines.append(f"- **{a[0]}R {a[1]}（{a[2]:+.2f}）／ {b[0]}R {b[1]}（{b[2]:+.2f}）** "
                     f"← 本日の頭抜け")
    tier = [h for h in headline[2:] if h[2] >= 2.4]
    if tier:
        lines.append("- " + " ／ ".join(f"{r}R {n}（{v:+.2f}）" for r, n, v in tier))
    if top_jockey and top_jockey_n >= 2:
        axis_rs = [f"{rno}R" for rno, _d, picks, _b, _f in collected
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
