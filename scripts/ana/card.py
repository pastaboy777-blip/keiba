"""印を打つ ── 過去走・調教・馬体重・枠・血統を1本にまとめた版。

  python3 card.py <card.json> <cyokyo.json> [ped.json] [--waku in|out|none] [R...]
  python3 card.py ... --why 5        # その鞍の内訳を全部出す

  card.json   … card23.py が吐く楽天の出馬表（過去5走・馬体重・枠つき）
  cyokyo.json … cyokyo.py の parse 結果を鞍ごとに並べたもの
  ped.json    … kettou.py の parse 結果を鞍ごとに並べたもの（任意）

── 何を見るか（CLAUDE.md「買う馬リストの組み方」＋ 10/23 の反省）

  ① 上がり   今日と同じ距離帯だけ。場×距離の中央値との差で見る（ルール2）
  ② 位置     中団前め（相対0.30〜0.55）を最上位。逃げ切り型は残すが上には置かない
  ③ gain     1角→4角でいくつ前へ出られるか
  ④ 枠       その日の馬場傾向。--waku in で内、out で外を加点
  ⑤ 調教     その調教場の3F中央値との差（★10/23から追加）
  ⑥ 馬体重   その馬が3着内に来たときの体重帯との差（★10/23から追加）
  ⑦ 血統     母系3代以内にサンデーサイレンスがいるか（★10/24から追加）

── ⑦を入れた理由（10/23 浦和の成立11鞍・127頭を数えた結果）

  母父父がSS   36頭  6勝(16.7%)  3着内38.9%  平均人気6.0
  母父がSS      5頭  1勝(20.0%)  3着内40.0%  平均人気6.4
  いない       86頭  4勝( 4.7%)  3着内19.8%  平均人気6.5

  3倍以上ちがうのに平均人気はほぼ同じ。オッズには入っていない。
  一方、父系（ストームキャット系／エーピーインディ系／キングマンボ系…）は
  どの系統も勝率6〜13%に収まって **分かれなかった**。
  11R単体を読んだときは「父系に米国ダートの血があるか」で分かれたように
  見えたが、11鞍に広げると父系は効かず、効いていたのは母系のサンデーだった。
  1鞍の読み解きを一般化してはいけない、という実例。

  ただしこれも **1日・11鞍・127頭** の話。母父父SSは36頭で6勝しかない。
  点は控えめ（+2）にしてある。

── 10/23 で外した2つを、ここで潰している

  **履歴が引けない馬を最下位に落とさない。**
  CLAUDE.md ルール6で「切らない」としているのに、点が付かないせいで
  実質いちばん下に沈んでいた。10/23は8R⑨レドゥローズ(2人気)と
  12R⑦キタイノホシ(3人気)が **どちらも勝った**。市場は評価していて、
  こちらだけが評価できていなかった。
  → 過去走が引けない馬には「その鞍の中央値」を与え、そのうえで調教の点を足す。

  **調教でいちばん動いた馬を印に反映する。**
  10/23の6Rは⑩アルディバの追い切りが全140頭で最速（浦和3F38.2・
  その調教場の平均より3.1秒速い）で、こちらも「▲から○に上げるのが筋」と
  書いていたのに▲のままにして、その馬が勝った。言語化できていたのに
  点数に入っていなかった。→ 調教を項目として入れた。
"""
import sys, os, json, importlib.util, statistics as st

# kettou.py を隣から読む。python3 -I だとスクリプトのディレクトリが
# sys.path に入らないので import では取れない
_kt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kettou.py")
_spec = importlib.util.spec_from_file_location("kettou", _kt_path)
kettou = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kettou)

MK = ["◎", "○", "▲", "△", "△"]
FORCE, DROP = {}, {}          # {R: {順位: 馬番}} / {R: [馬番]}


# ────────────────────────── 過去走

