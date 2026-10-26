"""条件が下りてきた馬を探す ── 「能力が上がった馬」ではなく「同じ脚で足りる馬」。

  python3 orite.py <card.json> [R...] [--min 2] [--date YYYYMMDD]

card.json は syutuba.py が吐く楽天の出馬表（過去5走・枠つき）。

── 考え方（2026-10-26 大井・全鞍不良で出た形）

  9R をエムオーナイナー（10番人気）が勝った。上がりは39.8。
  ところがこの馬が1200mで8〜10番手から使っていた上がりは 38.4・39.0・39.9・39.8。
  **普段どおりの数字で足りている。この馬は何も速くなっていない。**

  変わったのはレースのほう。

    ① 距離が1200m→1400mに延びて、位置を取る時間ができた
    ② 間隔が42日あいて、反応が戻っていた
    ③ 不良で全体が遅くなり、普段の上がりで足りた

  同じ日の7Rも同じ形。ノーブルプライム（6番人気2着）は1600m専門で
  通過12-12-12-12が並ぶ馬だったが、1200mに400m短縮して6番手まで前進し、
  上がり39.0は全12頭で最速だった。ゴールデンルチル（9番人気3着）は間隔96日。

  **探すのは「伸びそうな馬」ではなく「今日と同じ脚で足りる鞍」。**

── 見る3つ

  ① 普段は後ろ    過去走の4角が平均5番手以降
  ② 距離が変わる  ±200m以上。延長なら位置を取る時間、短縮なら相対的に前へ
  ③ 間隔があいた  30日以上

  3つそろうほど強い。2つで候補、3つで本命級に扱う。

── ★ 一緒に見ること（この3つだけでは足りない）

  **馬場。** この形は全体が遅くなる日に出る。良に回復したら前提が崩れる。
  2026-10-26 は後3Fが前開催より 1600mで+1.2秒・1800mで+1.3秒 遅かった。

  **馬体重。** 押して行く体力が要る。同じ日の3着内7頭のうち3頭が
  レース平均より +22〜+73kg だった。絞って出てきたら下げる。

  **オッズ。** 前走の着順で「人気が落ちる」と見込んで拾う形なので、
  発走30分前に取り直して、本当に人気薄かを確かめる。
"""
import sys, json, datetime as dt, statistics as st, unicodedata as ud


def w(s, n):
    l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    return s + " " * max(0, n - l)


def prof(h, dist, today, mean_w):
    past = h.get("past") or []
    if not past:
        return None
    c4 = [q["c4"] for q in past if q.get("c4")]
    if not c4:
        return None
    p = past[0]
    try:
        gap = (today - dt.datetime.strptime(p["date"], "%y.%m.%d").date()).days
    except Exception:
        gap = None
    ag = [q["agari"] for q in past if q.get("agari")]
    return {
        "av": st.mean(c4), "best": min(c4), "c4": c4,
        "dd": dist - p["dist"], "gap": gap,
        "agari": st.mean(ag) if ag else None,
        "w": p.get("w"), "wd": (p["w"] - mean_w) if (p.get("w") and mean_w) else None,
        "pchaku": p["chaku"], "pnk": p["nk"], "pdist": p["dist"],
    }


def run(D, only=None, minhit=2, today=None):
    today = today or dt.date.today()
    for k in sorted(D, key=int):
        v = D[k]
        if only and v["R"] not in only:
            continue
        d = v["dist"] or 0
        ws = [h["past"][0]["w"] for h in v["horses"] if h.get("past")]
        mw = st.mean(ws) if len(ws) >= 5 else None
        rows = []
        for h in v["horses"]:
            z = prof(h, d, today, mw)
            if not z:
                continue
            hit = [z["av"] >= 5.0, abs(z["dd"]) >= 200, (z["gap"] or 0) >= 30]
            if sum(hit) < minhit:
                continue
            rows.append((sum(hit), h, z))
        print("\n%2dR ダ%dm %2d頭  %s" % (
            v["R"], d, len(v["horses"]), (v.get("cls") or "")[:22]))
        if not rows:
            print("    該当なし")
            continue
        for n, h, z in sorted(rows, key=lambda r: (-r[0], -r[2]["av"])):
            tag = []
            if z["av"] >= 5.0:
                tag.append("普段4角%.1f番手" % z["av"])
            if abs(z["dd"]) >= 200:
                tag.append("距離%+dm" % z["dd"])
            if (z["gap"] or 0) >= 30:
                tag.append("間隔%d日" % z["gap"])
            print("  %d/3 %2d %s %s枠  %s" % (
                n, h["ub"], w(h["name"], 16), h.get("waku") or "?", " / ".join(tag)))
            print("        普段の上がり%s  体重%s%s  前走%d人気%d着  過去4角%s" % (
                ("%.1f" % z["agari"]) if z["agari"] else "?",
                z["w"] or "?",
                ("（平均%+.0f）" % z["wd"]) if z["wd"] is not None else "",
                z["pnk"], z["pchaku"], z["c4"]))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    D = json.load(open(a[0]))
    mn = int(a[a.index("--min") + 1]) if "--min" in a else 2
    today = None
    if "--date" in a:
        s = a[a.index("--date") + 1]
        today = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    only = [int(x) for x in a[1:] if x.isdigit()]
    print(__doc__.split("──")[0].strip())
    print("  ①普段は後ろ（4角平均5番手以降） ②距離が±200m以上変わる ③間隔30日以上"
          "　／ %d つ以上で表示" % mn)
    run(D, only or None, mn, today)


if __name__ == "__main__":
    main()
