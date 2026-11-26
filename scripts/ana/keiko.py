"""この条件（場×距離）で、**3着内に来た馬が4コーナーでどこにいたか**。

  python3 keiko.py 大井 1200            # 1つの条件を見る
  python3 keiko.py 大井 1200 --baba 不良  # その馬場だけ
  python3 keiko.py --kyou a.json,b.json 大井 1200   # 今日ここまでの分と並べる

── 何を出すか（2026-11-15、ユーザーの見本の画像どおり）

  ユーザーの指示 ──「真似して」「書いてあること」＋見本2枚。見本の文面は

    過去の傾向
    この条件東京芝2000m　3着内の4角　良(117鞍) 前51・中36・後13・外53%
    　／　稍重(14鞍) 前74・中21・後5・外62%　／　重以上(なし)

  これを南関（ダートだけ）に移したもの。出すのは **4角の位置と内外の分布だけ**。
  ★ 回収率・的中率・倍率は出さない（CLAUDE.md 冒頭 ★★★ 最優先）。

── 位置の3分け

  前＝0〜1/3、中＝1/3〜2/3、後＝2/3〜1（見本が「前1/3から」と書いているのに合わせた）。
  相対位置は `(通過順 − 1) / (頭数 − 1)`。頭数は**その角に記録された馬の数**、
  通過順は括弧（併走）を同位に数えたもの ── `harvest.pos_of` / `tenkai_zu.rel` と同じ読み方。
  **前・中・後は％記号なしの数字**で、合計が100になるように丸める（見本の書き方）。

── 外◯%

  **4角で併走していた馬のうち、いちばん外にいた割合**。
  通過順の括弧は内→外の並びなので、括弧の最後にいれば外（`soto.py` と同じ読み方）。
  ★ **単独で走っていた馬は母数から外す。** 併走していた馬しか内外は分からない
    （CLAUDE.md ルール14。「ラチ沿いを走った」と「併走の内にいた」は別のこと）。
  ★ 基準は50%ではない ── 2頭併走なら外にいられるのは1/2、3頭なら1/3なので
    構造的な平均は45%あたり（`soto.py` の「★ 基準は50%ではない」）。

── 馬場の分け方は4つ（良・稍重・重・不良）

  見本は3つ（良／稍重／重以上）だが、**南関は不良が多い**ので重と不良を混ぜない。
  大井1200mは 良178 / 稍重63 / 重25 / 不良77鞍 で、まとめると不良が重に埋もれる。
  `tenkai.py` の水準（`toki.json`）も4つに分けてあるので、そちらと揃う。
  データが無い馬場は見本どおり `(なし)` と書く。

── 元データ

  `scripts/ana/harvest/*_res.json` だけ。**取りに行かない**（楽天も競馬ブックも叩かない）。
  harvest が増えたら自動で増える（`--build` するものは無い）。
"""
import sys, os, json, glob, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
VEN = {"ooi": "大井", "fun": "船橋", "ura": "浦和", "kaw": "川崎"}
PRE = {v: k for k, v in VEN.items()}
BABA = ["良", "稍重", "重", "不良"]      # 見本は3つだが南関は不良が多いので分ける
_CACHE = {}


def _blank():
    return {"races": 0, "mae": 0, "naka": 0, "ushiro": 0, "grp": 0, "out": 0}


def pos_of(seq, ub):
    """括弧つきの並びから、その馬番の順位（括弧の中は同位）。harvest.pos_of と同じ。"""
    p = 1
    for g in seq:
        if ub in g:
            return p
        p += len(g)
    return None


def _add(e, rel, g, i):
    if rel is not None:
        if rel < 1 / 3:
            e["mae"] += 1
        elif rel < 2 / 3:
            e["naka"] += 1
        else:
            e["ushiro"] += 1
    if g is not None and len(g) > 1:      # ★ 単独は母数から外す（ルール14）
        e["grp"] += 1
        if i == len(g) - 1:
            e["out"] += 1


def scan(ven):
    """その場の harvest を1回だけ読み、{(距離, 馬場): 集計} にして覚える。"""
    if ven in _CACHE:
        return _CACHE[ven]
    pre = PRE.get(ven)
    out = collections.defaultdict(_blank)
    if not pre:
        _CACHE[ven] = out
        return out
    for f in sorted(glob.glob(os.path.join(HERE, "harvest", "%s*_res.json" % pre))):
        try:
            D = json.load(open(f))
        except Exception:
            continue
        for r in D.values():
            seq = (r.get("corner") or {}).get("4")
            dist, baba = r.get("dist"), r.get("baba")
            if not seq or not dist:
                continue
            flat = [u for g in seq for u in g]
            if len(flat) < 2:
                continue
            e = out[(dist, baba)]
            e["races"] += 1
            for row in (r.get("rows") or []):
                if (row.get("chaku") or 99) > 3:
                    continue
                ub = row.get("ub")
                p = pos_of(seq, ub)
                rel = (p - 1) / (len(flat) - 1) if p else None
                g = next((g for g in seq if ub in g), None)
                _add(e, rel, g, g.index(ub) if g else None)
    _CACHE[ven] = out
    return out


def cond(ven, dist, baba=None):
    """場×距離（×馬場）の集計を1つ返す。baba=None なら全馬場をまとめる。"""
    S = scan(ven)
    e = _blank()
    for (d, b), v in S.items():
        if d != dist or (baba is not None and b != baba):
            continue
        for k in e:
            e[k] += v[k]
    return e


