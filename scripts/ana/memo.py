"""南関版「次走へのメモ」── 1走ぶんの競馬内容を文章にする。

  python3 memo.py <馬名の一部>                  # 第11回大井の記録から
  python3 memo.py --card <card.json> <馬名>     # 出馬表の過去5走から
  python3 memo.py --day 1028 --R 7              # その鞍の全頭ぶん

── ★ これは「見た記録」ではない

  中央の「次走へのメモ」はトラックマンが**見て**書いている。
  装具・パドックの気配・直線の進路・手前の替え方は、**映像を見ないと書けない**。
  このツールはそこを**書かない**。埋めると嘘になる。

  書けるのは、通過順・ハロンタイム・着差・馬体重から**言い切れることだけ**。

    出せる … 枠と頭数から見た位置取りの難易度／1角の出方／3〜4角の押し上げ／
             直線での伸び（上がり − レース後3F）／流れの前傾後傾／
             レース全体がどれだけ落ちたか／着差／馬体重と増減
    出せない … 装具・気配・周回の様子・直線の進路・手前・不利の有無

  そのかわり、人の目には出せないものを足してある ──
  **そのレース自体が何秒落ちたか**と、**その中でこの馬がどれだけ耐えたか**。

── 言葉の対応（勝手な形容をしないための対応表）

  位置（1角の相対位置 ＝ (通過−1)/(頭数−1)）
    0.15未満 ハナ ／ 〜0.35 好位 ／ 〜0.60 中団の前 ／ 〜0.80 中団の後ろ ／ それ以上 後方

  3〜4角（3角の順位 − 4角の順位）
    +2以上 押し上げて ／ −2以下 置かれて ／ その間 位置のまま

  直線（その馬の上がり3F − レースの後3F）
    −0.5以下 渋太く伸びて ／ 〜0.0 脚色を保って ／ +0.5以上 直線で止まって

  流れ（レースの前3F − 後3F）
    −2.5以下 前半が速い流れ ／ +0.5以上 遅い流れ

  着差
    1着で0.5秒以上 完勝 ／ 1着で0.3秒未満 辛勝 ／ 2〜3着で0.3秒以内 惜敗 ／ 2.0秒以上 大敗
"""
import sys, json, os, re, glob, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
_LAP = None


def lapidx():
    """harvest/*_res.json から 日付(MMDD) → その日の全鞍 を作る"""
    global _LAP
    if _LAP is not None:
        return _LAP
    _LAP = {}
    for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json")):
        m = re.search(r"(\d{4})_res", os.path.basename(f))
        if not m:
            continue
        try:
            D = json.load(open(f))
        except Exception:
            continue
        _LAP.setdefault(m.group(1), {}).update(D)
    return _LAP


def race_of(mmdd, name):
    D = lapidx().get(mmdd)
    if not D:
        return None
    for k in D:
        v = D[k]
        if any(r["name"] == name for r in v["rows"]):
            return v
    return None


def pos_word(c, n):
    """★ 相対位置だけで見ると16頭立ての3番手が「ハナ」になる。頭数と絶対位置の両方を見る"""
    if not c or n < 2:
        return None
    r = (c - 1) / (n - 1)
    if c == 1:
        return "ハナ"
    if c <= 3 and r < 0.30:
        return "先行"
    return "中団の前" if r < 0.50 else "中団" if r < 0.75 else "後方"


def waku_word(ub, n):
    if not ub or n < 2:
        return ""
    r = (ub - 1) / (n - 1)
    return "大外枠から" if r >= 0.80 else "外枠から" if r >= 0.62 else \
           "内枠から" if r <= 0.20 else ""


