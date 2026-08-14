#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""実走BT値（南関版）── 走破タイムから外部要因を剥がして能力を数値化する。

考え方は BigTime の実走BT値と同じ:
  基準タイムとのズレを、馬場・斤量・年齢で正規化してから指数に直す。
  中心値55、全場・全距離で同一スケール。

南関で作るにあたって、原典から変えた点を先に書いておく（重要）:

  ① 区間は3つではなく2つ
     原典は 前3F／中間／後3F の3区間で馬場比を独立に持つ。
     だが1頭ごとに取れる区間タイムは「上がり3F」だけで、中間は公表されない。
     よって テン(距離-600m) と 上がり(600m) の2区間に落とす。
     レース単位のラップは3区間に割れるが、馬ごとに割り当てられないので使わない。

  ② 個別不利補正（原典の第2層）は入れない
     南関の成績に不利の構造化データが無い。無いものを推定で埋めると
     「補正したつもり」の分だけ誤差が増えるので、最初から持たない。

  ③ 馬場状態補正の向きは原典と逆にできない
     原典は「ダートは重・不良でBT値が高く出るので割り引く」とする。
     南関4場の実測は 良→稍重(遅い)→重(遅い)→不良(速い) のU字で、単調ではない。
     Phase 1 では馬場状態係数を当てず、日別の馬場比だけで吸収する。

  ④ 基準タイムは表引きではなく最小二乗
     場×距離×クラスの表にすると、母数が割れて基準の作れない条件が残る。
        タイム ≒ base[(場,距離)] + κ[クラス] × (距離/1000)
     とすればA2の1700mが年3レースでも全距離のA2からκが決まる。
     （baba_sa.py で1,940レース・残差SD1.00秒を確認した式をそのまま使う）

入っているもの:
    基準タイム3本（全体／テン／上がり）→ 2区間の日別馬場比 → 斤量補正
    → 年齢補正（馬齢群×月）→ スロー時の上がり寄せブレンド
    → ペースバイアス補正（日の偏り×位置、レースの流れ×位置）
    → 中心合わせ → クラス別Cap/Floor

入れなかったもの（理由つき）:
    個別不利補正        … 南関にデータが無い
    コース形態係数      … 基準タイムを場×距離×区間別に引いているので二重になる
    ハイペースのテン寄せ … テンを「走破−上がり」で作る以上、潰れた馬ほど高得点になる
    馬場状態係数        … 南関のダートはU字で、原典の単調な向きが当てはまらない

使い方:
    python3 scripts/ana/bt.py --fit                     # 係数を推定して表示
    python3 scripts/ana/bt.py 船橋 --date 2026-08-02    # その日のBT値
    python3 scripts/ana/bt.py --horse マルヒロユートピア  # 1頭の推移
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h2h
from baba_sa import grade

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bt_model.json")

CENTER = 55.0          # 中心値
BASE_CLASS = "B2"      # 中心値を当てるクラス（南関の真ん中）
DIST_FLOOR = 1.2       # 距離係数の下限。短距離でノイズが同じ倍率で増幅されるのを抑える
KIN_FRONT = 0.70       # 斤量補正の前3F配分（加速時のほうが重量が効く）

# --- Phase 2: ペース補正ブレンド ------------------------------------------
# ペース比＝実測テン ÷（テン基準×その日のテン馬場比）。1より大きければスロー。
# 南関1,710レースの実測で 中央1.0006 / SD 0.0181 だったので、1σを刻みに使う。
PACE_SIG = 0.018       # ペース比の1σ（実測値）
W_AT_1SIG = 0.25       # 1σずれたときのブレンド率
W_MAX = 0.50           # ブレンド率の上限。走破タイムを主役から降ろしすぎない
SLOW_KIN = 0.10        # スロー時の斤量追加補正（秒/kg/1000m・ブレンド率に比例）

# ★コース形態係数（テン3F係数・上がり3F係数）は入れない。
#   原典がこれを必要とするのは基準タイムの粒度が粗いため。
#   こちらは基準タイムを【場×距離ごとに、テン・上がり別々に】引いているので、
#   下り坂スタートで構造的にテンが速い分はすでに基準に入っている。
#   同じものを係数でもう一度引くと二重補正になる。

