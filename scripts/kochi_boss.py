#!/usr/bin/env python3
"""【ボス理論・高知ファイナル限定検証】
高知は同じ弱い馬が延々と回り続ける＝序列理論の理想的な実験場。特にファイナルレース(最終R)は
万馬券の宝庫として有名。§26では「序列固定度が高い=堅い(lift0.75)」だったが、高知ファイナルは
対戦を繰り返しまくるのに大荒れ＝「序列が刻まれない(弱い馬は着順がランダム)」のか
「ボス信号がさらに強い」のかを実データで判定する。

出力: ①高知ファイナル(最終R)限定 ②高知の全レース ③南関(比較対象) の
      ボス度別 複勝率lift と 序列固定度の分布。
※リーク無し(時系列順・各レース時点までの対戦のみ使用)。

使い方: python3 scripts/kochi_boss.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


class Bucket:
    def __init__(self):
        self.d = defaultdict(lambda: [0, 0])
        self.base = [0, 0]
        self.fixed = []          # 序列固定度の分布
        self.nrace = 0

    def add(self, k, g):
        c = self.d[k]; c[0] += g; c[1] += 1

    def report(self, label):
        b = self.base[0] / self.base[1] if self.base[1] else 0
        fx = sum(self.fixed) / len(self.fixed) if self.fixed else 0
        print(f"\n=== {label} ===")
        print(f" {self.nrace}R / 人気薄n={self.base[1]} ベース複勝{b:.1%} / 平均序列固定度{fx:.0%}")
        if not self.base[1]:
            return
        for k in ["★ボス(3戦+勝率60%+)", "中間", "子分(3戦+勝率30%-)", "対戦歴0"]:
            v = self.d.get(k)
            if not v or not v[1]:
                print(f"  {k:20s} n0"); continue
            r = v[0] / v[1]
            print(f"  {k:20s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--warmup", default="2026-05-15")
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    beat = defaultdict(int); met = defaultdict(int)
    B = {"高知ファイナル": Bucket(), "高知(全R)": Bucket(), "南関(比較)": Bucket()}

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in ["高知", "浦和", "船橋", "大井", "川崎"]:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            if not races:
                continue
            final_R = max(races)                      # その日の最終レース=ファイナル
            for R, rid in sorted(races.items()):
                try:
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                rows = [(r.horse_name.strip(), r.finish_pos, r.popularity or 99)
                        for r in rr.rows if r.horse_name and r.finish_pos]
                if len(rows) < 5:
                    continue
                names = [n for n, f, p in rows]
                tgt = []
                if tr == "高知":
                    tgt.append(B["高知(全R)"])
                    if R == final_R:
                        tgt.append(B["高知ファイナル"])
                else:
                    tgt.append(B["南関(比較)"])
                if day >= warm:
                    tot = kn = 0
                    for i in range(len(names)):
                        for j in range(i + 1, len(names)):
                            tot += 1
                            if met[frozenset((names[i], names[j]))] > 0:
                                kn += 1
                    fixed = kn / tot if tot else 0
                    for bk in tgt:
                        bk.nrace += 1; bk.fixed.append(fixed)
                    for name, fin, pop in rows:
                        if pop < a.usui or pop == 99:
                            continue
                        g = 1 if fin <= 3 else 0
                        w = l = 0
                        for o in names:
                            if o == name:
                                continue
                            w += beat[(name, o)]; l += beat[(o, name)]
                        enc = w + l
                        if enc == 0:
                            k = "対戦歴0"
                        else:
                            wr = w / enc
                            k = ("★ボス(3戦+勝率60%+)" if (enc >= 3 and wr >= 0.6)
                                 else ("子分(3戦+勝率30%-)" if (enc >= 3 and wr <= 0.3) else "中間"))
                        for bk in tgt:
                            bk.base[0] += g; bk.base[1] += 1
                            bk.add(k, g)
                # 履歴更新
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1, _ = rows[i]; n2, f2, _ = rows[j]
                        met[frozenset((n1, n2))] += 1
                        if f1 < f2:
                            beat[(n1, n2)] += 1
                        elif f2 < f1:
                            beat[(n2, n1)] += 1
        day += datetime.timedelta(days=1)

    print(f"=== ボス理論 高知ファイナル限定検証 {a.warmup}〜{a.to} 人気薄≥{a.usui} ===")
    for k in ["高知ファイナル", "高知(全R)", "南関(比較)"]:
        B[k].report(k)


if __name__ == "__main__":
    main()