def band(runs, d):
    if d <= 1000:
        return [r for r in runs if r["dist"] <= 1000]
    return [r for r in runs if abs(r["dist"] - d) <= 200]


def medians(D):
    """出馬表に載る過去走ぜんぶから、場×距離の上がりの中央値を作る"""
    pool = {}
    for v in D.values():
        for h in v["horses"]:
            for r in h["past"]:
                pool.setdefault((r["venue"], r["dist"]), []).append(r["agari"])
    return {k: st.median(v) for k, v in pool.items() if len(v) >= 4}


def prof(h, d, MED):
    runs = h["past"]
    if not runs:
        return None
    b = band(runs, d)
    use = b or runs
    z = {"xband": not b}
    e = [r["agari"] - MED[(r["venue"], r["dist"])]
         for r in b if (r["venue"], r["dist"]) in MED]
    z["edge"] = round(sum(e) / len(e), 2) if e else None
    z["bedge"] = round(min(e), 2) if e else None
    pr = [(r["c4"] - 1) / max(1, r["n"] - 1) for r in use if r["c4"]]
    z["prel"] = round(sum(pr) / len(pr), 3) if pr else None
    g = [r["c1"] - r["c4"] for r in use if r["c1"] and r["c4"]]
    z["gain"] = round(sum(g) / len(g), 2) if g else None
    z["inrate"] = round(sum(1 for r in use if r["chaku"] <= 3) / len(use), 2)
    z["frontwin"] = sum(1 for r in use if r["c4"] and r["c4"] <= 3 and r["chaku"] <= 3)
    p = runs[0]
    z["pchaku"], z["psa"], z["pdist"], z["pven"] = (
        p["chaku"], p["sa"], p["dist"], p["venue"])
    z["pgain"] = (p["c1"] - p["c4"]) if (p["c1"] and p["c4"]) else None
    # 馬体重（好走帯との差）
    ws = [r["w"] for r in runs if r.get("w")]
    if ws:
        good = [r["w"] for r in runs if r.get("w") and r["chaku"] <= 3]
        z["wband"] = round(st.mean(good) if good else st.mean(ws), 1)
        z["pw"] = runs[0].get("w")
        z["wd"] = round(z["pw"] - z["wband"], 1) if z["pw"] else None
        z["wrange"] = max(ws) - min(ws)
        z["ngood"] = len(good)
    else:
        z["wband"] = z["pw"] = z["wd"] = None
        z["wrange"], z["ngood"] = 0, 0
    return z


# ────────────────────────── 調教

def cy_med(CY):
    pool = {}
    for v in CY.values():
        for zz in v:
            for r in zz["runs"]:
                t = fnum(r["times"].get("3F"))
                if t:
                    pool.setdefault(r["course"], []).append(t)
    return {k: st.median(v) for k, v in pool.items() if len(v) >= 5}


def fnum(v):
    try:
        return float(v)
    except Exception:
        return None


def cy_prof(z, CMED):
    if z is None:
        return None
    ds = [fnum(r["times"].get("3F")) - CMED[r["course"]]
          for r in z["runs"]
          if fnum(r["times"].get("3F")) and r["course"] in CMED]
    return {"best": round(min(ds), 2) if ds else None,
            "n": z["nrun"], "ya": z["ya"], "tanpyo": z["tanpyo"],
            "gap11": z["gap11"]}


# ────────────────────────── 点をつける