# --- Phase 3: ペースバイアス補正・Cap/Floor --------------------------------
# その日その場が前残りだったか差し有利だったかは、個々の馬の能力とは無関係。
# ただし【同じレースの着順から測ると循環する】ので、日×場の単位で測って当てる。
CAP_Q = 99.5           # クラス別の上限（パーセンタイル）
FLOOR_Q = 0.5          # クラス別の下限


# ---------------------------------------------------------------- 読み込み

def sec(t):
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)", (t or "").strip())
    return (int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10) if m else None


def parse(fn):
    """netkeiba(db)の南関レース結果を1レース分読む。"""
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)", flat)
    cond = re.search(r"(ダ|芝)(?:左|右|直)?(\d+)m.{0,80}?(良|稍重|重|不良)", flat)
    if not hd or not cond or cond.group(1) != "ダ":
        return None
    h1 = re.search(r'class="data_intro".*?<h1>(.*?)</h1>', t, re.S)
    rname = re.sub(r"<[^>]+>", "", re.sub(r"<!--.*?-->", "", h1.group(1), flags=re.S)).strip() if h1 else ""
    x = re.sub(r"[ 　]+", " ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", t)))
    lap = re.search(r"ラップ\| \|([0-9.\- ]+)\|", x)
    laps = [float(v) for v in lap.group(1).split("-")] if lap else []
    c4m = re.search(r"4コーナー\| \|([^|]+)\|", x)
    c4 = c4m.group(1).strip() if c4m else ""
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        if "/horse/" not in r:
            continue
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", z)).strip()
             for z in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(c) < 19 or not c[0].isdigit():
            continue
        sa = re.match(r"(牡|牝|セ)(\d+)", c[4])
        wt = re.match(r"(\d+)\(([+\-]?\d+)\)", c[18])
        rows.append(dict(
            chaku=int(c[0]), ub=int(c[2]) if c[2].isdigit() else None, name=c[3],
            sex=(sa.group(1) if sa else "?"), age=(int(sa.group(2)) if sa else None),
            kin=(float(c[5]) if re.match(r"^\d+(\.\d)?$", c[5]) else None),
            jockey=c[6], t=sec(c[7]), pas=c[14],
            agari=(float(c[15]) if re.match(r"^\d+\.\d$", c[15]) else None),
            odds=(float(c[16]) if re.match(r"^\d+(\.\d+)?$", c[16]) else None),
            ninki=(int(c[17]) if c[17].isdigit() else None),
            weight=(int(wt.group(1)) if wt else None), dw=(int(wt.group(2)) if wt else None)))
    if len(rows) < 4:
        return None
    y, m, d = int(hd.group(1)), int(hd.group(2)), int(hd.group(3))
    # レース単位のテン／上がり。上がりは末尾3ハロン、テンはその残り。
    ag3 = sum(laps[-3:]) if len(laps) >= 4 else None
    win = next((h for h in rows if h["chaku"] == 1 and h["t"]), None)
    return dict(date=f"{y:04d}-{m:02d}-{d:02d}", month=m, place=hd.group(4),
                rn=int(os.path.basename(fn)[-7:-5]), dist=int(cond.group(2)),
                baba=cond.group(3), rname=rname, klass=grade(rname), laps=laps,
                c4=c4, rk=rank4(c4), n=len(rows),
                ag3=ag3, ten3=(win["t"] - ag3 if win and ag3 else None),
                wt=(win["t"] if win else None), rows=rows)


def load(dfrom, dto, places=None):
    out = []
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = parse(fn)
        if not p or not (dfrom <= p["date"] <= dto):
            continue
        if places and p["place"] not in places:
            continue
        out.append(p)
    return out


def agegrp(age, month):
    """2歳・3歳・古馬。月は年齢補正のカーブに使う。"""
    if age is None:
        return "古馬"
    return "2歳" if age == 2 else ("3歳" if age == 3 else "古馬")


# ---------------------------------------------------------------- 基準タイム

