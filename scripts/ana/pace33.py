"""33ラップとペース指数を、手元のラップ（tsuka_data.jsonl）から出す。

  python3 pace33.py 浦和 2026-10          # その場・その月の各鞍を一覧
  python3 pace33.py 浦和 2026-10 --base   # 基準タイムの表だけ出す

PDF新聞（鈴木ショータ）の2つの指標を自前で再現したもの。読み方は
notes/live/pdf_shinbun_bachu.md を見ること。

  前半タイム = 走破時計 − レース上がり3F（＝ゴール前600mを除いた部分）
  33ラップ    = 前半3F − 上がり3F          正が瞬発力勝負／負が持久力勝負
  ペース指数  = (実測の前半タイム − 基準) × 10   正がスロー／負がハイ
                −1〜+1 が M、+1以上が S、−1以下が H

★基準の作り方について（2026-10-22 にユーザーと詰めた）

  基準は「場 × 距離 × 馬場」まで。**クラスでは割らない。**
  ただし2歳限定戦だけは別建てにする（成長が速く、7月→9月で0.8秒動くため）。

  本家は古馬もクラスで割っているらしく、同じ浦和ダ1400で基準が
  51.19 / 50.54 / 49.44 と1.75秒ぶれる。指数は差×10なので、
  **クラスの割り当てだけで指数が17.5も動いてしまう**。実測前半の振れ幅
  （浦和ダ1400の同日6鞍で2.8秒＝28）と同じオーダーで、これでは
  「流れが速かったか遅かったか」ではなく能力差の指標になる。
  クラスの強弱は shirushi.py が別に持っているので、ここでは混ぜない。

★係数10について

  本家の紙面から逆算すると距離で9.6〜11.5と動くように見えるが、
  **2鞍からでは係数と基準を分離できない**（基準0.02秒の違いが係数9.6と10の
  違いに化ける）。確定には同一条件3鞍以上の連立が要る。当面は10固定。
"""
import sys, json, os, statistics as st
from collections import defaultdict

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tsuka_data.jsonl")
COEF = 10.0
MIN_N = 3          # 基準を作るのに最低これだけの鞍が要る


def zenhan(lap):
    """前半タイム＝走破時計 − 上がり3F。ラップの最後3本を除いた合計。"""
    return round(sum(lap[:-3]), 2) if len(lap) > 3 else None


def lap33(lap):
    """33ラップ＝前半3F − 上がり3F。800m(4本)は 1F目 − 4F目。"""
    if len(lap) < 4:
        return None
    if len(lap) == 4:
        return round(lap[0] - lap[3], 2)
    return round(sum(lap[0:3]) - sum(lap[-3:]), 2)


def is_2sai(rec):
    c = (rec.get("cls") or rec.get("cond") or "")
    return "2歳" in c or "２歳" in c


def key(rec):
    """基準を引くキー。場 × 距離 × 馬場 × (2歳戦かどうか)"""
    return (rec.get("track"), rec.get("dist"), rec.get("baba") or "?", is_2sai(rec))


def load(track=None, ym=None):
    out = []
    for line in open(DATA):
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("lap"):
            continue                      # ラップ保存前に取った記録は飛ばす
        if track and r.get("track") != track:
            continue
        if ym and not (r.get("date") or "").startswith(ym):
            continue
        out.append(r)
    return out


def baselines(recs):
    g = defaultdict(list)
    for r in recs:
        z = zenhan(r["lap"])
        if z is not None:
            g[key(r)].append(z)
    return {k: st.median(v) for k, v in g.items() if len(v) >= MIN_N}, g


def mark(v):
    return "S" if v >= 1 else ("H" if v <= -1 else "M")


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    track = a[0] if a else None
    ym = a[1] if len(a) > 1 else None
    recs = load(track, ym)
    if not recs:
        print("ラップつきの記録がありません。capture.py で取り直してください。")
        print("（tsuka_data.jsonl の古い記録には lap が入っていません）")
        return
    base, groups = baselines(recs)

    if "--base" in sys.argv:
        print("基準タイム（前半タイムの中央値）")
        for k in sorted(base, key=lambda t: (str(t[0]), t[1] or 0, str(t[2]))):
            tr, d, bb, y = k
            print("  %-4s %5sm %-3s %-6s  %6.2f秒  (%d鞍)"
                  % (tr, d, bb, "2歳限定" if y else "", base[k], len(groups[k])))
        return

    print("  日付        R  距離  馬場  走破計  前半    33ラップ  ペース指数  勝ち馬")
    for r in sorted(recs, key=lambda z: z["rid"]):
        lap = r["lap"]
        z, l33 = zenhan(lap), lap33(lap)
        b = base.get(key(r))
        pi = (z - b) * COEF if (b is not None and z is not None) else None
        w = sorted(r["rows"], key=lambda x: x["chaku"])[0]
        tk = "-".join(map(str, w["tsuka"] or []))
        print("  %s %2sR %4sm %-3s %6.1f %6.2f   %+6.2f   %s  %s(%s人気 %s)"
              % (r["date"], r["rid"][10:12], r["dist"], r.get("baba") or "?",
                 sum(lap), z if z is not None else -1,
                 l33 if l33 is not None else 0,
                 ("%s%+6.1f" % (mark(pi), pi)) if pi is not None else "   基準なし",
                 w["name"][:10], w["nk"], tk))


if __name__ == "__main__":
    main()
