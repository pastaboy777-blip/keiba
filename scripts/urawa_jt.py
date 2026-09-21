#!/usr/bin/env python3
"""**その場・その馬場で、誰が乗り／どこから来た馬が走るか。**

    python3 scripts/urawa_jt.py --jsonl data/baba/urawa_furyo_1y.jsonl --place 浦和

`nankan_baba.py` が作った物差し（レース一覧）を入力に、**騎手・調教師・
前走の場・前走からの距離変化**で3着内率を割る。

⚠️ 楽天の結果ページの騎手欄は「櫻井光 (川崎)」の形で、**括弧の中が騎手の
   所属場**。これで「地元騎手か、他場からの遠征騎手か」が分かる。

⚠️ 前走は**出馬表の馬柱**から取る（結果ページには無い）。`nankan_baba.py` が
   不良レースの出馬表を既にキャッシュしているので追加取得は不要。

⚠️ 恒久ルール5：物差し作り。回収率は数えない。

── 実測（浦和・不良 2025-09-21〜2026-09-20・50レース511頭）──────

  **騎手の所属場がいちばん大きく割れる。**

      大井 **45.5%** (30/66)  ／ 川崎 33.7% (31/92)
      船橋   29.0% (29/100)  ／ **浦和 23.4%** (56/239)

    → 遠征騎手 ＞ 地元騎手。倍近い差。
    → 騎手個人では 笹川翼(大井) **65.2%** (15/23)、0%が2人(8頭以上)。
    → 調教師では 繁田健 **70.8%** (17/24)、0%が3厩舎(8頭以上)。

  **馬の遠征は逆向きで、効かない。**

      前走 浦和 32.7% (86/263) ／ 川崎 25.5% (13/51) ／ 船橋 21.0% (29/138)

    → 「川崎からの遠征馬が良い」は支持されない。地元組が最上位。
       騎手は遠征が効くのに馬の遠征は効かない、という**逆向き**。

  **距離の延長・短縮は効かない。**

      延長+400m以上 27.6% ／ 延長+100〜300m 27.2% ／ 同じ 29.7%
      短縮-100〜300m 32.3% ／ 短縮-400m以上 25.3%

    → 全部25〜32%に収まり、単調ですらない。材料になっていない。

⚠️⚠️ **騎手・調教師の数字は人気と交絡している。**上手い騎手・強い厩舎には
   人気馬が集まる。これがオッズの外にある妙味かどうかは、**人気帯で割らない
   と分からない**。JRA側で「その競馬場での好走歴」が全体 +9.1pt に見えたのに、
   人気帯で割ったら4帯すべてマイナスだった前例がある（シンプソンのパラドックス）。
   `--by-pop` を通してから結論を出すこと。
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nankeiba.scraping import rakuten as rk                 # noqa: E402


def jockey_home(j: str) -> tuple[str, str]:
    """騎手欄 → (騎手名, 所属場)。

    ⚠️ 楽天は「櫻井光 (川崎)」の形で書く。**括弧の中が騎手の所属場**で、
       これが「地元か遠征か」の唯一の手がかり。見習い印（☆◇△）は名前に
       付いたまま残す（減量の有無そのものが材料になりうるので落とさない）。
    """
    j = (j or "").strip()
    if "(" not in j:
        return j, "不明"
    name, _, rest = j.partition("(")
    return name.strip(), rest.rstrip(")").strip() or "不明"


def rate(d):
    return f"{d[0]/d[1]*100:>5.1f}% ({d[0]:>3}/{d[1]:<3})" if d[1] else "—"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--min", type=int, default=8, help="この頭数未満は出さない")
    a = ap.parse_args()
    H = [json.loads(l) for l in open(a.jsonl, encoding="utf-8") if l.strip()]
    cli = rk.KeibaRakuten()
    jk_home = defaultdict(lambda: [0, 0])      # 騎手の所属場
    jk = defaultdict(lambda: [0, 0])           # 騎手個人
    tr = defaultdict(lambda: [0, 0])           # 調教師
    prev_place = defaultdict(lambda: [0, 0])   # 前走の場
    dist_mv = defaultdict(lambda: [0, 0])      # 距離の変化
    n_card = 0
    for r in sorted(H, key=lambda x: (x["date"], x["race"])):
        try:
            base = cli.find_race_id(r["date"], a.place, 1)[:-2]
            rid = f"{base}{r['race']:02d}"
            res = rk.parse_result(cli.get(f"/race_performance/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        if not res:
            continue
        hist = {}
        try:
            card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            for e in card.get("entries") or []:
                hs = e.get("history") or []
                if hs:
                    hist[e["umaban"]] = hs[0]
            n_card += 1
        except Exception:                                   # noqa: BLE001
            pass
        for x in res:
            f = x.get("finish")
            if not f:
                continue
            im = 1 if f <= 3 else 0
            name, home = jockey_home(x.get("jockey"))
            for d, k in ((jk_home, home), (jk, name),
                         (tr, (x.get("trainer") or "不明"))):
                d[k][0] += im; d[k][1] += 1
            h = hist.get(x.get("umaban"))
            if h and h.place:
                prev_place[h.place][0] += im; prev_place[h.place][1] += 1
            if h and h.distance and r["distance"]:
                dd = r["distance"] - h.distance
                k = ("**延長**+400m以上" if dd >= 400 else "延長+100〜300m" if dd >= 100
                     else "同じ距離" if abs(dd) < 100 else "短縮-100〜300m"
                     if dd > -400 else "**短縮**-400m以上")
                dist_mv[k][0] += im; dist_mv[k][1] += 1

    print(f"\n■ {a.place}・{os.path.basename(a.jsonl)}　{len(H)}レース"
          f"／馬柱が取れたレース {n_card}")
    print(f"\n── 騎手の所属場（括弧の中）──────────────")
    for k, v in sorted(jk_home.items(), key=lambda kv: -kv[1][1]):
        if v[1] >= a.min:
            print(f"  {k:<6}{rate(v)}")
    print(f"\n── 騎手個人（{a.min}頭以上）────────────────")
    for k, v in sorted(jk.items(), key=lambda kv: -(kv[1][0]/kv[1][1])):
        if v[1] >= a.min:
            print(f"  {k:<8}{rate(v)}")
    print(f"\n── 調教師（{a.min}頭以上）─────────────────")
    for k, v in sorted(tr.items(), key=lambda kv: -(kv[1][0]/kv[1][1])):
        if v[1] >= a.min:
            print(f"  {k:<8}{rate(v)}")
    print(f"\n── 前走がどこだったか ───────────────────")
    for k, v in sorted(prev_place.items(), key=lambda kv: -kv[1][1]):
        if v[1] >= a.min:
            print(f"  {k:<6}{rate(v)}")
    print(f"\n── 前走からの距離変化 ───────────────────")
    for k in ("**延長**+400m以上", "延長+100〜300m", "同じ距離",
              "短縮-100〜300m", "**短縮**-400m以上"):
        if dist_mv[k][1] >= a.min:
            print(f"  {k:<18}{rate(dist_mv[k])}")
    print("\n⚠️ 物差し。回収率は数えていない（恒久ルール5）。")


if __name__ == "__main__":
    main()
