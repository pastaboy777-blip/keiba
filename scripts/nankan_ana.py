#!/usr/bin/env python3
"""その日の**穴馬がなぜ好走したか**を1頭ずつ分解する。

    python3 scripts/nankan_ana.py --date 20260807 --place 浦和
    python3 scripts/nankan_ana.py --date 20260807 --place 浦和 --pop 5 --all

穴馬＝「人気薄（既定6人気以下）で3着内」。理由の候補を**並べるだけ**で、
どれが効いたかの重みづけはしない。1日ぶんのデータで重みは決められない。

出す材料:
  展開    … 4角の位置とレースの決着傾向。前が垂れる流れを前で残ったのか、
            差しが決まる流れを差したのか。**噛み合ったのか、逆らったのか。**
  上がり  … 上がり順位。3着内で上がり最速なら「脚を使った」、
            上がり下位なら「位置で残った」。
  時計    … その馬自身の同場・同距離の過去と比べる（自己比）。
  刺激    … 他場帰り／乗替／距離短縮・延長／間隔／馬体重の増減／若さ。

⚠️⚠️ **この出力から「この日は特別だった」と言ってはいけない。**（§32）
   穴馬を集めて共通点を数えれば、必ず何かの数が多くなる。**穴馬は着順で
   選んだ集団**なので、そこから逆算した特徴は同義反復になりやすい。
   一般則として使うなら、対照日を2〜3日置いて同じ数え方をすること。
   このスクリプトはそれを**やらない**。1日を説明するための道具。

⚠️ 「なぜ来たか」は走った後の話。**そのまま次のレースの買い材料にはならない。**
   位置取り・展開の噛み合いは、次走で同じ流れになる保証がない。

⚠️ ラップ（`furlongs`）が取れるかは場による。浦和・大井は取れることが多く、
   船橋は取れないことがある。取れない日は前半＝走破タイム−上がり3F で近似する。

⚠️ 1500m/1900m など200で割り切れない距離のテン3Fは信用しない（§thickness）。
"""

from __future__ import annotations

import argparse
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import lap as lapmod                  # noqa: E402
from nankeiba.core import shock, track_bias              # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402

#: 何人気以下を「穴」とみなすか。
ANA_POP = 6
#: 何着以内を「好走」とみなすか。
HIT = 3


def corner4(corners: str | None) -> dict[int, int]:
    """結果ページの通過順文字列から **4角の馬番→順位** を作る。

        '４角 6,5,(2,8)-(7,3),(9,1),4' → {6:1, 5:2, 2:3, 8:3, 7:5, ...}

    括弧は横並び（同順）。同順は同じ数字を振り、次はその頭数ぶん飛ばす。
    """
    if not corners:
        return {}
    m = re.search(r"４角(.*?)(?:■|$)", corners)
    if not m:
        return {}
    pos: dict[int, int] = {}
    rank = 1
    for a, b in re.findall(r"\(([^)]*)\)|(\d+)", m.group(1)):
        nums = [int(x) for x in re.findall(r"\d+", a or b)]
        for u in nums:
            pos[u] = rank
        rank += len(nums)
    return pos


def measured_bias(rows: list[dict]) -> str:
    """**実際の着順から**その日の前・後ろの有利不利を測る。

    ⚠️ `lap.analyze` の `bias` は `テン3F − 上がり3F` を 0 と比べているだけで、
       **小回り＝直線が短い場では上がりが遅くなるのが構造**なので、常に
       マイナス＝常に「差し有利」と出る。2026-08-07 浦和は全12レースが
       「差し・追込有利」と判定されたが、実測は **4角7番手以降が116頭中0頭**
       という極端な前有利だった。**判定ラベルではなく、この実測を見ること。**
    """
    if not rows:
        return "測れない（通過順なし）"
    front = [x for x in rows if x["p"] <= 2]
    back = [x for x in rows if x["p"] >= 7]
    if not front or not back:
        return "測れない（母数不足）"
    fh = sum(1 for x in front if x["f"] <= 3) / len(front)
    bh = sum(1 for x in back if x["f"] <= 3) / len(back)
    d = fh - bh
    if d >= 0.40:
        return f"**前が圧倒的に有利**（4角1〜2番手 {fh:.0%} 対 7番手以降 {bh:.0%}）"
    if d >= 0.15:
        return f"やや前有利（{fh:.0%} 対 {bh:.0%}）"
    if d <= -0.15:
        return f"差し有利（4角1〜2番手 {fh:.0%} 対 7番手以降 {bh:.0%}）"
    return f"位置による差は小さい（{fh:.0%} 対 {bh:.0%}）"


