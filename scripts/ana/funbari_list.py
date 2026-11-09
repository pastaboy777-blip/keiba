#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「劣化しにくさ」で全馬を並べるリスト。

考え方（2026/7/29 川崎の乾いた砂から）:
  反発が返ってこない砂では、速い上がりを使える馬ではなく【上がりが落ちない馬】が残る。
  7/29 12Rの2着⑤アマビリティは上がり41.4でメンバー最速だったが、絶対値では遅い。
  誰も切れていない中で落ち幅が最小だっただけ。455kg・467kgのワンツーも
  「軽いから沈まない＝落ち幅が小さい」で説明がつく。
  → 見るべきは「上がり最速」ではなく【上がりのブレ幅】と【実際に踏ん張った記録】。

出す材料（推測を入れず、馬柱にある事実だけ）:
  ①踏ん張り実績 … 過去5走のうち「上がりがかかったレース」で3着内に来た回数
                   （距離ごとの基準上がり以上＝かかったレース、と定義）
  ②ブレ幅       … 距離差を補正した上がりの最大−最小（小さいほど劣化しにくい）
  ③馬体重       … 近走の実測（最新）
  ④脚質         … 近3走の3角までの位置

  当日「今日はパサパサだ」と判断したら、このリストの上から取る。

基準上がり（川崎84R＝2026/7/6-7/10, 7/27-7/29 の中央値）:
  900m 38.0 / 1400m 40.2 / 1500m 40.5 / 1600m 40.6 / 2000m 41.5

使い方:
  python3 scripts/ana/funbari_list.py <楽天RACEID接頭辞16桁> [レース数]
  例) python3 scripts/ana/funbari_list.py 2026073021150604
"""
import re, os, sys, subprocess, statistics as st

TMP = os.environ.get("FUNTMP", "/tmp/funbari")
os.makedirs(TMP, exist_ok=True)

BASE = {900: 38.0, 1400: 40.2, 1500: 40.5, 1600: 40.6, 2000: 41.5}

def base_of(d):
    if d in BASE: return BASE[d]
    k = min(BASE, key=lambda z: abs(z - d))
    return BASE[k]

def fetch(pre, RR):
    fp = f"{TMP}/{pre}{RR:02d}.html"
    if not (os.path.exists(fp) and os.path.getsize(fp) > 50000):
        subprocess.run(["curl", "-s", "-L", "--max-time", "25",
                        f"https://keiba.rakuten.co.jp/race_card/list/RACEID/{pre}{RR:02d}",
                        "-o", fp], check=False)
    return open(fp, encoding="utf-8", errors="replace").read()

def parse(html):
    x = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    x = re.sub(r"<[^>]+>", "|", x); x = re.sub(r"[ 　]+", " ", x); x = re.sub(r"\|{3,}", "||", x)
    marks = [m.start() for m in re.finditer(r"\|◎\|", x)]
    dist = re.search(r"(\d{3,4})m成績", html)
    hs = []
    for k, pos in enumerate(marks):
        pre = x[max(0, pos-90):pos]; nums = re.findall(r"\|\s*(\d+)\s*\|", pre)
        ub = int(nums[-1]) if nums else k+1
        seg = re.sub(r"\s+", " ", x[pos:(marks[k+1] if k+1 < len(marks) else len(x))])
        nm = re.search(r"\|\|([ァ-ヴーヶ・]{2,16})\|\|", seg)
        if not nm: continue
        tn = re.search(r"（(\d{1,2})人気）", seg)
        jk = re.search(r"\|((?:[▲△☆★◇])?[^|]{2,6})\|\s*\|（[^）]{1,6}）\|", seg)
        # 各過去走を切り出す
        blk = [(m.start(), int(m.group(1))) for m in
               re.finditer(r"\|(\d{1,2})\| \| \|(?:良|重|稍|不)\| \|\d{1,2}頭\|", seg)]
        runs = []
        for i, (p, chaku) in enumerate(blk):
            b = seg[p:(blk[i+1][0] if i+1 < len(blk) else p+460)]
            d = re.search(r"(\d{3,4})(?:左|右|直)?ダ", b)
            ag = re.search(r"([\d.]{4}) (\d{3})k", b)
            cor = re.search(r"\|\s*(\d+(?:-\d+){2,3})\s*\|", b)
            if not (d and ag): continue
            p3 = [int(v) for v in cor.group(1).split("-")] if cor else None
            runs.append(dict(chaku=chaku, dist=int(d.group(1)), agari=float(ag.group(1)),
                             w=int(ag.group(2)),
                             front=(min(p3[:3]) if p3 and len(p3) >= 3 else None)))
        hs.append(dict(ub=ub, name=nm.group(1), tn=(int(tn.group(1)) if tn else None),
                       jk=(jk.group(1).strip() if jk else "?"), runs=runs[:5]))
    return (int(dist.group(1)) if dist else None), hs

def score(h):
    """踏ん張り実績・ブレ幅・体重・脚質を計算"""
    r = h["runs"]
    if not r:
        return dict(n=0, hard=0, hardn=0, spread=None, w=None, kyaku=None)
    dev = [x["agari"] - base_of(x["dist"]) for x in r]        # ＋なら基準よりかかった
    hardn = sum(1 for x in r if x["agari"] >= base_of(x["dist"]))
    hard = sum(1 for x in r if x["agari"] >= base_of(x["dist"]) and x["chaku"] <= 3)
    spread = (max(dev) - min(dev)) if len(dev) >= 2 else None
    fr = [x["front"] for x in r[:3] if x["front"]]
    return dict(n=len(r), hard=hard, hardn=hardn, spread=spread,
                w=r[0]["w"], kyaku=(st.median(fr) if fr else None))

def run(pre, upto=12):
    print(f"■ 踏ん張りリスト  {pre}")
    print("  並び＝①踏ん張り実績（かかったレースで3着内）が多い順 → ②上がりのブレ幅が小さい順\n")
    for RR in range(1, upto+1):
        dist, hs = parse(fetch(pre, RR))
        if not hs: continue
        rows = []
        for h in hs:
            s = score(h); h.update(s); rows.append(h)
        rows.sort(key=lambda z: (-z["hard"], z["spread"] if z["spread"] is not None else 9))
        print(f"── {RR}R ダ{dist}m {len(hs)}頭 ──")
        print(f"  {'番':>3} {'馬名':<15}{'人気':>4}{'踏ん張り':>9}{'ブレ幅':>7}{'体重':>6}{'脚質':>6}  騎手")
        for h in rows:
            hd = f"{h['hard']}/{h['hardn']}" if h["hardn"] else "0/0"
            sp = f"{h['spread']:.1f}" if h["spread"] is not None else "—"
            ky = ("逃" if h["kyaku"] and h["kyaku"] <= 1.5 else
                  "先" if h["kyaku"] and h["kyaku"] <= 3.5 else
                  "中" if h["kyaku"] and h["kyaku"] <= 6.5 else
                  "後" if h["kyaku"] else "—")
            print(f"  {h['ub']:>3} {h['name']:<15}{(h['tn'] or 0):>4}{hd:>9}{sp:>7}"
                  f"{(h['w'] or 0):>6}{ky:>6}  {h['jk']}")
        print()

if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 12)
