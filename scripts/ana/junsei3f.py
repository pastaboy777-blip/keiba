"""京大式「純正3ハロン」(久保和功) ── JRA(中央)専用。
純正3ハロン = ラスト2F目 + (ラスト1F × 2)。終い1Fを2倍評価し"本物の決め手"を測る。
JRA成績ページの公式ラップタイム(200m毎)から算出。値が小さいほど優秀。
※南関(keibabook)はハロン毎ラップが無いため算出不可 → 南関は総上がり3F/想定上がり/加速ラップ調教でカバー。
"""
import re, os, sys
import monogatari as M

def race_laps(rid, path=None):
    """JRA成績ページ → 200m毎ラップ列[秒]。"""
    p = path or os.path.join(M.ARC, f"csei_{rid}.html")
    if not os.path.exists(p):
        # 中央取得(monogatari_cyuou を使う環境ならそちら)。無ければ空。
        try: M._get(f"{M.BASE}/cyuou/seiseki/{rid}", p)
        except Exception: return []
    h = open(p, encoding="utf-8", errors="replace").read()
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
    m = re.search(r"ラップタイム((?:\s*\d{3,4}m)+)\s*((?:\d{1,2}\.\d\s*)+)", t)
    if not m: return []
    return [float(x) for x in re.findall(r"\d{1,2}\.\d", m.group(2))]

def junsei(laps):
    """ラップ列 → dict(純正3F, 上がり3F, L1F, L2F)。ラップ2本未満はNone。"""
    if len(laps) < 2: return None
    L1 = laps[-1]; L2 = laps[-2]
    j = round(L2 + 2 * L1, 1)
    a3 = round(sum(laps[-3:]), 1) if len(laps) >= 3 else None
    return {"junsei3f": j, "agari3f": a3, "L1F": L1, "L2F": L2}

def show(rid):
    laps = race_laps(rid)
    if not laps:
        print(f"{rid}: ラップ取得不可"); return
    j = junsei(laps)
    print(f"{rid}  ラップ{laps}")
    print(f"  純正3ハロン={j['junsei3f']}  (上がり3F={j['agari3f']}, L2F={j['L2F']}, L1F={j['L1F']})")
    print(f"  ※純正 < 上がり3F なら終い加速型（本物の決め手）／純正 > 上がり3F なら失速型")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        for rid in sys.argv[1:]: show(rid)
    else:  # デモ：キャッシュの中央成績から
        import glob
        for f in sorted(glob.glob(os.path.join(M.ARC, "csei_*.html")))[:6]:
            show(os.path.basename(f)[5:-5])