def score(z, waku, d, wk):
    s = 0
    e = z["edge"]
    if e is not None:
        if e <= -0.8: s += 5
        elif e <= -0.4: s += 4
        elif e <= 0.0: s += 3
        elif e <= 0.4: s += 1
        elif e >= 1.0: s -= 2
    b = z["bedge"]
    if b is not None:
        if b <= -1.2: s += 2
        elif b <= -0.6: s += 1
    if z["xband"]:
        s -= 1
    ir = z["inrate"]
    if ir >= 0.5: s += 3
    elif ir >= 0.33: s += 2
    elif ir == 0: s -= 2
    if z["frontwin"] >= 2: s += 2
    g = z["gain"]
    if g is not None:
        if g >= 2: s += 3
        elif g >= 1: s += 2
        elif g <= -2.5: s -= 3
        elif g <= -1: s -= 1
    p = z["prel"]
    if p is not None:
        if p < 0.15: s += 1
        elif p < 0.30: s += 2
        elif p < 0.55: s += 3
        elif p < 0.70: s += 0
        else: s -= 3
        if z["xband"]: s -= 1
        # ★ 後ろすぎる馬でも、上がりが毎回平均以下で道中に上げているなら
        #   減点しない（10/23 10R ④ゴールドソニックの形）
        if p >= 0.55 and (e is not None and e <= -0.3) and (g or 0) >= 0.5:
            s += 3
    pc = z["pchaku"]
    if pc and 2 <= pc <= 6: s += 1
    s += waku_pt(wk, d, waku)
    s += weight_pt(z)
    return s


def waku_pt(wk, d, mode):
    if not wk or mode == "none":
        return 0
    if mode == "in":
        return 2 if wk <= 3 else (-1 if wk >= 7 else 0)
    if mode == "out":
        return 2 if wk >= 7 else (-1 if wk <= 2 else 0)
    return 0


def weight_pt(z):
    """好走帯から離れていたら割り引く。体重がほとんど動かない馬では見ない"""
    if not z["ngood"] or z["wrange"] < 10 or z["wd"] is None:
        return 0
    if z["wd"] >= 10:
        return -2          # 大きく太め残り
    if z["wd"] >= 6:
        return -1
    if z["wd"] <= -10:
        return -2          # 細すぎ
    if z["wd"] <= -6:
        return -1
    return 0


def cy_pt(c):
    """調教。その調教場の3F中央値との差で見る"""
    if c is None:
        return 0, ""
    s, w = 0, []
    if c["n"] == 0:
        return -1, "追い切りの時計なし"
    if c["best"] is not None:
        if c["best"] <= -2.0: s += 4; w.append("3F %+.1f秒" % c["best"])
        elif c["best"] <= -1.2: s += 3; w.append("3F %+.1f秒" % c["best"])
        elif c["best"] <= -0.6: s += 2; w.append("3F %+.1f秒" % c["best"])
        elif c["best"] >= 0.8: s -= 1; w.append("3F %+.1f秒" % c["best"])
    if c["ya"] and c["ya"] != "→":
        s += 2; w.append("矢印" + c["ya"])
    if c["n"] == 1:
        s -= 1; w.append("1本だけ")
    return s, "・".join(w)


# ────────────────────────── 本体

def ped_pt(ped):
    """血統の点。浦和・第7回（10/19〜23）の56鞍628頭で数えた結果に合わせてある。

       父は他系統 × 母系にサンデー   214頭 12.1%勝 31.3%複  平均人気6.3
       父は他系統 × サンデー無し     242頭  8.3%勝 24.8%複  平均人気6.1
       父サンデー系 × 母系にもSS      15頭  6.7%勝 26.7%複  平均人気6.5
       父サンデー系のみ             157頭  5.7%勝 23.6%複  平均人気6.2

    勝率が2倍ちがうのに平均人気は4群とも6.1〜6.5でほぼ同じ。
    白井寿昭元調教師の言う「掛け合わせ」の形で、父で他系統のパワーを入れ、
    母系からサンデーの切れを取る。父にも母にもサンデーだと沈む。

    ただし 1開催・浦和だけ の数字。しかも card.py に入れても印は改善しなかった
    （母系SSの馬は上がりが0.36秒速く、血統の効果はすでに上がりの点に入っている）。
    点は小さくしてある。詳細は notes/live/ketto_urawa.md
    """
    if not ped:
        return 0, ""
    sire_ss = kettou.sire_line(ped) == "サンデー系"
    hss = kettou.haha_ss(ped)
    if sire_ss:
        return -2, "父サンデー系"
    if hss:
        return 2, hss + "SS"
    return 0, ""