def write(p, name, venue=None):
    """1走ぶんのメモ本文をつくる"""
    n = p["n"]
    ts = p.get("tsuka") or []
    c1, c4 = p.get("c1"), p.get("c4")
    s = []
    # 馬体
    if p.get("w"):
        dw = p.get("dw")
        if dw and abs(int(dw)) >= 10:
            s.append("%skg（%s）と%s" % (p["w"], dw, "大きく増えて" if int(dw) > 0 else "大きく絞れて"))
    # 出方と位置
    wk = waku_word(p.get("waku") or p.get("ub"), n)
    pw = pos_word(c1, n)
    if pw:
        s.append("%s%s" % (wk, {"ハナ": "ハナを主張", "先行": "先行して",
                                "中団の前": "中団の前へ", "中団": "中団で",
                                "後方": "後方から"}[pw]))
    # 3〜4角
    if len(ts) >= 2:
        g34 = ts[-2] - ts[-1]
        g14 = ts[0] - ts[-1]            # 道中ぜんぶでどれだけ動いたか
        if abs(g14) >= 2 and abs(g14) > abs(g34):
            s.append("道中で%dつ押し上げて" % g14 if g14 > 0 else "道中で%dつ下げて" % (-g14))
        elif g34 >= 2:
            s.append("3〜4角で%dつ押し上げて" % g34)
        elif g34 <= -2:
            s.append("3〜4角で%dつ置かれて" % (-g34))
        else:
            s.append("位置のまま4角へ")
    # 直線（レースの後3Fと比べる）
    rr = None
    if venue == "大井":
        rr = race_of(p["date"][3:5] + p["date"][6:8], name)
    extra = ""
    if rr and rr.get("lap") and p.get("agari"):
        L = rr["lap"]; LL = L[1:] if L[0] < 10 else L
        r_ag = sum(LL[-3:]); r_f3 = sum(LL[:3])
        da = p["agari"] - r_ag
        s.append("直線は渋太く伸びて" if da <= -0.5 else
                 "直線は脚色を保って" if da <= 0.0 else
                 "直線で止まって" if da >= 0.5 else "直線は並の脚で")
        pace = r_f3 - r_ag
        extra = "（流れは%s／レースは最速%.1f→最終%.1f で%+.1f秒落ちた。この馬の上がり%.1f はレース%.1f に対し%+.1f）" % (
            "前半が速い" if pace <= -2.5 else "遅い" if pace >= 0.5 else "並",
            min(LL), LL[-1], LL[-1] - min(LL), p["agari"], r_ag, da)
    elif p.get("agari"):
        s.append("上がり%.1f" % p["agari"])
    # 結末
    ch, sa = p["chaku"], p.get("sa") or 0
    s.append("%d着" % ch + (
        "。完勝" if ch == 1 and sa >= 0.5 else
        "。辛勝" if ch == 1 and sa < 0.2 else
        "。惜敗" if 2 <= ch <= 3 and sa <= 0.3 else
        "。大敗" if sa >= 2.0 else ""))
    return "。".join(x for x in s if x).replace("。。", "。"), extra


def show(name, past, head=None):
    print("\n■ %s" % name)
    if head:
        print("   %s" % head)
    for p in past:
        body, extra = write(p, name, p.get("venue"))
        print("\n   %s %s %s %dm %d頭 %d番人気" % (
            p["date"], p.get("venue", "?"), p["baba"], p["dist"], p["n"], p["nk"]))
        print("     %s。" % body)
        if extra:
            print("     %s" % extra)
    print("\n   ※ 装具・パドックの気配・直線の進路・手前は見ていないので書いていない。")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--card" in a:
        D = json.load(open(a[a.index("--card") + 1]))
        q = [x for x in a if not x.startswith("--") and not x.endswith(".json")][0]
        for k in sorted(D, key=int):
            v = D[k]
            for h in v["horses"]:
                if q in h["name"]:
                    show(h["name"], h.get("past") or [],
                         "本日 %dR ダ%dm %d頭 %d番" % (v["R"], v["dist"], len(v["horses"]), h["ub"]))
        return
    H = json.load(open(os.path.join(HERE, "ooi11_kaisai.json")))
    if "--day" in a:
        day = a[a.index("--day") + 1]
        R = int(a[a.index("--R") + 1]) if "--R" in a else None
        for nm, e in sorted(H.items()):
            for r in e["kaisai"]:
                if r["date"][5:7] + r["date"][8:10] != day:
                    continue
                if R and r["R"] != R:
                    continue
                p = dict(r); p["venue"] = "大井"; p["sa"] = 0
                p["tsuka"] = [x for x in (r.get("c1"), r.get("c4")) if x]
                body, extra = write(p, nm, "大井")
                print("\n %2dR %2d番 %s（%s人気）" % (r["R"], r["ub"], nm, r["nk"]))
                print("   %s。" % body)
                if extra:
                    print("   %s" % extra)
        return
    q = a[0]
    hit = [e for nm, e in H.items() if q in nm]
    if not hit:
        print("%s に当たる馬がいません" % q); return
    for e in sorted(hit, key=lambda e: e["name"]):
        r = e["kaisai"][0]
        show(e["name"], e["past5"],
             "今開催 %s %dR ダ%dm %s %d頭 → %s着 %s人気" % (
                 r["date"][5:], r["R"], r["dist"], r["baba"], r["n"], r["chaku"], r["nk"]))


if __name__ == "__main__":
    main()
