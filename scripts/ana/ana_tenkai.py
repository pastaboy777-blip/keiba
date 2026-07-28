#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""荒れたレースの穴だけを拾うツール（展開一本）。

考え方:
  「前走で前に行けたのに凡走した馬」＝ 展開の形は持っているのに市場が評価していない馬。
  前走で好走していれば人気になる。凡走していれば人気は落ちる。
  そこに その日の馬場（前残りか差しか）を掛ける。

使い方:
  python3 scripts/ana/ana_tenkai.py <楽天出馬表RACEID> [--bias 前|差]
  例) python3 scripts/ana/ana_tenkai.py 202607282115060210

判定（川崎 7/6-7/10の60R ＋ 7/28の10R ＝ 669頭で再フィット）:
  母集団は「今回6番人気以下」＝325頭・3着内12.3%。

  ★A（推奨）前走1-3着          33頭 / 3着内27.3% / 倍率2.20
       内訳 前走1-3着×後(4番手以降) 17頭 29.4% 2.43
            前走1-3着×前(3番手以内) 16頭 25.0% 2.07
   B  前走6着以下×前(3番手以内)     48頭 / 16.7% / 1.38  ←旧★。上位の6割
   C  前走4-5着                56頭 / 14.3% / 1.15
   ✗  前走6着以下×後(4番手以降)   179頭 /  7.3% / 0.60  ←最も来ない

  つまり「前走で走ったのに人気が来ていない馬」が穴の本命。
  前走の位置取りより前走の着順のほうが効く。

  ※「人気」は【今回の人気】。前走の人気ではない。
    当日オッズは出馬表の <span class="rate">13.8（8人気）</span> から取る。

  7/28の実績：10R④(前走3着→9人気で1着・三連単96,380円)、8R⑪(前走1着→2人気で1着)を捕捉。
  ただし7R(三連単209,130円)の1着⑧は前走6着・前々走5着・前走5番手でどの型にも掛からない。
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
        tn = re.search(r"（(\d{1,2})人気）", seg)          # ★当日オッズの人気（前走人気ではない）
        pl = re.findall(r"(浦和|川崎|大井|船橋|門別|金沢|名古屋|園田|高知|佐賀|水沢|盛岡|笠松) (\d\d\.\d\d\.\d\d)", seg)
        if not cor: 
            hs.append(dict(ub=ub, name=nm.group(1), pas=None, front=None, c4=None,
                           chaku=None, ninki=None, n=None, jockey=(jk.group(1).strip() if jk else "?"),
                           place=None, tninki=(int(tn.group(1)) if tn else None))); continue
        p = [int(v) for v in cor[0].split("-")]
        hs.append(dict(ub=ub, name=nm.group(1), pas=cor[0],
                       front=(min(p[:3]) if len(p) >= 3 else min(p)), c4=p[-1],
                       chaku=(int(ch[0][0]) if ch else None),
                       ninki=(int(di[0][1]) if di else None),
                       n=(heads[0] if heads else None),
                       jockey=(jk.group(1).strip() if jk else "?"),
                       place=(pl[0][0] if pl else None),
                       tninki=(int(tn.group(1)) if tn else None)))
    return (title.group(2) if title else "?"), (dist.group(1) if dist else "?"), hs

def pick(hs, bias="前"):
    """A=★穴候補 / B=準候補 / core=軸候補（前走ハナ）

    bias は core（誰が前に行くか）と B の向きにのみ効く。
    A は前走着順ベースなので馬場に依らない。
    """
    # ★A：前走1-3着（＝走ったのに人気が来ていない）× 今回6番人気以下  倍率2.11
    A = [h for h in hs if (h["chaku"] or 99) <= 3 and (h["tninki"] or 0) >= 6]
    # B：前走の位置は取れているが着順は伴わなかった組（旧★・倍率1.37）
    if bias == "前":
        B = [h for h in hs if h not in A and h["front"] and h["front"] <= 3 and (h["chaku"] or 99) >= 6
             and (h["tninki"] or 0) >= 6]
        core = [h for h in hs if h["front"] and h["front"] == 1]
    else:
        B = [h for h in hs if h not in A and h["front"] and h["front"] >= 4 and (h["chaku"] or 99) >= 6
             and (h["tninki"] or 0) >= 6]
        core = [h for h in hs if h["c4"] and h["n"] and h["c4"] > h["n"] * 0.6]
    return A, B, core

def run(rid, bias="前"):
    R, dist, hs = parse(fetch(rid))
    A, B, core = pick(hs, bias)
    print(f"■ {R}  {dist}m  {len(hs)}頭   その日の馬場＝【{bias}】想定\n")
    print(f"{'番':>3} {'馬名':<14}{'騎手':<7}{'前走通過順':<14}{'前着':>4}{'前人':>5}{'今人':>5}  判定")
    for h in sorted(hs, key=lambda z: (z["front"] or 99, z["chaku"] or 99)):
        tag = ""
        if h in A: tag = "★穴候補（前走1-3着 × 今回6人気以下／倍率2.11）"
        elif h in B: tag = "○前走は前に行けたが着順が伴わず（1.37）"
        elif h in core: tag = "軸候補（前走ハナ）"
        print(f"{h['ub']:>3} {h['name']:<14}{h['jockey']:<7}"
              f"{(h['pas'] or '-'):<14}{(h['chaku'] or 0):>4}{(h['ninki'] or 0):>5}{(h['tninki'] or 0):>5}  {tag}")
    print("\n" + "-"*70)
    print("★穴候補: " + ("／".join(f"{h['ub']}{h['name']}" for h in A) if A else "なし"))
    print("軸候補（前走で3角までに先頭）: " + ("／".join(f"{h['ub']}{h['name']}" for h in core) if core else "なし"))
    print("\n買い方の型：軸候補 → ★穴候補 の順で3連単。★が2頭出たら2-3着に置く。")
    return A, B, core

if __name__ == "__main__":
    rid = sys.argv[1]
    bias = "差" if ("--bias" in sys.argv and "差" in sys.argv) else "前"
    run(rid, bias)
