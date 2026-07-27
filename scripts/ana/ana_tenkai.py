#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""荒れたレースの穴だけを拾うツール（展開一本）。

考え方:
  「前走で前に行けたのに凡走した馬」＝ 展開の形は持っているのに市場が評価していない馬。
  前走で好走していれば人気になる。凡走していれば人気は落ちる。
  そこに その日の馬場（前残りか差しか）を掛ける。

使い方:
  python3 scripts/ana/ana_tenkai.py <楽天出馬表RACEID> [--bias 前|差]
  例) python3 scripts/ana/ana_tenkai.py 202607272115060103

判定（2026/7/27 川崎12Rで検証）:
  ★A（推奨・絞り）前走3角までに3番手以内 × 前走4着以下 × 前走6番人気以下
      候補10頭／3着内3頭(30%)。**荒れた2レースを両方捉えた**
      → 3R ①フラワーガールエス 1着（三連単604,120円）
      → 10R ⑤ウワサノアノコ 3着（三連単44,150円）
   B（広め）人気条件なし  候補26頭／42%。10Rは⑨2着・⑤3着の両方を捉える
   C（最精度）前走3角で【先頭】 × 前走4着以下  候補15頭／53%。ただし10R⑤を取りこぼす
"""
import re, subprocess, os, sys

TMP = os.environ.get("ANATMP", "/tmp/anatenkai")
os.makedirs(TMP, exist_ok=True)

def fetch(rid):
    fp = f"{TMP}/{rid}.html"
    if not (os.path.exists(fp) and os.path.getsize(fp) > 50000):
        subprocess.run(["curl", "-s", "-L", "--max-time", "20",
                        f"https://keiba.rakuten.co.jp/race_card/list/RACEID/{rid}",
                        "-o", fp], check=False)
    return open(fp, encoding="utf-8", errors="replace").read()

def parse(html):
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    x = re.sub(r"<[^>]+>", "|", t); x = re.sub(r"[ 　]+", " ", x)
    x = re.sub(r"\|{3,}", "||", x)
    title = re.search(r"競馬場 出馬表 \| ([\d/]+) (\d+R)", x)
    dist = re.search(r"(\d{3,4})m成績", x)
    marks = [m.start() for m in re.finditer(r"\|◎\|", x)]
    hs = []
    for k, pos in enumerate(marks):
        pre = x[max(0, pos-90):pos]
        nums = re.findall(r"\|\s*(\d+)\s*\|", pre)
        ub = int(nums[-1]) if nums else k+1
        seg = x[pos:(marks[k+1] if k+1 < len(marks) else len(x))]
        nm = re.search(r"\|\|([ァ-ヴーヶ・]{2,16})\|\|", seg)
        if not nm: continue
        heads = [int(v) for v in re.findall(r"(\d+)頭", seg)]
        cor = re.findall(r"\|\s*(\d+(?:-\d+){2,3})\s*\|", seg)
        ch = re.findall(r"\|(\d{1,2})\|\s*\|\s*\|(良|重|稍|不)\|", seg)
        di = re.findall(r"(\d{3,4})(?:左|右|直)?(?:ダ|芝)\s*(\d+)人", seg)
        jk = re.search(r"\|((?:[▲△☆★◇])?[^|]{2,6})\|\s*\|（[^）]{1,6}）\|", seg)
        pl = re.findall(r"(浦和|川崎|大井|船橋|門別|金沢|名古屋|園田|高知|佐賀|水沢|盛岡|笠松) (\d\d\.\d\d\.\d\d)", seg)
        if not cor: 
            hs.append(dict(ub=ub, name=nm.group(1), pas=None, front=None, c4=None,
                           chaku=None, ninki=None, n=None, jockey=(jk.group(1).strip() if jk else "?"),
                           place=None)); continue
        p = [int(v) for v in cor[0].split("-")]
        hs.append(dict(ub=ub, name=nm.group(1), pas=cor[0],
                       front=(min(p[:3]) if len(p) >= 3 else min(p)), c4=p[-1],
                       chaku=(int(ch[0][0]) if ch else None),
                       ninki=(int(di[0][1]) if di else None),
                       n=(heads[0] if heads else None),
                       jockey=(jk.group(1).strip() if jk else "?"),
                       place=(pl[0][0] if pl else None)))
    return (title.group(2) if title else "?"), (dist.group(1) if dist else "?"), hs

def pick(hs, bias="前"):
    """bias='前' … 前残り日（既定）／ bias='差' … 差しが決まる日は条件を反転"""
    if bias == "前":
        A = [h for h in hs if h["front"] and h["front"] <= 3 and (h["chaku"] or 99) >= 4 and (h["ninki"] or 0) >= 6]
        B = [h for h in hs if h["front"] and h["front"] <= 3 and (h["chaku"] or 99) >= 4]
        core = [h for h in hs if h["front"] and h["front"] == 1]
    else:
        A = [h for h in hs if h["front"] and h["front"] >= 4 and (h["chaku"] or 99) >= 4 and (h["ninki"] or 0) >= 6]
        B = [h for h in hs if h["front"] and h["front"] >= 4 and (h["chaku"] or 99) >= 4]
        core = [h for h in hs if h["c4"] and h["n"] and h["c4"] > h["n"]*0.6]
    return A, B, core

def run(rid, bias="前"):
    R, dist, hs = parse(fetch(rid))
    A, B, core = pick(hs, bias)
    print(f"■ {R}  {dist}m  {len(hs)}頭   その日の馬場＝【{bias}】想定\n")
    print(f"{'番':>3} {'馬名':<14}{'騎手':<7}{'前走通過順':<14}{'着':>4}{'人気':>5}  判定")
    for h in sorted(hs, key=lambda z: (z["front"] or 99, z["chaku"] or 99)):
        tag = ""
        if h in A: tag = "★穴候補（形あり×凡走×人気薄）"
        elif h in B: tag = "○形あり×凡走"
        elif h in core: tag = "軸候補（前走ハナ）"
        print(f"{h['ub']:>3} {h['name']:<14}{h['jockey']:<7}"
              f"{(h['pas'] or '-'):<14}{(h['chaku'] or 0):>4}{(h['ninki'] or 0):>5}  {tag}")
    print("\n" + "-"*70)
    print("★穴候補: " + ("／".join(f"{h['ub']}{h['name']}" for h in A) if A else "なし"))
    print("軸候補（前走で3角までに先頭）: " + ("／".join(f"{h['ub']}{h['name']}" for h in core) if core else "なし"))
    print("\n買い方の型：軸候補 → ★穴候補 の順で3連単。★が2頭出たら2-3着に置く。")
    return A, B, core

if __name__ == "__main__":
    rid = sys.argv[1]
    bias = "差" if ("--bias" in sys.argv and "差" in sys.argv) else "前"
    run(rid, bias)
