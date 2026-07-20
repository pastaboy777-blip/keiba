"""コーナー通過順（(a,b,c)=併走は内→外, カンマ=前→後, -=やや開く, ==大差）を解析し、
各馬の【4角での 前後位置(group_rank) と 内外(lane: 0=最内)】を自動抽出。
今日の稍重の"勝ち位置=内でロスなく差す"を、写真なしでデータから判定する。
"""
import re, os, sys
import monogatari as M

def corners(rid):
    h = open(os.path.join(M.ARC, f"sei_{rid}.html"), encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(r"<th>([１２３４])角</th>\s*<td>([^<]+)</td>", h):
        cn = "１２３４".index(m.group(1)) + 1
        out[cn] = m.group(2).strip()
    return out

def parse_line(s):
    """通過順文字列 → [(group_rank, lane, umaban)]  lane:0=最内"""
    # トークン: (..)=併走群 / 単独数字。区切り , - = は群の前後
    res = []
    grank = 0
    for tok in re.findall(r"\((?:[^)]*)\)|\d+", s):
        grank += 1
        members = [int(x) for x in re.findall(r"\d+", tok)]
        for lane, ub in enumerate(members):   # ( )内は内→外
            res.append((grank, lane, ub))
    return res

def finish(rid):
    h = open(os.path.join(M.ARC, f"sei_{rid}.html"), encoding="utf-8", errors="replace").read()
    fin = {}
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        row = m.group(1)
        if 'class="umaban"' not in row: continue
        tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 14 or not re.match(r"^\d+$", tds[0]): continue
        ub = int(re.search(r'class="umaban">(\d+)', row).group(1))
        ni = None
        for i in range(13, len(tds)-1):
            if re.match(r"^\d{1,2}$", tds[i]) and re.match(r"^\d{2}\.\d$", tds[i-1]) and re.match(r"^\d{1,3}\.\d$", tds[i+1]): ni=i;break
        fin[ub] = {"chaku": int(tds[0]), "nk": int(tds[ni]) if ni else None}
    return fin

def run(rid):
    cs = corners(rid); fin = finish(rid)
    if 4 not in cs: print("4角データなし"); return
    c4 = {ub: (gr, ln) for gr, ln, ub in parse_line(cs[4])}
    print(f"=== {rid} 4角の 前後×内外 → 着順 ===")
    print(f"4角生: {cs[4]}")
    rows = []
    for ub, (gr, ln) in c4.items():
        f = fin.get(ub, {})
        rows.append((f.get("chaku", 99), ub, gr, ln, f.get("nk")))
    for chaku, ub, gr, ln, nk in sorted(rows):
        lane = "最内" if ln == 0 else f"内から{ln+1}頭目"
        band = "前" if gr <= 2 else "好位" if gr <= 4 else "中団" if gr <= 6 else "後方"
        star = " ★馬券圏" if chaku <= 3 else ""
        print(f"  {chaku:2d}着 {ub:2d}番({nk}人) 4角: {band}・{lane}{star}")

if __name__ == "__main__":
    run(sys.argv[1])
