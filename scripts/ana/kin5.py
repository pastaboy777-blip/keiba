"""出走馬の近5走を1走ずつ書き出す ── FS%・流れの厳しさ(TT)・1角→4角の動き。

  python3 kin5.py <card.json>               # 全鞍・全頭
  python3 kin5.py <card.json> --R 7         # その鞍だけ
  python3 kin5.py <card.json> --cover       # 何走ぶん照合できたかだけ出す
  python3 kin5.py <card.json> <馬名>        # 1頭だけ

── 1走につき出すもの

  FS%        その馬の走破タイムと上がり3Fから。100超＝終いのほうが速い。
             距離をまたいで比べられる（比だから）。水準は kukan_base.json。
  流れ(TT)   そのレースの2〜4ハロン目。**レースの性質**で、馬の能力ではない。
             水準より速ければ「厳しい流れ」、遅ければ「ゆるい流れ」。
  動き       1角の通過順 → 4角の通過順。

── ★ 「流れ」は手元にラップのある日しか出ない

  TT はレースのハロンタイムが要る。harvest/ に取ってある日のレースだけ照合できる。
  取っていない日・取っていない場（門別・名古屋・JRA など）は **流れなし** と出す。
  埋めない。埋めると、ないものを有るように見せることになる。

── ★ 「厳しい流れで下げた」は切る材料になる（4場1,300鞍で見た形）

  厳しい流れ × 押し上げ   3着内 39.9%
  厳しい流れ × 下げた     3着内  0.6%   ← 1着は0
  ゆるい流れ × 下げた     3着内  6.3%

  **同じ「下げた」が流れ次第で10倍ちがう。**だから前走を「下げて負けた」と
  読むときは、その日の流れを見ないと意味が反転する。
"""
import sys, json, os, glob, re, statistics as st, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kukan import race_fs, horse_fs, sui, VEN, laps

REV = {v: k for k, v in VEN.items()}
_IDX = None


def wd(s):
    return sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)


def w(s, n):
    while wd(s) > n:
        s = s[:-1]
    return s + " " * max(0, n - wd(s))


def index():
    """harvest/*_res.json を (場, MMDD) → 鞍 で引けるようにする"""
    global _IDX
    if _IDX is not None:
        return _IDX
    _IDX = {}
    for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json")):
        b = os.path.basename(f)
        m = re.match(r"([a-zA-Z]+?)L?(\d{4})(?:res)?_res\.json$", b)
        if not m:
            m = re.match(r"([a-zA-Z]+?)L?(\d{4})\w*_res\.json$", b)
        if not m:
            continue
        ven = VEN.get(m.group(1)[:3])
        if not ven:
            continue
        try:
            D = json.load(open(f))
        except Exception:
            continue
        key = (ven, m.group(2))
        _IDX.setdefault(key, {}).update(D)
    return _IDX


def find_race(p, name):
    """その過去走が手元のラップのどの鞍か。日・場・距離が合って、その馬がいる鞍"""
    mmdd = p["date"][3:5] + p["date"][6:8]
    D = index().get((p["venue"], mmdd))
    if not D:
        return None
    for k in D:
        v = D[k]
        if v.get("dist") != p["dist"]:
            continue
        if any(r.get("name") == name for r in v.get("rows") or []):
            return v
    return None


def run_line(p, name):
    """1走ぶん。(見出し行, 中身行) を返す"""
    fs = horse_fs(p.get("t"), p.get("agari"), p["dist"])
    c, _ = sui(p["venue"], p["dist"], p["baba"])
    fsd = (fs - c["fs"]) if (fs is not None and c) else None
    head = "%s %s %s%4dm %2d頭 %2d人 %2d着 %+.1f" % (
        p["date"], p["venue"], p["baba"], p["dist"], p["n"], p["nk"],
        p["chaku"], p.get("sa") or 0)
    # 動き
    c1, c4 = p.get("c1"), p.get("c4")
    if c1 and c4:
        g = c1 - c4
        mv = "1角%-2d→4角%-2d（%s）" % (c1, c4, "%+d" % g if g else "不動")
    else:
        mv = "通過順なし"
    # 流れ
    rr = find_race(p, name)
    nag = "流れなし"
    if rr:
        _, tt = race_fs(rr)
        if tt is not None:
            if c:
                d = tt - c["tt"]
                nag = "TT %.1f（水準%+.1f ＝ %s）" % (
                    tt, d, "厳しい流れ" if d <= -0.3 else "ゆるい流れ" if d >= 0.3 else "並の流れ")
            else:
                nag = "TT %.1f（水準なし）" % tt
    f = "FS%% %5.1f%s" % (fs, "（水準%+.1f）" % fsd if fsd is not None else "（水準なし）") \
        if fs is not None else "FS%% 測れない"
    return head, "%s  %s  %s" % (f, mv, nag)


def horse(h, v, out):
    out.append("  %2d番%s枠 %s" % (h["ub"], h.get("waku"), h["name"]))
    past = h.get("past") or []
    if not past:
        out.append("       近走なし（履歴が引けない馬。弱いという意味ではない）")
        return
    for p in past:
        a, b = run_line(p, h["name"])
        out.append("       %s" % a)
        out.append("         %s" % b)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    f = [x for x in a if x.endswith(".json")][0]
    D = json.load(open(f))
    R = int(a[a.index("--R") + 1]) if "--R" in a else None
    q = [x for x in a if not x.startswith("--") and not x.endswith(".json") and not x.isdigit()]
    q = q[0] if q else None
    if "--cover" in a:
        tot = ts = tn = tf = 0
        for k in D:
            for h in D[k]["horses"]:
                for p in (h.get("past") or []):
                    tot += 1
                    if p.get("c1") and p.get("c4"):
                        ts += 1
                    if find_race(p, h["name"]):
                        tn += 1
                    if horse_fs(p.get("t"), p.get("agari"), p["dist"]) is not None:
                        tf += 1
        print("近5走 … %d走" % tot)
        print("  通過順がある     %d走（%.0f%%）" % (ts, 100 * ts / tot))
        print("  FS%%が出る        %d走（%.0f%%）" % (tf, 100 * tf / tot))
        print("  流れ(TT)が出る   %d走（%.0f%%）" % (tn, 100 * tn / tot))
        return
    out = []
    for k in sorted(D, key=int):
        v = D[k]
        if R and v["R"] != R:
            continue
        hs = [h for h in v["horses"] if q is None or q in h["name"]]
        if not hs:
            continue
        out.append("\n%s" % ("=" * 78))
        out.append("%2dR %s ダ%dm %d頭  %s" % (
            v["R"], v.get("start") or "", v["dist"], len(v["horses"]), (v.get("cls") or "")[:24]))
        out.append("=" * 78)
        for h in hs:
            horse(h, v, out)
    print("\n".join(out))


if __name__ == "__main__":
    main()