def leg(pos: list | None, field: int) -> str:
    """4角の位置から脚質をひとことで。通過順が無ければ '?'。"""
    if not pos:
        return "?"
    p = pos[-1]
    if p <= 2:
        return "逃げ・先行"
    if p <= max(3, field * 0.4):
        return "好位"
    if p <= field * 0.7:
        return "中団"
    return "後方"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--place", required=True)
    ap.add_argument("--pop", type=int, default=ANA_POP, help="この人気以下を穴とする")
    ap.add_argument("--hit", type=int, default=HIT, help="この着以内を好走とする")
    ap.add_argument("--all", action="store_true", help="穴が居ないレースも出す")
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    base = cli.find_race_id(args.date, args.place, 1)[:-2]

    races = []
    for rno in range(1, 13):
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
            raw = cli.get(f"/race_performance/list/RACEID/{rid}")
            res = rk.parse_result(raw)
        except Exception:                                # noqa: BLE001
            continue
        if not res:
            continue
        races.append((rno, card, raw, res))
    if not races:
        print("結果が取れない。", file=sys.stderr)
        sys.exit(1)

    # 当日の馬場差
    rows = [dict(race_no=r, place=args.place, distance=c["header"]["distance"],
                 win_time=x[0]["time_sec"])
            for r, c, _, x in races if x[0].get("time_sec")]
    tb = track_bias.measure(rows, place=args.place)
    baba = rk.parse_baba(races[0][2])
    print(f"\n=== {args.date} {args.place}　穴馬（{args.pop}人気以下で{args.hit}着内）"
          f"がなぜ来たか ===")
    print(f"  馬場 {baba}／馬場差 {tb.offset:+.2f} s/F（{tb.label}）"
          f"／{len(races)}レース")

    # ── 先に「その日の位置取りの効き方」を実測する ────────────────
    day: list[dict] = []
    c4map: dict[int, dict[int, int]] = {}
    for rno, card, raw, res in races:
        c4map[rno] = corner4((rk.parse_lap(raw) or {}).get("corners"))
        for x in res:
            p = c4map[rno].get(x.get("umaban"))
            if p and x.get("finish") and x.get("popularity"):
                day.append(dict(r=rno, p=p, f=x["finish"], pop=x["popularity"],
                                fld=len(res), name=x["name"]))
    if day:
        print(f"\n  ◆ この日の決着（**判定ラベルではなく実測**・全{len(day)}頭）")
        print(f"    {'4角':<10}{'頭数':>5}{'3着内':>6}{'率':>7}{'勝':>4}")
        for lo, hi, nm in ((1, 2, "1〜2番手"), (3, 4, "3〜4番手"),
                           (5, 6, "5〜6番手"), (7, 99, "7番手以降")):
            s = [x for x in day if lo <= x["p"] <= hi]
            if not s:
                continue
            h = sum(1 for x in s if x["f"] <= 3)
            w = sum(1 for x in s if x["f"] == 1)
            print(f"    {nm:<10}{len(s):>5}{h:>6}{h / len(s):>7.0%}{w:>4}")
        print(f"    → {measured_bias(day)}")
        a6 = [x for x in day if x["pop"] >= args.pop]
        if a6:
            print(f"\n  ◆ {args.pop}人気以下だけ{len(a6)}頭を4角で切る"
                  f"（そもそも後ろ：4角の中央値 {st.median(x['p'] for x in a6):.1f}）")
            for lo, hi, nm in ((1, 2, "1〜2番手"), (3, 4, "3〜4番手"), (5, 99, "5番手以降")):
                s = [x for x in a6 if lo <= x["p"] <= hi]
                if not s:
                    continue
                h = sum(1 for x in s if x["f"] <= args.hit)
                print(f"    {nm:<10}{len(s):>5}頭中 {h}頭が{args.hit}着内  {h / len(s):>4.0%}")
    print()

    total = 0
    for rno, card, raw, res in races:
        hd = card["header"]
        di = hd["distance"]
        la = lapmod.analyze(res, di, rk.parse_lap(raw))
        lp = rk.parse_lap(raw) or {}
        ent = {e["name"]: e for e in card["entries"]}
        cor = c4map.get(rno, {})
        ana = [x for x in res
               if x.get("popularity") and x["popularity"] >= args.pop
               and x.get("finish") and x["finish"] <= args.hit]
        if not ana and not args.all:
            continue
        total += len(ana)
        par = shock.par_pace(args.place, di, track_bias.PAR_WIN or None)
        wt = res[0].get("time_sec")
        pd = (wt / (di / 200.0) - par) if (wt and par is not None) else None
        f = lp.get("furlongs") or []
        print(f"■ {rno}R ダ{di}m {len(res)}頭　勝ち{wt}"
              + (f"　par差 {pd:+.2f} s/F（馬場差込み {pd - tb.offset:+.2f}）" if pd is not None else "")
              + f"　{la.pace}／{la.bias}")
        if f:
            print(f"   ラップ {' - '.join(f'{x:.1f}' for x in f)}")
        if not ana:
            print("   穴なし\n")
            continue
        for x in ana:
            e = ent.get(x["name"]) or {}
            h = [r for r in (e.get("history") or [])
                 if r.date and r.date < f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"]
            pr = h[0] if h else None
            same = [r for r in h if r.place == args.place and r.distance == di and r.time_sec]
            bst = min((r.time_sec for r in same), default=None)
            ags = sorted(y["agari"] for y in res if y.get("agari"))
            ar = (ags.index(x["agari"]) + 1) if x.get("agari") in ags else None
            print(f"   ★ {x['finish']}着 {x['name']}（{x['popularity']}人気"
                  + (f"・{e.get('odds')}倍" if e.get("odds") else "") + f"）{x.get('sexage','')}")
            print(f"      時計 {x.get('time_sec')}　上がり {x.get('agari')}"
                  + (f"（{ar}/{len(ags)}位）" if ar else "")
                  + (f"　自己比 {x['time_sec'] - bst:+.1f}秒"
                     f"（{args.place}{di}m 自己ベスト{bst}）" if (bst and x.get("time_sec")) else
                     f"　{args.place}{di}m の経験なし"))
            stim = []
            if pr:
                y, m, d2 = map(int, pr.date.split("-"))
                import datetime as _dt
                gap = (_dt.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
                       - _dt.date(y, m, d2)).days
                if pr.place != args.place:
                    stim.append(f"{pr.place}帰り")
                if pr.jockey and e.get("jockey") and pr.jockey != e["jockey"]:
                    stim.append(f"乗替({pr.jockey}→{e['jockey']})")
                if pr.distance and pr.distance != di:
                    stim.append("短縮" if pr.distance > di else "延長")
                stim.append(f"中{gap}日" if gap <= 20 else
                          (f"**{gap}日ぶり**" if gap >= 60 else f"中{gap}日"))
                if e.get("age") and e["age"] <= 4:
                    stim.append(f"{e['age']}歳")
                if x.get("weight_diff"):
                    stim.append(f"馬体{x['weight_diff']:+d}kg")
                print(f"      前走 {pr.date} {pr.place}{pr.distance}m {pr.finish_pos}着"
                      f" 上{pr.last3f_sec or '-'}"
                      + (f" 通過{'-'.join(map(str, pr.corner_pos))}" if pr.corner_pos else "")
                      + f"　／ {'・'.join(stim)}")
                p_now = cor.get(x.get("umaban"))
                if pr.corner_pos and pr.field_size and p_now:
                    # 頭数が違うので前走の位置を今回の頭数に換算してから比べる
                    conv = pr.corner_pos[-1] / pr.field_size * len(res)
                    print(f"      4角 前走{pr.corner_pos[-1]}/{pr.field_size}頭"
                          f"（今回換算 {conv:.1f}）→ **今回{p_now}/{len(res)}頭**"
                          f"　{p_now - conv:+.1f}"
                          + ("　← 前走より前を取った" if p_now - conv <= -1.0 else ""))
                elif p_now:
                    print(f"      4角 今回{p_now}/{len(res)}頭"
                          f"（{leg([p_now], len(res))}）")
        print()

    print(f"  穴馬は全{total}頭。")
    print("  ⚠️ ここから『この日はこういう日だった』と一般化しないこと（§32）。")
    print("     穴馬は着順で選んだ集団なので、共通点は必ず出る。")


if __name__ == "__main__":
    main()
