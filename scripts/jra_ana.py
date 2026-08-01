#!/usr/bin/env python3
"""中央(JRA)の穴馬抽出。能力側（時計だけ）と市場側（オッズ）のズレを見る。

    # その日の全場・全レース
    python3 scripts/jra_ana.py --date 20260801

    # 場とレースを絞る／門を緩める
    python3 scripts/jra_ana.py --date 20260801 --place 新潟 --races 9-12
    python3 scripts/jra_ana.py --date 20260801 --gate-cond 5 --gate-market 5

    # 重みの感度と、ペース項を外した場合の残差を見る
    python3 scripts/jra_ana.py --date 20260801 --place 中京 --sens --no-pace

考え方・式の中身は `nankeiba.core.jra_ana` の docstring を読むこと。
ここは取得と表示とログだけを持つ。

⚠️ 予想は必ず `--log` でCSVに残すこと。重み(0.5/0.06)は回収率で最適化して
   おらず、結果を積んで直していく前提。ログが無いと直しようがない。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import jra_ana as ja                # noqa: E402
from nankeiba.scraping import keibabook as kb          # noqa: E402

LOG_COLS = ["日付", "場", "R", "馬場種", "距離", "馬番", "馬名", "印",
            "条件指数", "条件順", "実力指数", "実力順", "市場人気", "市場ソース",
            "人気薄好走", "スコア", "残差SD", "着順"]


def parse_races(s: str) -> list[int]:
    if not s:
        return list(range(1, 13))
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def load_race(client, rid, *, history=8, before=None):
    """1レース分の出馬表＋各馬の過去走を取る。

    ⚠️ 条件は必ず race_id を渡してナビ帯から引く。渡さないと本文検索にフォール
       バックし、**どのレースでも1Rの距離**が返る（keibabook 側の警告参照）。
    """
    syu = client.get(f"/cyuou/syutuba/{rid}")
    hd = kb.parse_race_header_cyuou(syu, rid)
    entries = kb.parse_entries(syu)
    for e in entries:
        try:
            e["runs"] = kb.parse_history(
                client.get(f"/db/uma/{e['umacd']}/seiseki"),
                limit=history, drop_turf=False)
            e["runs"] = ja.before_date(e["runs"], before)   # 当日行を必ず落とす
        except Exception:                              # noqa: BLE001
            e["runs"] = []
    return hd, entries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--place", action="append", help="省略時はその日の全場")
    ap.add_argument("--races", default="1-12")
    ap.add_argument("--history", type=int, default=8, help="1頭あたり何走まで見るか")
    ap.add_argument("--gate-cond", type=int, default=ja.GATE_COND)
    ap.add_argument("--gate-power", type=int, default=ja.GATE_POWER)
    ap.add_argument("--gate-market", type=float, default=ja.GATE_MARKET)
    ap.add_argument("--ana-pop", type=int, default=ja.ANA_POP)
    ap.add_argument("--power", choices=("median", "max"), default="median",
                    help="実力指数の定義。median=ふだんの水準(既定) / max=全走ベスト")
    ap.add_argument("--w-ana", type=float, default=ja.W_ANA)
    ap.add_argument("--w-pop", type=float, default=ja.W_POP)
    ap.add_argument("--no-pace", action="store_true",
                    help="ペース項を外して残差SDを比べる")
    ap.add_argument("--sens", action="store_true", help="重みの感度を見る")
    ap.add_argument("--show-all", action="store_true", help="落ちた馬も出す")
    ap.add_argument("--log", help="予測をCSVに追記する")
    ap.add_argument("--cookie", default="data/.keibabook_cookie")
    args = ap.parse_args()

    client = kb.KeibabookClient.from_cookie_file(args.cookie)
    meetings = kb._meetings_cyuou(client.get(f"/cyuou/nittei/{args.date}"))
    places = args.place or sorted(meetings)
    for p in places:
        if p not in meetings:
            print(f"⚠️ {args.date} に {p} の開催は無い。開催: {list(meetings)}",
                  file=sys.stderr)
    places = [p for p in places if p in meetings]
    if not places:
        sys.exit(1)
    rnos = parse_races(args.races)
    d = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"

    # --- 取得 ---------------------------------------------------------------
    races = []
    for pl in places:
        ids = kb.find_meeting_cyuou(client, args.date, pl)
        for rno in rnos:
            if rno > len(ids):
                continue
            print(f"取得中 {pl}{rno}R …", end="\r", file=sys.stderr)
            try:
                hd, entries = load_race(client, ids[rno - 1], history=args.history,
                                        before=d)
            except Exception as e:                     # noqa: BLE001
                print(f"{pl}{rno}R 取得失敗: {e}", file=sys.stderr)
                continue
            if entries and hd.get("surface"):
                races.append((pl, rno, ids[rno - 1], hd, entries))
    print(" " * 40, file=sys.stderr)
    if not races:
        print("出馬表が取れなかった。発表前かも。", file=sys.stderr)
        sys.exit(1)

    # --- 第1段: その日の全出走馬の過去走を一度にまとめて回帰 -----------------
    allruns = [r for _, _, _, _, ents in races for e in ents for r in e.get("runs", [])]
    model = ja.TimeModel.fit(allruns, use_pace=not args.no_pace, before=d)
    if model is None:
        print("回帰に必要な母数が足りない。", file=sys.stderr)
        sys.exit(1)

    print(f"=== {d} 中央 穴候補（{'・'.join(places)} / {len(races)}R） ===")
    print(f"\n[第1段] 時計指数 … {model.n}レース分の勝ちタイムを条件分解")
    print(f"  残差SD {model.resid_sd:.2f}秒"
          f"（{'ペース項あり' if model.use_pace else 'ペース項なし'}）"
          f" → **これより小さい条件指数の差は差と見ない**")
    b = model.baba_report()
    print("  馬場係数 " + " / ".join(f"{k}{v:+.2f}" for k, v in b.items()))
    if model.baba_sane():
        print("  ✅ 芝は渋るほど遅い・ダートは湿るほど速い＝正しい向き")
    else:
        print("  ⚠️ 馬場係数の向きが逆。母数不足かパース漏れ。**指数を信用しないこと**")
    if model.use_pace:
        alt = ja.TimeModel.fit(allruns, use_pace=False, before=d)
        if alt:
            print(f"  参考: ペース項を外すと残差SD {alt.resid_sd:.2f}秒 "
                  f"→ {alt.resid_sd - model.resid_sd:+.2f}秒")

    pw = "ふだんの水準(全走中央値)" if args.power == "median" else "全走ベスト"
    print(f"\n[第2段] 門 … ①条件{args.gate_cond}位以内(今日の条件のベスト) "
          f"②実力{args.gate_power}位以内でない({pw}) "
          f"③市場人気{args.gate_market:g}以下")
    print(f"[第3段] スコア = 条件指数 + {args.w_ana}×人気薄好走 + {args.w_pop}×市場人気\n")

    kw = dict(gate_cond=args.gate_cond, gate_power=args.gate_power,
              gate_market=args.gate_market, ana_pop=args.ana_pop, power=args.power,
              before=d)
    rows = []
    for pl, rno, rid, hd, ents in races:
        surf = hd["surface"]
        cands, _ = ja.evaluate(ents, surf, w_ana=args.w_ana, w_pop=args.w_pop,
                               model=model, **kw)
        passed = sorted((c for c in cands if c.passed),
                        key=lambda c: -c.score)
        head = (f"■ {pl}{rno}R {surf}{hd.get('course') or ''}{hd.get('distance')}m "
                f"{hd.get('race_name') or ''} {len(ents)}頭")
        if not passed:
            print(f"{head}  → 候補なし")
        else:
            print(head)
            print("     馬             条件指数 条件順 実力順 人気 薄好走 スコア")
            for i, c in enumerate(passed):
                mark = "◎" if i == 0 else ("○" if i == 1 else "▲")
                print(f"  {mark}{c.umaban:>2} {c.name[:8]:<8} "
                      f"{c.cond_idx:+7.2f} {c.cond_rank:>5} {c.power_rank:>5} "
                      f"{c.market:>5.1f} {c.ana_wins:>4} {c.score:>7.2f}")
            if args.sens:
                tally, n = ja.sensitivity(ents, surf, model=model,
                                          w_ana=(args.w_ana / 2, args.w_ana, args.w_ana * 2),
                                          w_pop=(args.w_pop / 2, args.w_pop, args.w_pop * 2),
                                          **kw)
                top = max(tally, key=tally.get) if tally else None
                if top is not None and tally[top] == n:
                    print(f"     感度: 重みを1/2〜2倍に振っても◎は{top}番のまま（{n}通り）")
                else:
                    order = " ".join(f"{k}番×{v}" for k, v in
                                     sorted(tally.items(), key=lambda x: -x[1]))
                    print(f"     ⚠️ 感度: 重み次第で◎が入れ替わる（{order}）"
                          f" → この日の◎は重みの産物。信用しない")
        if args.show_all:
            for c in sorted(cands, key=lambda c: (c.cond_rank or 99)):
                if not c.passed and c.cond_rank and c.cond_rank <= args.gate_cond + 3:
                    ci = f"{c.cond_idx:+.2f}" if c.cond_idx is not None else "  -  "
                    mk = f"{c.market:.1f}" if c.market is not None else " - "
                    print(f"    {c.umaban:>3} {c.name[:8]:<8} {ci:>7} "
                          f"条{c.cond_rank} 実{c.power_rank} 人{mk}  {c.why()}")
        print()

        for i, c in enumerate(passed):
            rows.append([d, pl, rno, surf, hd.get("distance"), c.umaban, c.name,
                         "◎○▲"[min(i, 2)], c.cond_idx, c.cond_rank, c.power_idx,
                         c.power_rank, c.market, c.market_src, c.ana_wins, c.score,
                         round(model.resid_sd, 2), ""])

    if args.log and rows:
        new = not os.path.exists(args.log)
        os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
        with open(args.log, "a", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(LOG_COLS)
            w.writerows(rows)
        print(f"→ {args.log} に {len(rows)}行 追記（着順は後で埋める）")


if __name__ == "__main__":
    main()
