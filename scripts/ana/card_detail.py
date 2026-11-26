# -*- coding: utf-8 -*-
"""8/3船橋 出馬表を1頭ずつ展開材料に落とす"""
import re, sys, datetime

TODAY = datetime.date(2026, 8, 3)

def flat(fp):
    h = open(fp, encoding="utf-8", errors="replace").read()
    t = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    x = re.sub(r"<[^>]+>", "|", t)
    x = re.sub(r"[ 　]+", " ", x)
    return re.sub(r"\|{3,}", "||", x)

# 前走ブロック: 場 YY.MM.DD | ... クラス | 距離+馬場+人気 | 騎手+斤量 | タイム(差) | 上がり 体重 ゲート | 通過順 | 相手
RUN = re.compile(
    r"\|(\d{1,2})\|\s*\|\s*\|(良|稍|重|不)\|\s*\|(\d{1,2})頭\|.*?"
    r"(浦和|船橋|大井|川崎|門別|金沢|名古屋|園田|高知|佐賀|水沢|盛岡|笠松|札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)"
    r" (\d\d)\.(\d\d)\.(\d\d)\|.*?"
    r"(\d{3,4})(左|右|直)?ダ\s*(\d{1,2})人\|.*?"
    r"(?:(\d):)?(\d{1,2})\.(\d)\s*\(([-\d.]+)\)\s*\|.*?"
    r"([\d.]+) (\d{3})k (\d{1,2})番\s*\|\s*([\d\-]+)\|",
    re.S)

HEAD = re.compile(r"\|\|([ァ-ヴーヶ・]{2,16})\|\|")

def parse(fp):
    x = flat(fp)
    R = re.search(r"出馬表 \| ([\d/]+) (\d+R)", x)
    D = re.search(r"(\d{3,4})m成績", x)
    marks = [m.start() for m in re.finditer(r"\|◎\|", x)]
    hs = []
    for k, pos in enumerate(marks):
        pre = x[max(0, pos-90):pos]
        nums = re.findall(r"\|\s*(\d+)\s*\|", pre)
        ub = int(nums[-1]) if nums else k+1
        seg = x[pos:(marks[k+1] if k+1 < len(marks) else len(x))]
        nm = HEAD.search(seg)
        if not nm: continue
        sire = re.search(r"\|\s*([ァ-ヴーヶ・A-Za-z]{3,20})\|\s*\|\|" + re.escape(nm.group(1)), seg)
        sa = re.search(r"\|\s*(牡|牝|セ)\s?(\d)\s*\|", seg)
        kg = re.search(r"\|\s*(?:牡|牝|セ)\s?\d\s*\|[^|]*\|\s*([\d.]{3,4})\s*\|", seg)
        jk = re.search(r"\|([^|]{2,7}?)\|\s*\|（[^）]{1,6}）\|", seg)
        runs = []
        for r in RUN.finditer(seg):
            (ch, ba, n, pl, yy, mm, dd, dist, lr, nin,
             t1, t2, t3, sa_, ag, wt, gate, cor) = r.groups()
            d = datetime.date(2000+int(yy), int(mm), int(dd))
            runs.append(dict(chaku=int(ch), baba=ba, n=int(n), place=pl, date=d,
                             dist=int(dist), ninki=int(nin),
                             sec=(int(t1) if t1 else 0)*60+int(t2)+int(t3)/10, diff=float(sa_),
                             agari=float(ag), weight=int(wt), gate=int(gate),
                             cor=[int(v) for v in cor.split("-") if v]))
            if len(runs) >= 3: break
        hs.append(dict(ub=ub, name=nm.group(1), sex=(sa.group(1)+sa.group(2) if sa else "?"),
                       kin=(kg.group(1) if kg else "?"),
                       jockey=(jk.group(1).strip() if jk else "?"),
                       sire=(sire.group(1) if sire else "?"), runs=runs))
    return (R.group(2) if R else "?"), (D.group(1) if D else "?"), hs

def show(fp):
    R, dist, hs = parse(fp)
    print(f"=== {R}  {dist}m  {len(hs)}頭 ===")
    for h in sorted(hs, key=lambda z: z["ub"]):
        print(f"[{h['ub']:>2}] {h['name']:<14}{h['sex']:<4}{h['kin']:<6}{h['jockey']:<6} 父{h['sire']}")
        for i, r in enumerate(h["runs"]):
            gap = (TODAY - r["date"]).days if i == 0 else (h["runs"][i-1]["date"] - r["date"]).days
            dd = r["dist"] - int(dist) if i == 0 else 0
            print(f"      {'前走' if i==0 else ('前々' if i==1 else '3走')} {r['date']} {r['place']}{r['dist']}m{r['baba']} "
                  f"{r['n']}頭 {r['ninki']}人 → {r['chaku']}着 ({r['diff']:+.1f}) "
                  f"通過{'-'.join(map(str,r['cor']))} 上り{r['agari']} {r['weight']}k 枠{r['gate']} 中{gap-1}日"
                  + (f"  ★今回{dd:+d}m" if i == 0 and dd else ""))
        print()

if __name__ == "__main__":
    for a in sys.argv[1:]:
        show(a)