def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    D = json.load(open(sys.argv[1]))
    CY = json.load(open(sys.argv[2]))
    args = sys.argv[3:]
    PED = {}
    if args and args[0].endswith(".json"):
        PED = json.load(open(args[0])); args = args[1:]
    waku = "none"
    if "--waku" in args:
        waku = args[args.index("--waku") + 1]
    why = int(args[args.index("--why") + 1]) if "--why" in args else None
    rs = [int(x) for x in args if x.isdigit()] or sorted(int(k) for k in D)
    if why:
        rs = [why]
    MED, CMED = medians(D), cy_med(CY)

    for R in rs:
        v = D[str(R)]; d = v["dist"]
        cyd = {z["ub"]: z for z in CY.get(str(R), [])}
        pd = PED.get(str(R), {})
        rows, base = [], []
        for h in v["horses"]:
            z = prof(h, d, MED)
            c = cy_prof(cyd.get(h["ub"]), CMED)
            cs, cw = cy_pt(c)
            pz = pd.get(str(h["ub"])) or {}
            ps, pw = ped_pt(pz.get("ped"))
            cs += ps
            cw = "・".join(x for x in (cw, pw) if x)
            if z is None:
                rows.append([h, None, None, c, cs, cw])      # 履歴なしは後で埋める
            else:
                s = score(z, waku, d, h.get("waku")) + cs
                rows.append([h, s, z, c, cs, cw]); base.append(s)
        # ★ 履歴が引けない馬は最下位に落とさず、その鞍の中央値＋調教分を与える
        mid = round(st.median(base)) if base else 0
        for r in rows:
            if r[1] is None:
                r[1] = mid + r[4]
                r[5] = ("履歴が引けません。中央値から" +
                        ("＋調教 " + r[5] if r[5] else "")).strip()
        rows = [r for r in rows if r[0]["ub"] not in DROP.get(R, [])]
        rows.sort(key=lambda r: -r[1])
        f = FORCE.get(R)
        if f:
            dd = {r[0]["ub"]: r for r in rows}
            picked = [u for u in f.values() if u in dd]
            rest = [r for r in rows if r[0]["ub"] not in picked]
            out = []
            for i in range(len(rows)):
                if i in f and f[i] in dd: out.append(dd[f[i]])
                elif rest: out.append(rest.pop(0))
            rows = out

        gap = (rows[0][1] - rows[1][1]) if len(rows) > 1 else 0
        print("=" * 104)
        print("%2dR %4dm %-16s %2d頭  枠=%s  ◎と2位の差 %+d%s" % (
            R, d, (v.get("cls") or "")[:16], len(rows), waku, gap,
            "  ★拮抗。1着を決め打ちしない（馬単は表裏）" if gap <= 1 else ""))
        for i, (h, s, z, c, cs, cw) in enumerate(rows if why else rows[:5]):
            mk = MK[i] if i < 5 else "  "
            tag = ""
            if z:
                tag = "上%s 位%s gain%s 3着内%.0f%% 体重%s" % (
                    ("%+.2f" % z["edge"]) if z["edge"] is not None else " 帯なし",
                    ("%.2f" % z["prel"]) if z["prel"] is not None else "─",
                    ("%+.1f" % z["gain"]) if z["gain"] is not None else " ─",
                    100 * z["inrate"],
                    ("%+.0f" % z["wd"]) if z["wd"] is not None else "─")
            print("  %-2s %2d %s %-13s %+3d  %s" % (
                mk, h["ub"], ("%d枠" % h["waku"]) if h.get("waku") else "  ",
                h["name"][:13], s, tag))
            if cw:
                print("        調教%+d  %s" % (cs, cw))


if __name__ == "__main__":
    main()