def pcts(e):
    """前・中・後を％記号なしの整数で（合計100になるように丸める）。母数0なら None。"""
    n = e["mae"] + e["naka"] + e["ushiro"]
    if not n:
        return None
    raw = [100 * e[k] / n for k in ("mae", "naka", "ushiro")]
    fl = [int(x) for x in raw]
    for i in sorted(range(3), key=lambda i: -(raw[i] - fl[i]))[:100 - sum(fl)]:
        fl[i] += 1
    return fl


def soto(e):
    return (e["out"] / e["grp"]) if e["grp"] else None


def seg(e):
    """「前51・中36・後13・外53%」。位置が出なければ None。"""
    p = pcts(e)
    if not p:
        return None
    s = "前%d・中%d・後%d" % tuple(p)
    r = soto(e)
    return s + ("・外%.0f%%" % (100 * r) if r is not None else "")


def head(ven, dist, sur="ダ"):
    """見本で少し強調されている頭の部分 ──「この条件大井ダ1200m」"""
    return "この条件%s%s%dm" % (ven, sur, dist)


def body(ven, dist):
    """頭のあと ──「3着内の4角　良(178鞍) 前…　／　稍重(63鞍) …　／　重(なし)　／　…」"""
    parts = []
    for b in BABA:
        e = cond(ven, dist, b)
        s = seg(e) if e["races"] else None
        parts.append("%s(なし)" % b if not s else "%s(%d鞍) %s" % (b, e["races"], s))
    return "3着内の4角　%s" % "　／　".join(parts)


def text(ven, dist, sur="ダ"):
    """見本の1行 ──「この条件大井ダ1200m　3着内の4角　良(178鞍) 前…　／　…」"""
    return "%s　%s" % (head(ven, dist, sur), body(ven, dist))


# ── 今日ここまで（kekka.py の json をそのまま読む）
def kyou(paths):
    """kekka.py が出した結果の json を集めて、今日ここまでの3着内を数える。

    ★ ここでも**取りに行かない**。引数で渡された json だけを読む。"""
    e = _blank()
    for p in paths:
        try:
            D = json.load(open(p))
        except Exception:
            continue
        for v in (D if isinstance(D, list) else [D]):
            cn = v.get("corner") or []
            seq = cn[-1]["seq"] if (cn and isinstance(cn, list)) else (
                (cn or {}).get("4") if isinstance(cn, dict) else None)
            if not seq:
                continue
            flat = [u for g in seq for u in g]
            if len(flat) < 2:
                continue
            e["races"] += 1
            hs = v.get("horses") or {}
            it = hs.values() if isinstance(hs, dict) else hs
            for row in it:
                if (row.get("chaku") or 99) > 3:
                    continue
                ub = row.get("ub")
                p_ = pos_of(seq, ub)
                rel = (p_ - 1) / (len(flat) - 1) if p_ else None
                g = next((g for g in seq if ub in g), None)
                _add(e, rel, g, g.index(ub) if g else None)
    return e


MAE_TH, SOTO_TH = 8.0, 8.0      # ふだんとの差がこれ以上あれば「来ている」と書く
SOTO_MIN = 5                    # 外の母数がこれ未満なら向きを書かない（偏りなし）


def kyou_line(k, futsu):
    """ペースの箱の2行目。今日の分が無ければ None（＝前日のカードでは出ない）。

    ★ 見本 ──「今日ここまで3鞍の3着内: 4角で前1/3から55%（ふだん56%）・外28%（ふだん51%）
      → 内が来ている」。向きは**外の割合**で決める（差 8ポイントで切る）。"""
    if not k or not k["races"]:
        return None
    p, pf = pcts(k), pcts(futsu)
    if not p:
        return None
    s = "今日ここまで%d鞍の3着内: 4角で前1/3から%d%%" % (k["races"], p[0])
    if pf:
        s += "（ふだん%d%%）" % pf[0]
    r, rf = soto(k), soto(futsu)
    muki = None
    if r is not None:
        s += "・外%.0f%%" % (100 * r)
        if rf is not None:
            s += "（ふだん%.0f%%）" % (100 * rf)
            d = 100 * (r - rf)
            muki = ("偏りなし" if (k["grp"] < SOTO_MIN or abs(d) < SOTO_TH)
                    else ("外が来ている" if d > 0 else "内が来ている"))
    return s + ("→ %s" % muki if muki else "")     # 見本は「…（ふだん51%）→ 内が来ている」


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    pos = [x for i, x in enumerate(a)
           if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]
    ven = pos[0] if pos else "大井"
    if len(pos) < 2:
        S = scan(ven)
        for d in sorted({d for d, b in S}):
            print("%s %dm … %d鞍" % (ven, d, sum(v["races"] for (dd, b), v in S.items() if dd == d)))
        return
    dist = int(pos[1])
    print(text(ven, dist))
    b = g("--baba")
    if b:
        e = cond(ven, dist, b)
        print("  %s(%d鞍) %s" % (b, e["races"], seg(e) or "―"))
    if g("--kyou"):
        k = kyou([x for x in g("--kyou").split(",") if x])
        print("  " + (kyou_line(k, cond(ven, dist, b)) or "今日の分はまだ無い"))


if __name__ == "__main__":
    main()
