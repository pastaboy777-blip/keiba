"""自前スピード指数のデータ取得層（マキシマム競馬新聞の指数を逆算・再現）。
指数計算の本体は speed_index.py（確定版 k=10・二次パー・実測基準の符号一貫）。ここは
DBページから各馬の過去走(タイム/距離/馬場)を拾い、speed_index に渡して指数化する配管。
・過去走の馬場差は当日実測が理想だが毎回は引けないので、過去走評価には二次パー＋BABA_OFFで代替。
・距離±400m内の過去走のみ対象（凡例「±500m内で算出」に準拠）、venue で評価会場を指定。
・代表値：近2走最高(=上段)／近5走最高(=下段)。上段無印×下段有印相当＝条件替わりの巻返し妙味。
・展開が主役、これは"能力上限の客観確認"の補助レイヤー。比重は上げない。

検証：良馬場ではほぼ完璧、外れは道悪に集中（前開催大井60Rで3着内95%・外れ3件は全て重/不良）。
→ 道悪精度は speed_index の「当日実測基準」を過去走にも効かせれば更に上がる（次の一手）。
"""
import re, os, sys
import monogatari as M
import speed_index as SI

# 過去走の馬場差は「その日の実測基準」が理想だが、他日の全馬時計は毎回は引けないので、
# 標準二次パー(SI.par_std)に大井キャッシュ実測の馬場ティア差を1回だけ乗せる（方向のみ担保）。
BABA_OFF = {"良": 0.0, "稍重": -0.6, "重": -1.2, "不良": 0.0}   # 稍重/重は勝ちタイムが速い＝基準を速める
NEAR = 400          # 距離±400mまで同一距離群として評価

def _sec(t):
    m = re.match(r"(\d)\.(\d\d)\.(\d)$", t)
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None

def par(dist, baba):
    """基準タイム＝標準二次パー＋馬場ティア差（過去走評価用のフォールバック）。"""
    return SI.par_std(dist) + BABA_OFF.get(baba, 0.0)

def race_index(dist, baba, own_sec):
    """1レース分の自前指数（確定版 k=10）。速い(基準比)ほど＋。"""
    if own_sec is None or dist is None:
        return None
    return SI.index(own_sec, par(dist, baba))

def parse_ooi_history(cd, venue="大井"):
    """DBページ→ 指定会場の過去走 [(y,m,d, dist, baba, own_sec, chaku, ninki, ago)]。新しい順。
    own_sec は掲載タイム(上位6頭)から着順で取得。6着以下(未掲載)は None でスキップ。"""
    f = os.path.join(M.ARC, f"umaNEW_{cd}.html")
    if not os.path.exists(f):
        try: M._get(f"{M.BASE}/db/uma/{cd}/kanzen", f)
        except Exception: return []
    h = open(f, encoding="utf-8", errors="replace").read()
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        if 'class="tuka"' not in r: continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r)).strip()
        if venue not in txt: continue
        d = re.search(r"(\d{4})年(\d+)月(\d+)日", txt)
        dist = re.search(r"(\d+)m", txt)
        baba = re.search(r"[・(](良|稍重|重|不良)", txt)
        ch = re.search(r"(\d+)着", txt)
        nk = re.search(r"\((\d+)人気\)", txt)
        if not (d and dist and ch): continue
        times = re.findall(r"\b(\d\.\d\d\.\d)\b", txt)
        chaku = int(ch.group(1))
        own = _sec(times[chaku - 1]) if 1 <= chaku <= len(times) else None
        out.append((int(d.group(1)), int(d.group(2)), int(d.group(3)),
                    int(dist.group(1)), baba.group(1) if baba else "良",
                    own, chaku, int(nk.group(1)) if nk else None))
    out.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [row + (i + 1,) for i, row in enumerate(out)]   # ago = 何走前

def horse_index(cd, cur_dist, before=None, venue="大井"):
    """馬の自前指数プロファイル。
    戻り: dict(best2, best5, best10, list, makuri) — list は [(ago,y,m,d,dist,baba,idx,chaku,nk)]。
    before=(y,m,d) を渡すとその日より前の走のみ（当日リーク防止）。venue で評価会場を指定。"""
    hist = parse_ooi_history(cd, venue)
    if before:
        hist = [r for r in hist if (r[0], r[1], r[2]) < before]
        hist = [r[:8] + (i + 1,) for i, r in enumerate(hist)]
    rows = []
    for (y, mo, dy, dist, baba, own, chaku, nk, ago) in hist:
        if own is None or abs(dist - cur_dist) > NEAR: continue
        idx = race_index(dist, baba, own)
        if idx is not None:
            rows.append((ago, y, mo, dy, dist, baba, idx, chaku, nk))
    if not rows:
        return {"best2": None, "best5": None, "best10": None, "list": [], "makuri": False}
    def bestn(n):
        v = [r[6] for r in rows if r[0] <= n]
        return max(v) if v else None
    b2, b5, b10 = bestn(2), bestn(5), bestn(10)
    # 上段(近2)無印 × 下段(近5)有印 相当：近5走の地力が近2走より明確に上＝巻き返し妙味
    makuri = (b2 is not None and b5 is not None and b5 - b2 >= 6)
    return {"best2": b2, "best5": b5, "best10": b10, "list": rows, "makuri": makuri}

def show(cd, cur_dist, before=None):
    p = horse_index(cd, cur_dist, before)
    print(f"cd={cd} {cur_dist}m  近2走最高={p['best2']} 近5走最高={p['best5']} 近10={p['best10']}"
          + ("  ★巻き返し妙味" if p["makuri"] else ""))
    for (ago, y, mo, dy, dist, baba, idx, chaku, nk) in p["list"][:10]:
        print(f"   {ago}走前 {y}/{mo}/{dy} {dist}m {baba:<3} 指数{idx:+4d} {chaku}着 {nk}人")

if __name__ == "__main__":
    import glob
    if len(sys.argv) >= 3:
        show(sys.argv[1], int(sys.argv[2]))
    else:  # デモ：キャッシュから数頭
        for f in glob.glob(os.path.join(M.ARC, "umaNEW_*.html"))[:5]:
            cd = os.path.basename(f)[7:-5]
            show(cd, 1600)
            print()
