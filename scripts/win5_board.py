# -*- coding: utf-8 -*-
"""中央(JRA)WIN5：対象5レースの出走馬を『クラス横断で比較できる時計指数』で並べる。

南関のズブ穴は「勝ち圏の上がりを再現できるか(399)」で測るが、中央のWIN5は
条件も場もクラスもバラバラの5鞍を横並びにする必要がある。そこで物差しを変えて、

  ① 各馬の過去5走から『そのレースの勝ちタイム』を復元（自分の時計 − 着差）
  ② 勝ちタイム ≒ (距離帯) + (競馬場) + (馬場×芝ダ) + (クラス段階) を最小二乗で推定
  ③ 各馬の走破時計を「3勝クラス・その条件の標準勝ち時計より何秒速いか」に換算

②で馬場係数が「芝は渋るほど遅い／ダートは湿るほど速い」と実測どおりに出るかが
物差しの健全性チェックになる（出ない年は母数不足かパース漏れを疑う）。

    python3 scripts/win5_board.py 20260801            # 一覧
    python3 scripts/win5_board.py 20260801 --race 3   # 3レース目だけ
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

import numpy as np
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CTX = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
CACHE = Path("data/cache_win5_board")
WIN5 = "https://race.netkeiba.com/top/win5.html?date={d}"
PAST = "https://race.netkeiba.com/race/shutuba_past.html?race_id={rid}"
COURSE = re.compile(r"^(芝|ダ|障)(\d+)(\(外\)|\(内\))?(\s+(\d+:\d+\.\d+))?$")
KL = {"新馬": 0, "未勝利": 0, "1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4,
      "オープン": 4, "GIII": 5, "GII": 6, "GI": 7}
_last = [0.0]


def get(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (re.sub(r"\W", "_", url)[-80:] + ".html")
    if key.exists():
        return key.read_text()
    wait = 1.2 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    html = urllib.request.urlopen(req, timeout=30, context=CTX).read().decode("utf-8", "ignore")
    key.write_text(html)
    return html


def sec(t):
    m = re.match(r"(\d+):(\d+)\.(\d)", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


def kl(k):
    return KL.get((k or "").translate(str.maketrans("１２３", "123")), 3)


def parse_past(td):
    """馬柱1走ぶん。行数が可変なのでコース行を基準に前後を切る。"""
    t = [x.replace("\xa0", " ") for x in td.get_text("\n", strip=True).split("\n")]
    m0 = re.match(r"(\d{4})\.(\d{2})\.(\d{2})\s+(\S+)", t[0] if t else "")
    if not m0:
        return None
    ci = next((i for i, x in enumerate(t) if COURSE.match(x)), None)
    if ci is None:
        return None
    d = {"date": f"{m0.group(1)}-{m0.group(2)}-{m0.group(3)}", "place": m0.group(4)}
    head = t[1:ci]                                   # [着順, レース名, (クラス)]
    d["fin"] = int(head[0]) if head and head[0].isdigit() else None
    d["race"] = head[1] if len(head) > 1 else None
    d["klass"] = head[2] if len(head) > 2 else None
    m = COURSE.match(t[ci])
    d["surf"], d["dist"], d["time"] = m.group(1), int(m.group(2)), m.group(5)
    rest = t[ci + 1:]
    if rest and rest[0] in ("良", "稍", "重", "不"):
        d["baba"] = rest[0]
        rest = rest[1:]
    if rest and (m := re.match(r"(\d+)頭 (\d+)番 (\d+)人 (\S+) ([\d.]+)", rest[0])):
        d.update(field=int(m.group(1)), umaban=int(m.group(2)), pop=int(m.group(3)),
                 jockey=m.group(4), kin=float(m.group(5)))
        rest = rest[1:]
    if rest and (m := re.match(r"([\d\-]*) ?\(([\d.]+)\) ?(\d+)?(\(([+-]?\d+)\))?", rest[0])):
        d.update(corner=[int(x) for x in m.group(1).split("-") if x], agari=float(m.group(2)),
                 hw=int(m.group(3)) if m.group(3) else None,
                 hw_diff=int(m.group(5)) if m.group(5) else None)
        rest = rest[1:]
    if rest:
        d["winner"] = rest[0]
        rest = rest[1:]
    if rest and (m := re.match(r"\(([-\d.]+)\)", rest[0])):
        d["margin"] = float(m.group(1))
    return d


def collect(ymd):
    """WIN5対象5鞍の出走馬＋過去5走。"""
    html = get(WIN5.format(d=ymd))
    ids = sorted(set(re.findall(r"race_id=(\d{12})", html)))
    if len(ids) != 5:
        raise SystemExit(f"WIN5対象レースが5鞍取れない（{len(ids)}件）。発売日か日付を確認。")
    # win5.html 内の並び順＝1〜5レース目
    order = []
    for m in re.finditer(r"race_id=(\d{12})", html):
        if m.group(1) not in order:
            order.append(m.group(1))
    out = {}
    for rid in order:
        s = BeautifulSoup(get(PAST.format(rid=rid)), "html.parser")
        horses = []
        for tr in s.select("tr.HorseList"):
            info, um = tr.select_one("td.Horse_Info"), tr.select_one("td.Waku")
            if not info or not um or not um.get_text(strip=True).isdigit():
                continue
            ln = info.get_text("\n", strip=True).split("\n")
            jk = tr.select_one("td.Jockey").get_text("\n", strip=True).split("\n")
            horses.append(dict(
                umaban=int(um.get_text(strip=True)),
                sire=ln[0] if ln else None, name=ln[1] if len(ln) > 1 else None,
                sexage=jk[0] if jk else None, jockey=jk[1] if len(jk) > 1 else None,
                kin=float(jk[2]) if len(jk) > 2 and re.match(r"[\d.]+$", jk[2]) else None,
                past=[p for p in (parse_past(td) for td in tr.select("td.Past")) if p]))
        out[rid] = dict(name=s.select_one(".RaceName").get_text(strip=True),
                        data1=s.select_one(".RaceData01").get_text(" ", strip=True),
                        data2=s.select_one(".RaceData02").get_text(" ", strip=True),
                        horses=horses)
    return out


def add_figures(D):
    """勝ちタイムを条件で回帰して、各走を『3勝クラス標準勝ち時計 − 走破時計』に換算。"""
    races = {}
    for r in D.values():
        for h in r["horses"]:
            for p in h["past"]:
                t, mg = sec(p.get("time")), p.get("margin")
                if t is None or mg is None or p.get("surf") == "障":
                    continue
                races[(p["date"], p["place"], p.get("race"))] = dict(
                    place=p["place"], surf=p["surf"], dist=p["dist"],
                    baba=p.get("baba", "良"), k=kl(p.get("klass")),
                    wt=t if p.get("fin") == 1 else t - mg)
    rs = list(races.values())
    grp = sorted({(x["surf"], x["dist"]) for x in rs})
    pl = sorted({x["place"] for x in rs})
    bb = [s + b for s in ("芝", "ダ") for b in ("良", "稍", "重", "不")]
    gi = {g: i for i, g in enumerate(grp)}
    pi = {p: i for i, p in enumerate(pl)}
    bi = {b: i for i, b in enumerate(bb)}
    NG, NP = len(grp), len(pl)
    X = np.zeros((len(rs), NG + NP + len(bb) + 1))
    y = np.array([x["wt"] for x in rs])
    for i, x in enumerate(rs):
        X[i, gi[(x["surf"], x["dist"])]] = 1
        X[i, NG + pi[x["place"]]] = 1
        X[i, NG + NP + bi.get(x["surf"] + x["baba"], 0)] = 1
        X[i, -1] = x["k"] - 3                       # クラス1段階あたりの秒差
    I = np.eye(X.shape[1]); I[:NG, :NG] = 0         # 距離帯の主効果だけ罰則なし
    beta = np.linalg.solve(X.T @ X + I, X.T @ y)
    print(f"■ 物差し：{len(rs)}レースで較正／残差SD {np.std(y - X @ beta):.2f}秒"
          f"／クラス係数 {beta[-1]:+.2f}秒per段")
    for s in ("芝", "ダ"):
        adj = {b: round(beta[NG + NP + bi[s + b]] - beta[NG + NP + bi[s + "良"]], 2)
               for b in ("良", "稍", "重", "不")}
        print(f"  馬場補正({s}) {adj}")

    def par(place, surf, dist, baba):
        if (surf, dist) not in gi or place not in pi or surf + baba not in bi:
            return None
        return beta[gi[(surf, dist)]] + beta[NG + pi[place]] + beta[NG + NP + bi[surf + baba]]

    for r in D.values():
        for h in r["horses"]:
            for p in h["past"]:
                b = par(p.get("place"), p.get("surf"), p.get("dist"), p.get("baba", "良"))
                t = sec(p.get("time"))
                p["fig"] = round(b - t, 2) if (b is not None and t is not None) else None
    return D


def wid(s, n):
    """全角込みの表示幅で切って詰める。"""
    out, cur = "", 0
    for ch in s or "":
        c = 2 if ord(ch) > 0x2000 else 1
        if cur + c > n:
            break
        out += ch
        cur += c
    return out + " " * (n - cur)


def main():
    ap = argparse.ArgumentParser(description="WIN5の5鞍を時計指数で並べる")
    ap.add_argument("ymd", help="開催日 YYYYMMDD")
    ap.add_argument("--race", type=int, help="1〜5レース目のどれか一つだけ")
    args = ap.parse_args()

    D = add_figures(collect(args.ymd))
    for n, (rid, r) in enumerate(D.items(), 1):
        if args.race and n != args.race:
            continue
        m = re.search(r"(芝|ダ)(\d+)m", r["data1"])
        surf, dist = (m.group(1), int(m.group(2))) if m else (None, 0)
        print("\n" + "=" * 108)
        print(f"■ {n}レース目 {r['name']}  {r['data1']}".replace("\n", " "))
        print(f"  {r['data2']}")
        rows = []
        for h in r["horses"]:
            f = sorted((p["fig"] for p in h["past"] if p.get("fig") is not None), reverse=True)
            rec = [p["fig"] for p in h["past"][:4] if p.get("fig") is not None]
            cond = [p["fig"] for p in h["past"] if p.get("fig") is not None
                    and p.get("surf") == surf and abs(p.get("dist", 0) - dist) <= 200]
            hi = [p["margin"] for p in h["past"]
                  if (p.get("klass") or "") in ("3勝", "OP", "L", "GIII", "GII", "GI")
                  and p.get("margin") is not None]
            rows.append(dict(h=h, top2=sum(f[:2]) / len(f[:2]) if f else None,
                             rec=sum(rec) / len(rec) if rec else None,
                             cond=max(cond) if cond else None,
                             mg=sum(hi) / len(hi) if hi else None, nhi=len(hi)))
        rows.sort(key=lambda x: -(x["top2"] if x["top2"] is not None else -9))
        for x in rows:
            h = x["h"]
            g = lambda v: f"{v:6.2f}" if v is not None else "     -"
            print(f"\n{h['umaban']:>2} {wid(h['name'], 20)}{wid(h['sexage'], 7)}{wid(h['jockey'], 7)}"
                  f"{h['kin'] or 0:>5}  上位2走{g(x['top2'])} 近4走{g(x['rec'])} "
                  f"該当条件{g(x['cond'])} 上級{x['nhi']:>2}走平均着差{g(x['mg'])}")
            for p in h["past"][:5]:
                print(f"     {p['date']} {wid(p['place'], 4)}{wid(p.get('race'), 10)}"
                      f"{wid(p.get('klass'), 4)}{p.get('surf', '')}{p.get('dist', '')}"
                      f"{p.get('baba', ''):<2} {str(p.get('fin') or '?'):>3}着/{p.get('field', '?'):>2}頭"
                      f" {p.get('pop', '?'):>2}人 上{p.get('agari', '-'):>5} 差{p.get('margin', '-'):>5}"
                      f" 体{p.get('hw', '-'):>4} 指数{p.get('fig') if p.get('fig') is not None else '-':>6}")


if __name__ == "__main__":
    main()