def fit_par(R, key, verbose=False):
    """タイム ≒ base[(場,距離)] + κ[クラス] × (距離/1000) を最小二乗で。

    key は "wt"(全体) / "ten3"(テン) / "ag3"(上がり) のいずれか。
    良馬場だけを使う。日ごとの速さは馬場比で別に持つので、
    parは開催日をまたいだ共通の物差しでよい。
    """
    import numpy as np
    rs = [r for r in R if r["baba"] == "良" and r[key] and r["klass"]]
    if len(rs) < 30:
        return None
    gs = sorted({(r["place"], r["dist"]) for r in rs})
    ks = sorted({r["klass"] for r in rs})
    gi = {g: i for i, g in enumerate(gs)}
    ki = {k: i for i, k in enumerate(ks)}
    X = np.zeros((len(rs), len(gs) + len(ks)))
    y = np.array([r[key] for r in rs], dtype=float)
    for i, r in enumerate(rs):
        X[i, gi[(r["place"], r["dist"])]] = 1
        X[i, len(gs) + ki[r["klass"]]] = r["dist"] / 1000.0
    I = np.eye(X.shape[1]); I[:len(gs), :len(gs)] = 0      # クラス側だけ縮める
    beta = np.linalg.solve(X.T @ X + I, X.T @ y)
    resid = float(np.std(y - X @ beta))
    if verbose:
        c0 = beta[len(gs) + ki[BASE_CLASS]] if BASE_CLASS in ki else 0.0
        print(f"  {key:<5} {len(rs):>5}レース  残差SD {resid:.2f}秒")
        print("        クラス係数(秒/1000m・%sを0とした差) " % BASE_CLASS
              + " ".join(f"{k}{beta[len(gs)+ki[k]]-c0:+.2f}" for k in ks))
    return dict(gs=[list(g) for g in gs], ks=ks,
                beta=[float(v) for v in beta], resid=resid)


def par_of(P, place, dist, klass):
    if not P:
        return None
    gs = {tuple(g): i for i, g in enumerate(P["gs"])}
    ks = {k: i for i, k in enumerate(P["ks"])}
    g = gs.get((place, dist))
    k = ks.get(klass)
    if g is None or k is None:
        return None
    return P["beta"][g] + P["beta"][len(gs) + k] * (dist / 1000.0)


# ---------------------------------------------------------------- 馬場比

def basa(R, M):
    """日×場ごとに、テンと上がりの馬場比を出す。

    比 = その日の実測 ÷ 良馬場の基準。1.0より大きければ時計がかかった日。
    原典は「斤量補正後タイムが基準以下の馬」を対象に取るが、
    ここではレース単位の実測（テンはラップ、上がりは末尾3F）を使うので
    頭数にも着順にも依存しない。
    """
    by = defaultdict(list)
    for r in R:
        by[(r["date"], r["place"])].append(r)
    out = {}
    for k, rs in by.items():
        tv, av = [], []
        for r in rs:
            if not r["klass"]:
                continue
            pt = par_of(M["ten"], r["place"], r["dist"], r["klass"])
            pa = par_of(M["ag"], r["place"], r["dist"], r["klass"])
            if pt and r["ten3"]:
                tv.append(r["ten3"] / pt)
            if pa and r["ag3"]:
                av.append(r["ag3"] / pa)
        out["\t".join(k)] = [round(st.median(tv), 4) if len(tv) >= 3 else 1.0,
                             round(st.median(av), 4) if len(av) >= 3 else 1.0]
    return out


# ---------------------------------------------------------------- 斤量・年齢

def teiryo(R):
    """南関の牡馬定量にあたる基準斤量を、データ側から (馬齢群,性) の最頻値で決める。"""
    c = defaultdict(lambda: defaultdict(int))
    for r in R:
        for h in r["rows"]:
            if h["kin"] and h["age"]:
                c[(agegrp(h["age"], r["month"]), h["sex"])][h["kin"]] += 1
    return {"\t".join(k): max(v.items(), key=lambda z: z[1])[0] for k, v in c.items()}


KIN_PRIOR = 0.15       # 斤量係数の既定値（秒/kg/1000m）。データ推定が使えないときの保険


