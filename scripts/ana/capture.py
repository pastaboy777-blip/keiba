"""ライブ通過キャプチャ ── 開催当日に結果を"実通過付き"で構造化保存。
競馬ブックの結果ページ(seiseki)の通過順は開催直後は生値だが時間が経つと****マスク。
→ 当日にフェッチして通過・上がり・着順・人気・体重をJSONLへ保存し、実データを蓄積する。
保存するのは派生した結果事実のみ(生HTML/cookieは保存しない)。冪等(rid重複はスキップ)。

使い方:
  python3 capture.py meet 2026 11 10 0720 0721 0722 0723 0724   # 年 回 場 各日MMDD...
  python3 capture.py rids 2026111001010720 ...                   # 個別rid
  python3 capture.py stat                                         # 蓄積状況
保存先: DATA(tsuka_data.jsonl)。場コード: 大井10 川崎11 船橋12 浦和13。
標準ライブラリ+monogatari。
"""
import re, os, sys, json
import monogatari as M

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tsuka_data.jsonl")

def _uncircle(s):
    return "".join(str(ord(c) - 0x2460 + 1) if 0x2460 <= ord(c) <= 0x2473 else c for c in s)

def parse_seiseki(h):
    """結果HTML -> {date,track,dist,cls,masked,rows:[{chaku,umaban,umacd,name,tsuka,agari,nk,wt}]}"""
    tt = re.search(r"<title>\s*成績\s*\|\s*(\d{4})年(\d{1,2})月(\d{1,2})日([^\d]+?)(\d+)R([^|<]*)", h)
    date = f"{tt.group(1)}-{int(tt.group(2)):02d}-{int(tt.group(3)):02d}" if tt else None
    track = tt.group(4).strip() if tt else None
    dm = re.search(r'racekyori">(\d+)', h); dist = int(dm.group(1)) if dm else None
    rows = []; any_real = False
    for m in re.finditer(r"<tr>(.*?)</tr>", h, re.S):
        body = m.group(1)
        cm = re.search(r"/db/uma/(\d+)", body)
        c = [_uncircle(re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)]
        if not cm or len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if nmi is None or nmi < 1 or not re.match(r"^\d+$", c[nmi - 1]): continue
        wi = next((i for i in range(nmi + 1, len(c)) if re.match(r"^[345]\d\d$", c[i])), None)
        nk = int(c[wi - 2]) if wi and wi >= 2 and re.match(r"^\d+$", c[wi - 2]) else None
        wt = int(c[wi]) if wi else None
        agari = None
        if wi:
            for j in range(nmi + 1, wi - 1):
                if re.match(r"^[34]\d\.\d$", c[j]): agari = float(c[j])
        # 通過: このumacdの<ul class="tuka">を本文から
        tu = re.search(r'class="tuka">(.*?)</ul>', body, re.S)
        tsuka = None
        if tu:
            digs = re.findall(r">(\d+)<", tu.group(1))
            if digs: tsuka = [int(x) for x in digs]; any_real = True
        rows.append({"chaku": int(c[0]), "umaban": int(c[nmi - 1]), "umacd": cm.group(1),
                     "name": c[nmi], "tsuka": tsuka, "agari": agari, "nk": nk, "wt": wt})
    return {"date": date, "track": track, "dist": dist, "masked": not any_real, "rows": rows}

def _seen():
    if not os.path.exists(DATA): return set()
    return {json.loads(l)["rid"] for l in open(DATA) if l.strip()}

def capture(rid, seen):
    if rid in seen: return "skip"
    fpath = os.path.join(M.ARC, f"kekka_{rid}.html")
    # 常にライブ取得(古いキャッシュのマスクを避ける)
    M._get(f"{M.BASE}/chihou/seiseki/{rid}", fpath) if not os.path.exists(fpath) else None
    h = open(fpath, encoding="utf-8", errors="replace").read()
    rec = parse_seiseki(h)
    if not rec["rows"]: return "empty"
    rec["rid"] = rid
    with open(DATA, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    seen.add(rid)
    return "masked" if rec["masked"] else "real"

def main():
    if not sys.argv[1:]:
        print(__doc__); return
    mode = sys.argv[1]
    seen = _seen()
    if mode == "stat":
        recs = [json.loads(l) for l in open(DATA)] if os.path.exists(DATA) else []
        real = sum(1 for r in recs if not r["masked"])
        print(f"蓄積: {len(recs)}レース (実通過{real} / マスク{len(recs)-real})")
        from collections import Counter
        c = Counter((r["date"], r["track"]) for r in recs)
        for (d, t), n in sorted(c.items())[-10:]: print(f"  {d} {t}: {n}R")
        return
    rids = []
    if mode == "meet":
        yy, kai, jyo = sys.argv[2], sys.argv[3], sys.argv[4]
        for nn, mmdd in enumerate(sys.argv[5:], 1):
            rids += [f"{yy}{kai}{jyo}{nn:02d}{rr:02d}{mmdd}" for rr in range(1, 13)]
    elif mode == "rids":
        rids = sys.argv[2:]
    res = {}
    for rid in rids:
        r = capture(rid, seen); res[r] = res.get(r, 0) + 1
        if r in ("real", "masked"): print(f"{r:6} {rid}", flush=True)
    print("=== 集計:", res, "===")
    if res.get("masked"): print("⚠ maskedあり=取得が遅い。通過を使うなら開催当日中に再取得を。")

if __name__ == "__main__":
    main()
