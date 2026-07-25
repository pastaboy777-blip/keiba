#!/usr/bin/env python3
"""【変態ファクター①】レースレベル伝播ネットワーク。
馬自身のタイム・着順・血統を一切見ず、「そのレースに誰がいて、その馬たちが"他の場所"で
どれだけ走ったか」だけでレースの格(level)を推定し、そこから馬の隠れ実力を測る。

核心：着順は"誰と走ったか"を無視している。強いレースの4着は弱いレースの1着より上。
市場は着順とタイムしか見ないので、ここに恒常的な歪みがある。

アルゴリズム(PageRank的な反復収束):
  馬力(horse) = Σ_過去走 [ レベル(race) + 着順ボーナス(相対順位) ]  / 走数
  レベル(race) = median( そのレースの出走馬の馬力 )     ←自レース分は除いて循環を緩和
  上記を交互に反復して収束させる。初期値は全レース level=0。

出力：各馬の net_power(ネットワーク由来の実力)。人気薄で net_power 上位＝
「弱いレースで勝ってきた人気馬」に対し「強いレースで負けてきた過小評価馬」を炙る。

使い方(検証):
  python3 scripts/racenet.py --from 2026-04-01 --to 2026-07-24 --iters 6
"""
import sys, argparse, datetime, statistics
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def scan(d0, d1, tracks=TRACKS):
    """期間の全レースを {rid: {"date","place","R","dist","rows":[(horse,finish,pop,field)]}}。"""
    c = PoliteClient()
    races = {}
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in tracks:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                rr_ = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                rr_ = {}
            for R, rid in sorted(rr_.items()):
                try:
                    pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                    res = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                if not res.rows or not res.rows[0].finish_pos:
                    continue
                rows = []
                for row in res.rows:
                    if row.horse_name and row.finish_pos:
                        rows.append((row.horse_name.strip(), row.finish_pos, row.popularity or 99))
                if len(rows) < 5:
                    continue
                races[rid] = {"date": day.isoformat(), "place": tr, "R": R,
                              "dist": getattr(pc, "distance", None), "rows": rows,
                              "field": len(rows)}
        day += datetime.timedelta(days=1)
    return races


def build(races, iters=6):
    """反復収束で race level と horse power を求める。"""
    horse_runs = defaultdict(list)          # horse -> [(rid, finish, field)]
    for rid, r in races.items():
        for name, fin, pop in r["rows"]:
            horse_runs[name].append((rid, fin, r["field"]))
    level = {rid: 0.0 for rid in races}     # レースの格(初期0)
    power = {h: 0.0 for h in horse_runs}    # 馬の実力

    def rank_bonus(fin, field):
        """相対順位ボーナス。1着=+1.0, 中位=0, 最下位=-1.0 の線形。"""
        if field <= 1:
            return 0.0
        return 1.0 - 2.0 * (fin - 1) / (field - 1)

    for it in range(iters):
        # 1) 馬力 = 出たレースの格 + そこでの相対着順
        for h, runs in horse_runs.items():
            vals = [level[rid] + rank_bonus(fin, fld) for rid, fin, fld in runs]
            power[h] = sum(vals) / len(vals) if vals else 0.0
        # 2) レースの格 = 出走馬の馬力の中央値(ただし"そのレースの寄与"を除いた馬力で)
        for rid, r in races.items():
            ps = []
            for name, fin, pop in r["rows"]:
                runs = horse_runs[name]
                others = [(rr, f, fl) for rr, f, fl in runs if rr != rid]   # 自レースを除外＝循環緩和
                if not others:
                    continue
                v = sum(level[rr] + rank_bonus(f, fl) for rr, f, fl in others) / len(others)
                ps.append(v)
            if ps:
                level[rid] = statistics.median(ps)
        # 正規化(発散防止): レベル平均を0に
        m = statistics.mean(level.values()) if level else 0.0
        for rid in level:
            level[rid] -= m
    return level, power, horse_runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--iters", type=int, default=6)
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    races = scan(d0, d1)
    print(f"=== レースレベル伝播ネットワーク {a.frm}〜{a.to} ===")
    print(f" 取込 {len(races)}R / 延べ出走 {sum(len(r['rows']) for r in races.values())}")
    level, power, horse_runs = build(races, a.iters)
    lv = sorted(level.items(), key=lambda kv: -kv[1])
    print(f"\n[レースレベル上位5(=出た馬が他所でも走った=ハイレベル戦)]")
    for rid, v in lv[:5]:
        r = races[rid]
        print(f"  lv{v:+.3f} {r['date']} {r['place']}{r['R']}R ダ{r['dist']} {r['field']}頭")
    print(f"[レースレベル下位3(=低調戦)]")
    for rid, v in lv[-3:]:
        r = races[rid]
        print(f"  lv{v:+.3f} {r['date']} {r['place']}{r['R']}R ダ{r['dist']} {r['field']}頭")
    print(f"\n[net_power上位10頭(ネットワーク実力)]")
    for h, v in sorted(power.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {v:+.3f} {h[:12]:12s} ({len(horse_runs[h])}走)")


if __name__ == "__main__":
    main()