def fit_kin_age(R, M, verbose=False):
    """斤量係数と年齢補正を、馬場比まで剥がした残差から同時に推定する。

        残差(秒/1000m) ~ a * 斤量差(kg) + Σ b[馬齢群×月] + Σ c[騎手]

    ★騎手を必ず入れること。
      南関の斤量は性齢で決まる定量なので「強い馬ほど重い」という逆因果は無い。
      代わりに【見習い減量】という別の交絡がある。斤量差が負になるのはほぼ見習いで、
      見習いは腕が落ちる分だけ遅い。騎手を入れずに回すと
      「軽い＝遅い」＝「重いほど速い」と読んで係数の符号が反転する（実測 -0.105）。
      騎手ダミーで腕を吸ってから、同じ騎手の中の斤量差だけで係数を取る。

    それでも符号が負に出る場合は推定を捨てて KIN_PRIOR を使う。
    符号が物理と逆の補正を入れると、補正しないより悪くなるため。
    """
    import numpy as np
    T = teiryo(R)
    X, y = [], []
    grp = sorted({(agegrp(h["age"], r["month"]), r["month"])
                  for r in R for h in r["rows"] if h["age"]})
    jk = sorted({h["jockey"] for r in R for h in r["rows"] if h["jockey"]})
    gi = {g: i for i, g in enumerate(grp)}
    ji = {j: i for i, j in enumerate(jk)}
    B = M["basa"]
    for r in R:
        if not r["klass"]:
            continue
        p = par_of(M["all"], r["place"], r["dist"], r["klass"])
        if not p:
            continue
        tr, ar = B.get(f"{r['date']}\t{r['place']}", [1.0, 1.0])
        for h in r["rows"]:
            if not (h["t"] and h["agari"] and h["kin"] and h["age"] and h["jockey"]):
                continue
            adj = (h["t"] - h["agari"]) / tr + h["agari"] / ar     # 2区間で馬場を剥がす
            g = (agegrp(h["age"], r["month"]), r["month"])
            base = T.get(f"{g[0]}\t{h['sex']}")
            if base is None:
                continue
            row = [0.0] * (1 + len(grp) + len(jk))
            row[0] = (h["kin"] - base)
            row[1 + gi[g]] = 1.0
            row[1 + len(grp) + ji[h["jockey"]]] = 1.0
            X.append(row)
            y.append((adj - p) / (r["dist"] / 1000.0))             # 1000mあたりの秒に揃える
    if len(X) < 500:
        return None
    X = np.array(X); y = np.array(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    a = float(beta[0])
    # 妥当域を外れた推定は採らない。南関の斤量は (性齢 × 騎手) とほぼ共線で、
    # 騎手を統制すると斤量差の独立変動がほとんど残らず、係数が識別できない。
    # 実測でも -0.105（騎手なし＝符号逆）→ +0.006（騎手あり＝ほぼゼロ）と、
    # どちらも物理的にありえない値になる。無理に採らず既定値を使う。
    used, note = a, "データ推定"
    if not (0.05 <= a <= 0.40):
        used, note = KIN_PRIOR, f"推定値{a:+.3f}は妥当域外（識別できず）→既定値"
    age = {f"{g[0]}\t{g[1]}": float(beta[1 + i]) for g, i in gi.items()}
    # 年齢補正は「古馬をゼロ」に正規化する。そうしないと勝ち馬と平均馬の差や
    # 全体オフセットまで年齢の名前で吸ってしまい、2歳・3歳の実際の差が読めない。
    ov = [v for k, v in age.items() if k.startswith("古馬")]
    off = st.mean(ov) if ov else 0.0
    age = {k: v - off for k, v in age.items()}
    if verbose:
        print(f"  斤量係数 {used:+.3f} 秒/kg/1000m  （{len(y):,}走・騎手{len(jk)}人を統制／{note}）")
        print("  年齢補正（秒/1000m・古馬を0とした差／正なら古馬より遅い）")
        for gname in ("2歳", "3歳", "古馬"):
            v = [(m, age[f"{gname}\t{m}"]) for m in range(1, 13) if f"{gname}\t{m}" in age]
            if v:
                print(f"    {gname:<3}" + " ".join(f"{m}月{x:+.2f}" for m, x in v))
    return dict(kin=used, kin_raw=a, teiryo=T, age=age, offset=off)


# ---------------------------------------------------------------- BT値

def fit_blend(R, M):
    """全体／上がり／テンの残差を、同じ物差しに揃えるための平均とSD。

    3つは単位も分散も違う（上がりは常に600m、テンは距離-600m）。
    そのまま混ぜると混ぜた瞬間にスケールが壊れるので、
    先に平均0・SD1に標準化してから全体側のスケールに戻す。
    """
    A, G, T = [], [], []
    for r in R:
        pa = par_of(M["all"], r["place"], r["dist"], BASE_CLASS)
        pg = par_of(M["ag"], r["place"], r["dist"], BASE_CLASS)
        pt = par_of(M["ten"], r["place"], r["dist"], BASE_CLASS)
        if not pa:
            continue
        tr, ar = M["basa"].get(f"{r['date']}\t{r['place']}", [1.0, 1.0])
        for h in r["rows"]:
            if not (h["t"] and h["agari"]):
                continue
            ten = h["t"] - h["agari"]
            A.append((pa - (ten / tr + h["agari"] / ar)) / (r["dist"] / 1000.0))
            if pg:
                G.append((pg - h["agari"] / ar) / 0.6)
            if pt and r["dist"] > 600:
                T.append((pt - ten / tr) / ((r["dist"] - 600) / 1000.0))
    f = lambda v: [round(st.mean(v), 4), round(st.pstdev(v) or 1.0, 4)]
    return {"all": f(A), "ag": f(G), "ten": f(T)}


def fit_bias(R, M, verbose=False):
    """日×場の前残り【偏り】と、その効きを推定する。

    ★ここは一度タウトロジーで壊した。記録として残す。
      最初は「3着内馬の相対4角位置の中央値」をそのまま前残り度合いに使い、
      0.5より小さければ前有利、とした。だが実測は152開催日すべてで
      中央0.200。前にいた馬が上位に来るのはどの日でも当たり前で、
      これは日の性質ではなく着順で切ったことの言い換えでしかない。
      同じ理由で効きγも+5.0秒/1000mという桁違いの値になった。
      （「前の馬は速い」という普遍の関係を、そのまま補正量として拾っていた）

    直した測り方:
      ① 日×場の値から【全体の中央値】を引いた差だけを偏りとする。
      ② 効きは交互作用としてだけ取る。位置そのものの効き a は残す。
             残差 ~ a*(rel-0.5) + γ*偏り*(rel-0.5)
         a は「前にいる馬は実際に強い／うまい」という能力側の成分なので消さない。
         消すのは γ の項＝その日だけ余計に前が残った／差しが決まった分。
    """
    import numpy as np
    by = defaultdict(list)
    for r in R:
        if not r.get("rk") or r["n"] < 5:
            continue
        for h in r["rows"]:
            if h["chaku"] <= 3 and h["ub"] in r["rk"]:
                by[(r["date"], r["place"])].append((r["rk"][h["ub"]] - 1) / (r["n"] - 1))
    raw = {k: st.median(v) for k, v in by.items() if len(v) >= 9}
    if not raw:
        return {}, 0.0, 0.0
    g0 = st.median(raw.values())                       # 全体の水準。これが基準線
    bias = {"\t".join(k): round(v - g0, 4) for k, v in raw.items()}   # 差だけ持つ
    X, y = [], []
    for r in R:
        pa = par_of(M["all"], r["place"], r["dist"], BASE_CLASS)
        b = bias.get(f"{r['date']}\t{r['place']}")
        if not pa or b is None or not r.get("rk") or r["n"] < 5:
            continue
        pc = _pace(r, M)
        if pc is None:
            continue
        pd = (pc - 1.0) / PACE_SIG           # 正ならスロー、負ならハイ（σ単位）
        tr, ar = M["basa"].get(f"{r['date']}\t{r['place']}", [1.0, 1.0])
        for h in r["rows"]:
            if not (h["t"] and h["agari"] and h["ub"] in r["rk"]):
                continue
            rel = (r["rk"][h["ub"]] - 1) / (r["n"] - 1) - 0.5
            res = (pa - ((h["t"] - h["agari"]) / tr + h["agari"] / ar)) / (r["dist"] / 1000.0)
            X.append([rel, b * rel, pd * rel, 1.0])
            y.append(res)
    if len(X) < 500:
        return bias, 0.0, 0.0
    beta, *_ = np.linalg.lstsq(np.array(X), np.array(y), rcond=None)
    a, g, pz = float(beta[0]), float(beta[1]), float(beta[2])
    if verbose:
        v = sorted(bias.values())
        print(f"  3着内馬の相対4角位置は全体で {g0:.3f}。これを基準線にして日ごとの差を取る")
        print(f"  {len(bias)}開催日×場  前寄り{sum(1 for x in v if x < -0.05)}日"
              f" / 差し寄り{sum(1 for x in v if x > 0.05)}日  幅 {v[0]:+.2f}〜{v[-1]:+.2f}")
        print(f"  位置そのものの効き a={a:+.3f}（能力側なので消さない）")
        print(f"  日の偏り×位置 γ={g:+.3f} ／ ペース×位置 p={pz:+.3f} 秒/1000m（この2つを消す）")
    return bias, g, pz


def fit_cap(R, M, verbose=False):
    """クラス別の上限・下限。いびつな馬場やペースで膨らんだ外れ値を止める。"""
    by = defaultdict(list)
    for r in R:
        for h in r["rows"]:
            b = bt_of(r, h, M)
            if b:
                by[r["klass"] or "?"].append(b[0])
    cap = {}
    for k, v in by.items():
        if len(v) < 60:
            continue
        q = st.quantiles(v, n=1000)
        cap[k] = [round(q[int(FLOOR_Q * 10) - 1], 1), round(q[int(CAP_Q * 10) - 1], 1)]
    if verbose:
        print("  Cap/Floor " + " ".join(f"{k}[{a}-{b}]" for k, (a, b) in sorted(cap.items())))
    return cap


def rank4(c4):
    """4角の通過順文字列 → {馬番: 順位}。括弧は併走で、内側の馬から書かれる。"""
    out, k = {}, 0
    for tok in re.findall(r"\([^)]*\)|\d+", c4 or ""):
        for v in re.findall(r"\d+", tok):
            k += 1
            out[int(v)] = k
    return out


def _pace(r, M):
    """そのレースのペース比を返す。1より大きい＝スロー、小さい＝ハイ。"""
    if not (r["klass"] and r["ten3"]):
        return None
    p = par_of(M["ten"], r["place"], r["dist"], r["klass"])
    if not p:
        return None
    tr, _ = M["basa"].get(f"{r['date']}\t{r['place']}", [1.0, 1.0])
    return r["ten3"] / (p * tr)


def bt_of(r, h, M, blend=True):
    """1頭ぶんのBT値。返り値は (BT値, 内訳dict) か None。

    ① 馬場比（テン／上がりの2区間） ② 斤量 ③ 年齢 で補正後タイムを作り、
    ④ ペース補正ブレンド ⑤ ペースバイアス補正 ⑥ クラス別Cap/Floor を当てる。
    """
    if not (h["t"] and h["agari"] and h["kin"] and h["age"]):
        return None
    par = par_of(M["all"], r["place"], r["dist"], BASE_CLASS)   # 全クラス共通の物差し
    if par is None:
        return None
    tr, ar = M["basa"].get(f"{r['date']}\t{r['place']}", [1.0, 1.0])
    ten, ag = h["t"] - h["agari"], h["agari"]
    adj = ten / tr + ag / ar                                    # ① 馬場比（2区間）
    g = agegrp(h["age"], r["month"])
    base = M["ka"]["teiryo"].get(f"{g}\t{h['sex']}")
    if base is None:
        return None
    dk = (h["kin"] - base) * M["ka"]["kin"] * (r["dist"] / 1000.0)
    adj -= dk * KIN_FRONT + dk * (1 - KIN_FRONT)                # ② 斤量（配分は現状同値）
    ac = M["ka"]["age"].get(f"{g}\t{r['month']}", 0.0) * (r["dist"] / 1000.0)
    sa = par - adj - ac                                         # ③ 年齢
    dk1 = r["dist"] / 1000.0
    rr = sa / dk1                                               # 秒/1000m・正なら速い
    d = dict(par=round(par, 1), adj=round(adj, 1), ten_hi=tr, ag_hi=ar,
             kin=round(dk, 2), age=round(ac, 2), sa=round(sa, 2), w=0.0, mode="時計")

    if blend and M.get("blend"):
        pc = _pace(r, M)
        if pc:
            w = min(W_MAX, abs(pc - 1.0) / PACE_SIG * W_AT_1SIG)
            Z = M["blend"]
            if pc > 1.0:
                # ④ スロー：上がり勝負。上がり3Fベースのスコアを混ぜる。
                #    上がりは1頭ごとの実測値なので、走破タイムと独立に測れている。
                pa = par_of(M["ag"], r["place"], r["dist"], BASE_CLASS)
                if pa:
                    sub = (pa - h["agari"] / ar) / 0.6
                    sub = (sub - Z["ag"][0]) / Z["ag"][1] * Z["all"][1] + Z["all"][0]
                    rr = (1 - w) * rr + w * sub
                    # スロー時は軽斤量の恩恵がタイム差以上に効く。ブレンド率に比例して追加。
                    rr -= (base - h["kin"]) * SLOW_KIN * w
                    d.update(w=round(w, 2), mode="上がり寄せ")
            # ★ハイペース側の「テン寄せブレンド」は入れない。実装して外した記録:
            #   原典は1頭ごとの実測テン3Fを混ぜる。だが南関で1頭ごとに取れる区間は
            #   上がり3Fだけなので、テンは【走破タイム − 上がり3F】で作るしかない。
            #   するとテンと上がりが機械的に裏返しになり、
            #   「上がりが悪い馬ほどテンが速い」＝潰れた馬ほど高得点になる。
            #   実測でも 8/2船橋9R で6着(上り42.9)が勝ち馬と同じBT56.1、
            #   11着(上り44.7)が7着・10着より上、という壊れ方をした。
            #   ハイペースで先行した馬への評価は、時計ではなく【位置】で当てる。
            #   → 下のペース×位置の項で処理する。
            d["pace"] = round(pc, 4)

    # ⑤ ペースバイアス補正。日×場の前残り度合いを、その馬の4角位置に当てて外す。
    if M.get("bias") and h["ub"]:
        b = M["bias"].get(f"{r['date']}\t{r['place']}")
        pos = (r.get("rk") or {}).get(h["ub"])
        if b is not None and pos is not None and r.get("n", 0) > 1:
            rel = (pos - 1) / (r["n"] - 1) - 0.5
            rr -= M["bias_g"] * b * rel          # その日の偏りの分
            pc2 = _pace(r, M)
            if pc2 is not None and M.get("pace_p"):
                rr -= M["pace_p"] * ((pc2 - 1.0) / PACE_SIG) * rel   # そのレースの流れの分
            d["bias"] = round(b, 3)

    v = CENTER + rr * dk1 / max(dk1, DIST_FLOOR) * 10 + M.get("anchor", 0.0)

    # ⑥ クラス別Cap/Floor。いびつな馬場やペースで膨らんだ外れ値を止める。
    cf = (M.get("cap") or {}).get(r["klass"] or "?")
    if cf:
        v = max(cf[0], min(cf[1], v))
    return round(v, 1), d


# ---------------------------------------------------------------- 実行

def build(dfrom, dto, verbose=True):
    R = load(dfrom, dto)
    if verbose:
        print(f"■ 読み込み {len(R):,}レース（{dfrom}〜{dto}）")
        print("■ 基準タイム")
    M = {"all": fit_par(R, "wt", verbose), "ten": fit_par(R, "ten3", verbose),
         "ag": fit_par(R, "ag3", verbose)}
    M["basa"] = basa(R, M)
    if verbose:
        print(f"■ 馬場比 {len(M['basa'])} 開催日×場")
        print("■ 斤量・年齢")
    M["ka"] = fit_kin_age(R, M, verbose)
    if verbose:
        print("■ ペース補正ブレンド")
    M["blend"] = fit_blend(R, M)
    if verbose:
        z = M["blend"]
        print(f"  標準化 全体SD{z['all'][1]:.2f} 上がりSD{z['ag'][1]:.2f} テンSD{z['ten'][1]:.2f}"
              f"（秒/1000m）／1σで{W_AT_1SIG:.2f}・上限{W_MAX:.2f}混ぜる")
        print("■ ペースバイアス補正")
    M["bias"], M["bias_g"], M["pace_p"] = fit_bias(R, M, verbose)
    M["anchor"] = 0.0
    # 中心値の据え方。parは【勝ちタイム】で引いてあるので、そのままだと
    # 55＝「B2を基準タイムで勝った走り」になり、分布全体が下に寄る。
    # 原典は「標準的な走りをした馬が中心値」なので、基準クラスの全出走馬の
    # 中央値が55に来るよう平行移動する。ここは目盛りの原点合わせであって、
    # 馬ごとの上下関係は一切変えない。
    v = [b[0] for r in R if r["klass"] == BASE_CLASS for h in r["rows"]
         if (b := bt_of(r, h, M))]
    if len(v) >= 30:
        M["anchor"] = round(CENTER - st.median(v), 2)
        if verbose:
            print(f"■ 中心合わせ {BASE_CLASS}の{len(v):,}走の中央値を55へ（平行移動 {M['anchor']:+.2f}）")
    if verbose:
        print("■ クラス別Cap/Floor")
    M["cap"] = fit_cap(R, M, verbose)
    M["meta"] = dict(dfrom=dfrom, dto=dto, races=len(R), center=CENTER, base_class=BASE_CLASS)
    return M, R


def main():
    ap = argparse.ArgumentParser(description="実走BT値（南関版・Phase 1）")
    ap.add_argument("place", nargs="?")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--fit", action="store_true", help="係数を推定して bt_model.json に保存")
    ap.add_argument("--date", help="この日のBT値を出す")
    ap.add_argument("--horse", help="この馬のBT値推移を出す")
    ap.add_argument("--top", type=int, default=0, help="期間内のBT値上位N走")
    a = ap.parse_args()

    if a.fit or not os.path.exists(MODEL):
        M, _ = build(a.dfrom, a.dto)
        json.dump(M, open(MODEL, "w"), ensure_ascii=False)
        print(f"■ 保存 {MODEL}")
        if a.fit:
            return
    M = json.load(open(MODEL))

    R = load(a.dfrom, a.dto, [a.place] if a.place else None)
    if a.date:
        R = [r for r in R if r["date"] == a.date]
    recs = []
    for r in R:
        for h in r["rows"]:
            b = bt_of(r, h, M)
            if b:
                recs.append((b[0], r, h, b[1]))

    if a.horse:
        v = [x for x in recs if x[2]["name"] == a.horse]
        v.sort(key=lambda z: z[1]["date"])
        print(f"■ {a.horse}  {len(v)}走")
        for bt, r, h, d in v:
            print(f"  {r['date']} {r['place']}{r['dist']}m{r['baba']} {r['klass'] or '?':<4}"
                  f"{h['chaku']:>2}着 {h['t']:.1f} 上り{h['agari']} 斤{h['kin']}  "
                  f"BT {bt:>5.1f}  (馬場比 テン{d['ten_hi']} 上り{d['ag_hi']})")
        return

    if a.date:
        for r in sorted(R, key=lambda z: z["rn"]):
            v = sorted([x for x in recs if x[1] is r], key=lambda z: z[2]["chaku"])
            if not v:
                continue
            print(f"■ {r['rn']}R {r['dist']}m {r['baba']} 【{r['klass'] or '?'}】 {r['rname']}")
            for bt, _, h, d in v:
                print(f"   {h['chaku']:>2}着 {h['ub'] or 0:>2} {h['name']:<14}{h['jockey']:<8}"
                      f"{h['t']:>6.1f} 上り{h['agari']:<5} 斤{h['kin']:<5} {h['ninki'] or 0:>2}人気"
                      f"   BT {bt:>5.1f}")
            print()
        return

    if a.top:
        recs.sort(key=lambda z: -z[0])
        print(f"■ BT値 上位{a.top}走（{a.dfrom}〜{a.dto}{' '+a.place if a.place else ''}）")
        for bt, r, h, d in recs[:a.top]:
            print(f"  BT {bt:>5.1f}  {r['date']} {r['place']}{r['dist']}m{r['baba']} "
                  f"{r['klass'] or '?':<4}{h['chaku']:>2}着 {h['name']:<14}{h['t']:.1f}")
        return

    v = [x[0] for x in recs]
    if v:
        print(f"■ {len(v):,}走  中央 {st.median(v):.1f}  平均 {st.mean(v):.1f}  SD {st.pstdev(v):.1f}")
        print("  分布 " + " ".join(f"{q}%tile {st.quantiles(v, n=100)[q-1]:.1f}"
                                   for q in (5, 25, 50, 75, 95)))


if __name__ == "__main__":
    main()
