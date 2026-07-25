#!/usr/bin/env python3
"""【ボス理論・実戦版】集団の記憶で「今日の相手に勝ち越している人気薄」を出走前に抽出する。
§26で両期完全再現(勝率高lift1.34/子分0.67)、§26-Aで的中の79%が万馬券レースと確認済み。

  build : 過去結果から対戦グラフ(誰が誰に勝ったか)を構築し JSON 保存
  pick  : 指定日・場のカードを読み、各馬の「今日の相手に対する直接対決成績」を出す

使い方:
  python3 scripts/boss_pick.py build --from 2026-04-01 --to 2026-07-26
  python3 scripts/boss_pick.py pick --date 2026-07-27 --place 川崎
"""
import sys, json, argparse, datetime
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]
DB = Path("scratchpad/boss_db.json")


def cmd_build(a):
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    beat = defaultdict(int)
    nrace = 0
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in TRACKS:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            for R, rid in sorted(races.items()):
                try:
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                rows = [(r.horse_name.strip(), r.finish_pos) for r in rr.rows
                        if r.horse_name and r.finish_pos]
                if len(rows) < 5:
                    continue
                nrace += 1
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i]; n2, f2 = rows[j]
                        if f1 < f2:
                            beat[n1 + "\t" + n2] += 1
                        elif f2 < f1:
                            beat[n2 + "\t" + n1] += 1
        day += datetime.timedelta(days=1)
    DB.parent.mkdir(exist_ok=True)
    DB.write_text(json.dumps({"from": a.frm, "to": a.to, "races": nrace, "beat": dict(beat)},
                             ensure_ascii=False))
    print(f"対戦グラフ構築: {nrace}R / 勝敗ペア{len(beat)}組 → {DB}")


def cmd_pick(a):
    if not DB.exists():
        raise SystemExit("対戦DBが無い。先に build を実行してください。")
    d = json.loads(DB.read_text())
    beat = d["beat"]
    print(f"=== {a.date} {a.place} ボス理論ピック（対戦DB: {d['from']}〜{d['to']} {d['races']}R）===")
    print(" ★ボス=今日の相手に3戦以上かつ勝率60%+ / 消=3戦以上かつ勝率30%- (§26 lift1.34 vs 0.67)")
    print(" ※レースの序列固定度: 高=堅い(穴狙い不向き) / 低=荒れやすい\n")
    c = PoliteClient()
    ymd = a.date.replace("-", "")
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    Rs = [a.race] if a.race else sorted(races)
    for R in Rs:
        pc = P.parse_card_page(c.get(CARD.format(r=races[R]), use_cache=True), races[R])
        ent = [(e.umaban, (e.horse_name or "").strip(), getattr(e, "exp_pop", None))
               for e in pc.entries if e.umaban and e.horse_name]
        if len(ent) < 5:
            continue
        names = [n for u, n, p in ent]
        # 序列固定度(既に勝敗が付いているペアの比率)
        tot = kn = 0
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                tot += 1
                if beat.get(names[i] + "\t" + names[j], 0) or beat.get(names[j] + "\t" + names[i], 0):
                    kn += 1
        fixed = kn / tot if tot else 0
        lab = "序列固定(堅い)" if fixed >= 0.5 else ("序列中" if fixed >= 0.2 else "序列未確定(荒れ)")
        dist = getattr(pc, "distance", None)
        rows = []
        for um, nm, pop in ent:
            w = l = 0; det = []
            for o in names:
                if o == nm:
                    continue
                wi = beat.get(nm + "\t" + o, 0); li = beat.get(o + "\t" + nm, 0)
                w += wi; l += li
                if wi or li:
                    det.append(f"{o[:6]}{wi}-{li}")
            enc = w + l
            if enc == 0:
                continue
            wr = w / enc
            mark = ""
            if enc >= 3 and wr >= 0.6:
                mark = "★ボス"
            elif enc >= 3 and wr <= 0.3:
                mark = "消"
            rows.append((-(wr if enc >= 3 else 0), -enc, um, nm, pop, w, l, wr, mark, det))
        if not rows:
            continue
        rows.sort()
        print(f"■ {R:>2}R ダ{dist} {len(ent)}頭  序列固定度{fixed:.0%}={lab}")
        for _, _, um, nm, pop, w, l, wr, mark, det in rows:
            if not mark and w + l < 2:
                continue
            ps = f"{pop}人気予" if pop else "人気?"
            usui = "◆人気薄" if (pop and pop >= 6) else ""
            print(f"   {mark:4s} {um:>2} {nm[:10]:10s} {ps:7s} 対戦{w}勝{l}敗({wr:.0%}) {usui}  " +
                  " ".join(det[:5]))
        print()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--from", dest="frm", required=True); b.add_argument("--to", dest="to", required=True)
    p = sub.add_parser("pick")
    p.add_argument("--date", required=True); p.add_argument("--place", required=True)
    p.add_argument("--race", type=int, default=None)
    a = ap.parse_args()
    (cmd_build if a.cmd == "build" else cmd_pick)(a)


if __name__ == "__main__":
    main()
