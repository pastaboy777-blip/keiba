"""騎手ごとの「ラチ沿いに入れるか」── 4角で併走したとき、内側にいた割合。

  python3 jk_soto.py --build          # jk_soto.json を作る（harvest/ 全部から）
  python3 jk_soto.py <騎手名の一部>    # 1人を引く
  python3 jk_soto.py --top            # 上位と下位

── なぜ作ったか（2026-11-11）

  ユーザーの指摘 ──「⑦はラチ沿いにおくべき」「加藤はラチ沿いでケイバするの得意」。
  11/10 川崎7Rの⑦ルナティックブルーは**過去走がゼロ**で、馬側の材料が何も無かった。
  それでも4角は `(7,9)` の**内**で、12番人気3着。

  harvest の結果には騎手名が入っているので、騎手ごとに数えられた。

    107人 ／ 併走のべ 11,767回 ／ 内 5,264回 = **44.7%（基準線）**

    加藤雄   138回中 内 78 … **56.5%**（107人中3位）
    櫻井光   209回中 内120 … 57.4%
    東原悠    94回中 内 56 … 59.6%
    ──────────── 基準線 44.7%
    吉井章   221回中 内 71 … 32.1%
    篠谷葵   120回中 内 38 … 31.7%
    山口達    81回中 内 25 … 30.9%

  **上下で29ポイント開く。**

── ★ 基準は50%ではない（soto.py と同じ）

  2頭併走なら内にいられるのは1/2、3頭なら1/3。構造的な平均が**44.7%**。
  50%を境にすると半分以上を「内に入れる」と誤って拾う。

── ★ 母数を見ること

  併走60回未満の騎手は率が暴れる。札を出すのは60回以上から。

── ★ 枠・馬・騎手の3つがある

  枠       1-2枠79.7% ↔ 7-8枠29.4%（5,551頭・50ポイント）… いちばん強い
  騎手     59.6% ↔ 30.9%（11,767回・107人・29ポイント）
  馬の外率  soto.py。11/10 の28頭の検証で順序が壊れた。まだ弱い（ルール16）

  **食い違ったら枠を優先し、騎手で寄せる。**
"""
import sys, os, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "jk_soto.json")
MIN = 60


def build():
    J = {}
    for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json")):
        if os.sep + "old" + os.sep in f:
            continue
        try:
            D = json.load(open(f))
        except Exception:
            continue
        for k, v in D.items():
            rows = v.get("rows") or []
            g4 = (v.get("corner") or {}).get("4") or []
            if not rows or not g4:
                continue
            jk = {r["ub"]: (r.get("jk") or "").strip() for r in rows}
            for g in g4:
                if len(g) < 2:
                    continue
                for i, u in enumerate(g):
                    n = jk.get(u)
                    if not n:
                        continue
                    a = J.setdefault(n, [0, 0])
                    a[0] += 1
                    if i == 0:
                        a[1] += 1
    json.dump(J, open(OUT, "w"), ensure_ascii=False)
    t = sum(v[0] for v in J.values()); i = sum(v[1] for v in J.values())
    print("%d人 ／ 併走のべ %d回 ／ 内 %d回 = %.1f%% → %s" % (len(J), t, i, 100 * i / t, OUT))


def load():
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def rate(name):
    """騎手名（部分一致可）→ (内率, 併走回数)。母数が MIN 未満なら率は返さない。"""
    J = load()
    a = J.get(name)
    if not a:
        hit = [v for k, v in J.items() if name and name in k]
        if len(hit) != 1:
            return None, 0
        a = hit[0]
    return (a[1] / a[0] if a[0] >= MIN else None), a[0]


def main():
    a = sys.argv[1:]
    if "--build" in a:
        build(); return
    J = load()
    if not J:
        print("jk_soto.json がない。--build を先に。"); return
    if "--top" in a:
        big = sorted([(k, v) for k, v in J.items() if v[0] >= MIN],
                     key=lambda x: -x[1][1] / x[1][0])
        t = sum(v[0] for v in J.values()); i = sum(v[1] for v in J.values())
        print("基準線 %.1f%%（併走のべ %d回）\n" % (100 * i / t, t))
        for k, v in big[:12]:
            print("  %-8s %4d回中 内%4d  %5.1f%%" % (k, v[0], v[1], 100 * v[1] / v[0]))
        print("  ...")
        for k, v in big[-8:]:
            print("  %-8s %4d回中 内%4d  %5.1f%%" % (k, v[0], v[1], 100 * v[1] / v[0]))
        return
    if not a:
        print(__doc__); return
    q = a[0]
    for k, v in sorted(J.items()):
        if q in k:
            r = "%5.1f%%" % (100 * v[1] / v[0]) if v[0] >= MIN else "母数不足"
            print("  %-8s %4d回中 内%4d  %s" % (k, v[0], v[1], r))


if __name__ == "__main__":
    main()
