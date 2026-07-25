#!/usr/bin/env python3
"""叩き3戦目シグナルの南関大規模バックテスト(4トラック・期間指定)。
各開催日の全レース×全馬について、人気薄(既定6番人気以下)の中で叩きN戦目バケツ別に
3着内率(複勝)・1着率(勝)を集計し、ベース比liftを出す。トラック別/距離帯別/他タグ重なりも。
使い方(背景推奨): python3 scripts/tataki_backtest.py --from 2026-04-01 --to 2026-07-24 > report.txt
"""
import sys, argparse, datetime, json
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import tataki_n, edges_for, field_pace, agari_pattern

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def band(d):
    return "短" if d <= 1200 else ("マ" if d <= 1600 else ("中" if d <= 1900 else "長"))


def bucket_key(n):
    if n in (1, 2, 3):
        return n
    if isinstance(n, int) and n >= 4:
        return "4+"
    return "0"


class Agg:
    """好走数/母数のカウンタ群。"""
    def __init__(self):
        self.d = {}

    def add(self, key, good, win):
        c = self.d.setdefault(key, [0, 0, 0])  # [複勝(3着内), 母数, 勝(1着)]
        c[0] += good; c[1] += 1; c[2] += win


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6, help="この人気以下を穴とする")
    ap.add_argument("--tracks", default="浦和,船橋,大井,川崎")
    a = ap.parse_args()
    c = PoliteClient()
    tracks = a.tracks.split(",")
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)

    base = Agg(); byN = Agg(); byN3plus = Agg()
    byTrack = Agg()          # (track) 叩き3+のみ
    byBand = Agg()           # (距離帯) 叩き3+のみ
    overlap = Agg()          # 叩き3+ ×他タグ
    full_base = Agg(); full_N = Agg()  # 全人気(人気薄限定でない)対照
    pop_hits = []            # 叩き3+で3着内した馬の人気(穴の大きさ)
    n_races = 0; n_days = 0

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in tracks:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            if not races:
                continue
            n_days += 1
            for R, rid in sorted(races.items()):
                try:
                    _ch = c.get(CARD.format(r=rid), use_cache=True)
                    pc = P.parse_card_page(_ch, rid)
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                dist = getattr(pc, "distance", None)
                if not dist:
                    continue
                try:
                    from rakuten_ped import attach as _ap
                    _ap(_ch, pc.entries)
                except Exception:
                    pass
                n_races += 1
                tb = band(dist)
                pace, _ = field_pace(pc.entries)
                apct = agari_pattern(pc.entries)
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    e = emap.get(row.umaban)
                    if not e:
                        continue
                    good = 1 if row.finish_pos <= 3 else 0
                    win = 1 if row.finish_pos == 1 else 0
                    n = tataki_n(e, day)
                    bk = bucket_key(n)
                    # 全人気対照
                    full_base.add("all", good, win)
                    if isinstance(n, int) and n >= 3:
                        full_N.add("3+", good, win)
                    # ここから人気薄限定
                    if row.popularity < a.usui:
                        continue
                    base.add("base", good, win)
                    byN.add(bk, good, win)
                    if isinstance(n, int) and n >= 3:
                        byN3plus.add("3+", good, win)
                        byTrack.add(tr, good, win)
                        byBand.add(tb, good, win)
                        if good:
                            pop_hits.append(row.popularity)
                        tags, _ = edges_for(e, dist, pace=pace, agari_pct=apct.get(row.umaban), today=day)
                        for t in tags:
                            if t != "叩き3戦目穴":
                                overlap.add(t, good, win)
        day += datetime.timedelta(days=1)
        if day.day == 1 or (day - d0).days % 15 == 0:
            sys.stderr.write(f"...{day} 経過 races={n_races}\n"); sys.stderr.flush()

    def line(label, c3, cb):
        g, n, w = c3
        bg, bn, bw = cb
        b = bg / bn if bn else 0
        r = g / n if n else 0
        wr = w / n if n else 0
        return f" {label:16s} 複{g:>3}/{n:>4}={r:5.1%} lift{(r/b if b else 0):4.2f}  勝{w:>2}={wr:4.1%}"

    print(f"=== 叩きN戦目 南関バックテスト {a.frm}〜{a.to} / {a.tracks} ===")
    print(f" 開催日数={n_days} 有効レース={n_races} / 母集団=人気薄(≥{a.usui}番人気) / 好走=3着内")
    cb = base.d.get("base", [0, 0, 0])
    print(f"\n[ベース] 人気薄全体 複{cb[0]}/{cb[1]}={cb[0]/max(1,cb[1]):.1%} 勝{cb[2]}={cb[2]/max(1,cb[1]):.1%}")
    print("\n--- 叩きN戦目バケツ別(人気薄) ---")
    for k in [1, 2, 3, "4+"]:
        print(line(f"叩き{k}戦目" if k != "4+" else "叩き4戦目+", byN.d.get(k, [0, 0, 0]), cb))
    print(line("叩き3戦目以降", byN3plus.d.get("3+", [0, 0, 0]), cb))
    print("\n--- 叩き3戦目以降×トラック別(人気薄) ---")
    for tr in tracks:
        print(line(tr, byTrack.d.get(tr, [0, 0, 0]), cb))
    print("\n--- 叩き3戦目以降×距離帯別(人気薄) ---")
    for tb in ["短", "マ", "中", "長"]:
        print(line(f"{tb}帯", byBand.d.get(tb, [0, 0, 0]), cb))
    print("\n--- 叩き3戦目以降×他エッジ重なり(人気薄・複勝率) ---")
    for t, cc in sorted(overlap.d.items(), key=lambda kv: -kv[1][1]):
        if cc[1] >= 5:
            print(line(t, cc, cb))
    print("\n--- 対照:全人気(人気薄限定なし) ---")
    fb = full_base.d.get("all", [0, 0, 0])
    print(f" 全馬ベース 複{fb[0]}/{fb[1]}={fb[0]/max(1,fb[1]):.1%}")
    print(line("叩き3+ (全人気)", full_N.d.get("3+", [0, 0, 0]), fb))
    if pop_hits:
        pop_hits.sort()
        dd = sum(1 for p in pop_hits if p >= 10)
        print(f"\n[穴の大きさ] 叩き3+の3着内的中 {len(pop_hits)}本 / 平均{sum(pop_hits)/len(pop_hits):.1f}番人気 / 二桁人気{dd}本 / 最大{pop_hits[-1]}番人気")
    print("\n" + json.dumps({"races": n_races, "days": n_days}, ensure_ascii=False))


if __name__ == "__main__":
    main()
