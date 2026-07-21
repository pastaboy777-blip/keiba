"""別アプローチ②：前走の"展開不利"で着順が実力を過小評価している馬＝穴を炙り出す。
市場は着順に引っ張られる。前走のペース(S/M/H)×通過位置×着順で「負けて強し/勝って弱し」を判定。
DBページ1枚から前走の(ペース,1角通過,着順,上がり3F,人気,距離,馬場)を取得（追加fetch無し）。
シグナル別に今回の複勝率(3着内)を人気バケット別ベースラインと比較→lift(＝市場を超えるか)。
"""
import re, os, sys
from collections import defaultdict
import monogatari as M
import jiku_ana as J

MEETS = J.MEETS

def parse_db_races(cd):
    """DBページ→ [(y,m,d, baba, dist, pace, agari, c1, chaku, ninki)] 新しい順。"""
    f = os.path.join(M.ARC, f"umaNEW_{cd}.html")
    if not os.path.exists(f):
        try: M._get(f"{M.BASE}/db/uma/{cd}/kanzen", f)
        except Exception: return []
    h = open(f, encoding="utf-8", errors="replace").read()
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        if 'class="tuka"' not in r: continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r)).strip()
        d = re.search(r"(\d{4})年(\d+)月(\d+)日", txt)
        if not d: continue
        baba = re.search(r"[・(](良|稍重|重|不良)", txt)
        dist = re.search(r"(\d+)m", txt)
        pace = re.search(r"([SMH])ペース", txt)
        ag = re.search(r"上り[\d.]+-([\d.]+)", txt)
        ch = re.search(r"(\d+)着", txt)
        nk = re.search(r"\((\d+)人気\)", txt)
        tu = re.search(r'class="tuka">(.*?)</ul>', r, re.S)
        digs = re.findall(r">(\d+)<", tu.group(1)) if tu else []
        out.append((
            int(d.group(1)), int(d.group(2)), int(d.group(3)),
            baba.group(1) if baba else None,
            int(dist.group(1)) if dist else None,
            pace.group(1) if pace else None,
            float(ag.group(1)) if ag else None,
            int(digs[0]) if digs else None,
            int(ch.group(1)) if ch else None,
            int(nk.group(1)) if nk else None,
        ))
    return out

def zenso(cd, y, mo, dy):
    """target日付より前の最新レース。"""
    races = parse_db_races(cd)
    prev = [r for r in races if (r[0], r[1], r[2]) < (y, mo, dy)]
    if not prev: return None
    prev.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    return prev[0]

def signals(z):
    """前走特徴z → シグナルsetを返す。"""
    _, _, _, baba, dist, pace, ag, c1, ch, nk = z
    s = set()
    if pace and c1 and ch:
        if pace in ("S", "M") and c1 >= 7 and 4 <= ch <= 8:
            s.add("A_差し損ね")           # 前有利で後方から負け＝展開不利
        if pace == "H" and c1 <= 3 and ch >= 5:
            s.add("B_先行バテ")           # 前傾を先行して潰れた＝展開被害
        if pace == "S" and c1 <= 2 and ch <= 2:
            s.add("C_楽逃げ好走")         # スロー楽逃げで好走＝恵まれ(危険軸)
    return s

def run(kais):
    base = defaultdict(lambda: [0, 0])    # 人気bucket -> [n, 複]
    sighit = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # sig -> bucket -> [n,複]
    def bucket(nk):
        if nk <= 3: return "1-3人気"
        if nk <= 6: return "4-6人気"
        if nk <= 9: return "7-9人気"
        return "10-人気"
    nr = 0
    for kai in kais:
        for di, mmdd in enumerate(MEETS[kai]):
            mo, dy = int(mmdd[:2]), int(mmdd[2:])
            head = f"2026{kai}10{di+1:02d}"
            for rr in range(1, 13):
                rid = f"{head}{rr:02d}{mmdd}"
                try: d = M.race_danwa(rid)
                except Exception: continue
                if not d: continue
                res, baba = J.result(rid)
                if len(res) < 6: continue
                nr += 1
                for cd, info in d.items():
                    ub = info.get("umaban")
                    if ub is None or ub not in res: continue
                    ch, nk = res[ub]
                    if not nk or nk >= 99: continue
                    bk = bucket(nk); hit = ch <= 3
                    base[bk][0] += 1; base[bk][1] += hit
                    z = zenso(cd, 2026, mo, dy)
                    if not z: continue
                    for sig in signals(z):
                        sighit[sig][bk][0] += 1; sighit[sig][bk][1] += hit
    def pct(v): return f"{v[1]}/{v[0]}={v[1]/v[0]*100:.0f}%" if v[0] else "-"
    print(f"=== 前走・展開不利シグナル 検証（{nr}R） ===", flush=True)
    print("ベースライン（全馬）複勝率:", flush=True)
    for bk in ["1-3人気", "4-6人気", "7-9人気", "10-人気"]:
        if base[bk][0]: print(f"   {bk}: {pct(base[bk])}", flush=True)
    for sig in ["A_差し損ね", "B_先行バテ", "C_楽逃げ好走"]:
        print(f"\n【{sig}】シグナル該当馬の複勝率（vs 同人気ベース）:", flush=True)
        for bk in ["1-3人気", "4-6人気", "7-9人気", "10-人気"]:
            v = sighit[sig][bk]
            if v[0] >= 5:
                lift = (v[1]/v[0]) / (base[bk][1]/base[bk][0]) if base[bk][1] else 0
                print(f"   {bk}: {pct(v)}  (ベース{base[bk][1]/base[bk][0]*100:.0f}% / lift {lift:.2f}x)", flush=True)

if __name__ == "__main__":
    run(sys.argv[1:] or ["06","07","08","09","10"])
