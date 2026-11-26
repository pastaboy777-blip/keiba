# -*- coding: utf-8 -*-
import re, glob, statistics as st

def flat(fp):
    h = open(fp, encoding="utf-8", errors="replace").read()
    t = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    x = re.sub(r"<[^>]+>", "|", t); x = re.sub(r"[ 　]+", " ", x)
    return re.sub(r"\|{3,}", "||", x)

ROW = re.compile(
    r"\|(\d{1,2})\|\s*\|(\d)\|\s*\|(\d{1,2})\|\s*\|\s*\|\s*([ァ-ヴーヶ・A-Za-z]{2,18})\s*\|\s*\|\s*"
    r"\|(牡|牝|セ)(\d)\s*/[^|]*\|\s*\|([\d.]+)\|\s*\|\s*(\d{3})\|([+\-±][\d０]+)\s*\|.*?"
    r"\|([^|]{2,8}?)\|\s*\(([^)]+)\)\s*\|\s*\|(?:(\d):)?(\d{1,2})\.(\d)\|.*?\|([\d.]{4})\|\s*\|[^|]{2,6}\|\s*\|(\d{1,2})\|", re.S)

def one(fp):
    x = flat(fp)
    R = re.search(r"競走成績 \| ([\d/]+) (\d+R)", x)
    dist = re.search(r"ダ([\d,]+)m", x)
    cond = re.search(r"ダ：\|\|(良|稍重|重|不良)", x)
    cls  = re.search(r"\|\s*(Ｃ\d[一二三四五六七八九]?|Ｂ\d[一二三四五六七八九]?|Ａ\d[一二三四五六七八九]?|[^|]{2,24}?)\s*\|\s*\|サラブレッド系", x)
    lap  = re.search(r"ハロンタイム\|\s*\|([\d.\-]+)\|", x)
    ag   = re.search(r"上がり\|\s*\|([^|]+)\|", x)
    c4   = re.search(r"４角\|\s*\|([^|]+)\|", x)
    c3   = re.search(r"３角\|\s*\|([^|]+)\|", x)
    st3  = re.search(r"三連単\|\s*\|[\d\-]+\|\s*\|([\d,]+) 円\|", x)
    tan  = re.search(r"単勝\|\s*\|\d+\|\s*\|([\d,]+) 円\|\s*\|(\d+)番人気", x)
    rows = []
    for m in ROW.finditer(x):
        (ch, wk, ub, nm, sx, ag2, kin, wt, dw, jk, be, t1, t2, t3, up, nin) = m.groups()
        rows.append(dict(chaku=int(ch), ub=int(ub), name=nm.strip(), sex=sx+ag2,
                         weight=int(wt), dw=dw, jockey=jk.strip(),
                         sec=(int(t1) if t1 else 0)*60+int(t2)+int(t3)/10,
                         agari=float(up), ninki=int(nin)))
    return dict(R=(R.group(2) if R else "?"), dist=(dist.group(1).replace(",","") if dist else "?"),
                cond=(cond.group(1) if cond else "?"), cls=(cls.group(1) if cls else "?"),
                lap=(lap.group(1) if lap else ""), ag=(ag.group(1).strip() if ag else ""),
                c3=(c3.group(1).strip() if c3 else ""), c4=(c4.group(1).strip() if c4 else ""),
                st3=(st3.group(1) if st3 else "?"), tan=(tan.groups() if tan else ("?","?")),
                rows=rows)

def rank4(c4):
    out, r = {}, 0
    for tok in re.findall(r"\([^)]*\)|\d+", c4):
        for v in re.findall(r"\d+", tok):
            r += 1; out[int(v)] = r
    return out

for fp in sorted(glob.glob('/tmp/r0802_*.html')):
    d = one(fp)
    rk = rank4(d["c4"])
    laps = [float(v) for v in d["lap"].split("-") if v]
    ten = sum(laps[:3]) if len(laps) >= 6 else None
    print(f"■{d['R']:>4} {d['dist']}m {d['cond']} 【{d['cls']}】 {len(d['rows'])}頭  単{d['tan'][0]}円({d['tan'][1]}人気) 三連単{d['st3']}円")
    print(f"     ラップ {d['lap']}   {d['ag']}" + (f"   前半3F {ten:.1f}" if ten else ""))
    print(f"     4角 {d['c4']}")
    for r in d["rows"][:4]:
        print(f"       {r['chaku']}着 {r['ub']:>2}{r['name']:<14}{r['sex']:<4}{r['jockey']:<6}"
              f"4角{rk.get(r['ub'],'?'):>2}位  {r['sec']:.1f}  上り{r['agari']}  {r['weight']}k{r['dw']}  {r['ninki']}人気")
    print()
