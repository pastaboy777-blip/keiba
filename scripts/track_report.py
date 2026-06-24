"""指定場・指定日(範囲)の地方競馬を集計し、ブランド体裁のインフォグラフィック3枚を生成する。

楽天競馬の出馬表(race_card)と成績(race_performance)を結合し、
騎手/厩舎/血統/馬番/遠征・年齢/前走比距離/近5走上り・クラス/距離の偏りを集計。
predict_nankan.py のフェッチ部品を再利用する。

実行例:
    python3 scripts/track_report.py --place 浦和 --from 2026-06-22 --to 2026-06-24
    python3 scripts/track_report.py --place 浦和 --dates 2026-06-22 2026-06-23 2026-06-24 --no-cache

出力: out/<place>_<from>_<to>_p1.png / _p2.png / _p3.png
依存: Pillow と fonts/ (Google Fonts)。fonts/ が無ければ --download で取得を試みる。
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import predict_nankan as pn  # フェッチ部品を再利用
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = ROOT / "fonts"
FONT_FILES = {
    "mincho": "ShipporiMincho-Bold.ttf",
    "boku": "YujiBoku-Regular.ttf",
}
GOOGLE_FONTS = {
    "ShipporiMincho-Bold.ttf": "shipporimincho/ShipporiMincho-Bold.ttf",
    "YujiBoku-Regular.ttf": "yujiboku/YujiBoku-Regular.ttf",
}

# ---- palette ----
WASHI = (244, 240, 231); INK = (30, 26, 24); BLACK = (17, 15, 14)
SHU = (199, 32, 38); SHU_D = (150, 22, 28); GOLD = (186, 152, 84); GOLDL = (214, 186, 116)
GRAY = (120, 112, 107); CARD = (252, 250, 244); BLU = (54, 86, 120)
ORANGE = (196, 120, 40); GREEN = (40, 96, 72); MUTE = (150, 144, 138)


# ====================== データ収集 ======================
def daterange(d_from: str, d_to: str) -> list[str]:
    a = date.fromisoformat(d_from); b = date.fromisoformat(d_to)
    out = []
    while a <= b:
        out.append(a.strftime("%Y%m%d")); a += timedelta(days=1)
    return out


def collect(dates: list[str], place: str, client: PoliteClient):
    """各レースの card+result を結合。開催のある日だけ拾う。"""
    races, runners = [], []
    code = NANKAN_CODES[place]
    for ymd in dates:
        try:
            idx = client.get(pn.RESULT_URL.format(race_id=day_index_race_id(ymd, place)))
            links = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=code))
        except Exception:  # noqa: BLE001
            continue
        for rno, rid in links.items():
            try:
                card = P.parse_card_page(client.get(pn.CARD_URL.format(race_id=rid)), rid)
                res = P.parse_result_page(client.get(pn.RESULT_URL.format(race_id=rid)), rid)
            except Exception:  # noqa: BLE001
                continue
            if not res.rows:
                continue
            w = res.rows[0]
            races.append(dict(cls=getattr(card, "race_class", None), dist=card.distance,
                              field=card.field_size, win_um=w.umaban, win_pop=w.popularity))
            fin = {r.umaban: r.finish_pos for r in res.rows}
            for e in card.entries:
                if e.umaban is None or e.umaban not in fin:
                    continue
                sa = getattr(e, "sex_age", "") or ""
                m = re.search(r"(\d+)", sa)
                pr = e.recent_runs[0] if e.recent_runs else None
                pdist = getattr(pr, "distance", None) if pr else None
                ag = [x.agari for x in e.recent_runs[:5] if getattr(x, "agari", None)]
                runners.append(dict(
                    fin=fin[e.umaban], um=e.umaban,
                    jockey=e.jockey, trainer=e.trainer, sire=e.sire or "不明",
                    prev=getattr(pr, "place", None) if pr else None,
                    age=int(m.group(1)) if m else None,
                    dchg=(card.distance - pdist) if (pdist and card.distance) else None,
                    avg5=(sum(ag) / len(ag)) if ag else None,
                    dist=card.distance, cls=getattr(card, "race_class", None)))
    return races, runners


# ====================== 集計 ======================
def grade(c: str | None) -> str:
    if not c:
        return "?"
    if "オープン" in c or "Ｊｐｎ" in c or "重賞" in c:
        return "OP"
    if "新馬" in c or "２歳" in c:
        return "2歳"
    if "３歳" in c:
        return "3歳"
    if "Ａ" in c:
        return "A"
    if "Ｂ" in c:
        return "B"
    if "Ｃ３" in c:
        return "C3"
    if "Ｃ２" in c:
        return "C2"
    if "Ｃ１" in c:
        return "C1"
    return "他"


def _track(p) -> str | None:
    if not p:
        return None
    for t in ("浦和", "船橋", "大井", "川崎", "門別", "名古屋", "園田", "金沢",
              "笠松", "高知", "佐賀", "水沢", "盛岡", "姫路"):
        if t in str(p):
            return t
    return "他"


def aggregate(races, runners, place):
    win = lambda r: r["fin"] == 1
    t3 = lambda r: r["fin"] and r["fin"] <= 3
    N = len(runners)
    base = sum(t3(r) for r in runners) / N if N else 0
    A = {"meta": dict(nraces=len(races), nrunners=N, base=base)}

    def tally(keyfn):
        w, p, n = Counter(), Counter(), Counter()
        for r in runners:
            k = keyfn(r)
            if k is None:
                continue
            n[k] += 1
            if win(r):
                w[k] += 1
            if t3(r):
                p[k] += 1
        return w, p, n

    jw, jp, jn = tally(lambda r: r["jockey"])
    A["jockey"] = sorted(((k, jw[k], jp[k], jn[k]) for k in jn),
                         key=lambda x: (-x[1], -x[2]))[:5]
    tw, tp, tn = tally(lambda r: r["trainer"])
    A["trainer"] = sorted(((k, tw[k], tp[k], tn[k]) for k in tn),
                          key=lambda x: (-x[1], -x[2]))[:4]
    sw, sp, sn = tally(lambda r: r["sire"])
    A["sire_win"] = sorted(((k, sw[k], sp[k], sn[k]) for k in sn if sw[k] > 0),
                           key=lambda x: (-x[1], -x[2]))[:3]
    A["sire_stable"] = sorted(((k, sw[k], sp[k], sn[k]) for k in sn if sw[k] == 0 and sp[k] >= 3),
                              key=lambda x: -x[2])[:2]
    uw, up, un = tally(lambda r: r["um"])
    A["post_wins"] = {u: (uw[u], up[u]) for u in sorted(un)}
    A["post_zone"] = dict(
        inner_w=sum(uw[u] for u in uw if u <= 4), mid_w=sum(uw[u] for u in uw if 5 <= u <= 8),
        outer_w=sum(uw[u] for u in uw if u >= 9))
    # 遠征
    ens = [r for r in runners if _track(r["prev"]) and _track(r["prev"]) != place]
    src_n = Counter(_track(r["prev"]) for r in ens)
    src_3 = Counter(_track(r["prev"]) for r in ens if t3(r))
    A["ensei"] = dict(n=len(ens), w=sum(win(r) for r in ens), t3=sum(t3(r) for r in ens),
                      src=[(t, src_n[t], src_3[t]) for t, _ in src_n.most_common(3)])
    # 年齢
    A["age"] = []
    for a in (3, 4, 5, 6, 7):
        grp = ([r for r in runners if r["age"] == a] if a < 7
               else [r for r in runners if r["age"] and r["age"] >= 7])
        if grp:
            A["age"].append((f"{a}歳" if a < 7 else "7歳+", len(grp),
                             sum(win(r) for r in grp), sum(t3(r) for r in grp)))
    # 前走比距離
    A["dchg"] = []
    for nm, fn in (("延長", lambda r: r["dchg"] and r["dchg"] > 0),
                   ("同距離", lambda r: r["dchg"] == 0),
                   ("短縮", lambda r: r["dchg"] and r["dchg"] < 0)):
        grp = [r for r in runners if r["dchg"] is not None and fn(r)]
        if grp:
            A["dchg"].append((nm, len(grp), sum(win(r) for r in grp), sum(t3(r) for r in grp)))
    # 近5走上り
    A["agari"] = []
    for nm, fn in (("速い<38.5", lambda v: v < 38.5), ("標準38.5-39.5", lambda v: 38.5 <= v <= 39.5),
                   ("遅い>39.5", lambda v: v > 39.5)):
        grp = [r for r in runners if r["avg5"] is not None and fn(r["avg5"])]
        if grp:
            A["agari"].append((nm, len(grp), sum(win(r) for r in grp), sum(t3(r) for r in grp)))
    wv = [r["avg5"] for r in runners if win(r) and r["avg5"]]
    av = [r["avg5"] for r in runners if r["avg5"]]
    A["agari_avg"] = (sum(wv) / len(wv) if wv else 0, sum(av) / len(av) if av else 0)

    # クラス/距離の偏り
    def bias(keyfn):
        g = defaultdict(list)
        for r in races:
            g[keyfn(r)].append(r)
        out = []
        for k in sorted(g, key=lambda k: -len(g[k])):
            rr = g[k]; n = len(rr)
            if n < 2:
                continue
            out.append(dict(
                key=k, n=n,
                avgpop=sum(x["win_pop"] for x in rr if x["win_pop"]) / n,
                p1=sum(1 for x in rr if x["win_pop"] == 1) / n,
                rough=sum(1 for x in rr if x["win_pop"] and x["win_pop"] >= 5) / n,
                inner=sum(1 for x in rr if x["win_um"] <= 4) / n,
                outer=sum(1 for x in rr if x["win_um"] >= 9) / n))
        return out
    A["class_bias"] = sorted(bias(lambda r: grade(r["cls"])), key=lambda x: -x["rough"])
    A["dist_bias"] = bias(lambda r: r["dist"])
    return A


# ====================== 描画ヘルパ ======================
class Canvas:
    def __init__(self, w, h):
        self.W, self.H = w, h
        self.im = Image.new("RGB", (w, h), WASHI)
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def font(self, kind, size):
        path = FONT_DIR / FONT_FILES[kind]
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            return ImageFont.load_default()

    def M(self, s):
        return self.font("mincho", s)

    def Bk(self, s):
        return self.font("boku", s)

    def text(self, x, y, s, font, fill, anchor="la"):
        self.d.text((x, y), s, font=font, fill=fill, anchor=anchor)

    def header(self, no, title, sub):
        d = self.d
        d.rectangle([0, 0, self.W, 150], fill=BLACK)
        d.rectangle([0, 150, self.W, 156], fill=GOLD)
        self.text(50, 28, "浦和競馬", self.M(58), (245, 242, 236))
        self.text(356, 46, title, self.M(40), SHU)
        self.text(52, 108, sub, self.M(25), (214, 210, 202))
        d.rounded_rectangle([self.W - 128, 28, self.W - 44, 112], radius=12, fill=SHU)
        self.text(self.W - 86, 70, "穴", self.Bk(58), (245, 242, 236), anchor="mm")

    def card(self, x, y, w, h, title):
        d = self.d
        d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=CARD, outline=(225, 219, 206), width=2)
        d.rounded_rectangle([x, y, x + 14, y + h], radius=9, fill=SHU)
        self.text(x + 36, y + 16, title, self.M(34), SHU)
        d.line([x + 36, y + 60, x + w - 26, y + 60], fill=(230, 224, 210), width=2)
        return x + 36, y + 74

    def hbar(self, x, y, w, val, mx, col, h=24):
        self.d.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=(232, 226, 214))
        fw = max(int(w * val / mx) if mx else 0, 6)
        self.d.rounded_rectangle([x, y, x + fw, y + h], radius=6, fill=col)

    def tag(self, x, y, label, col):
        bb = self.d.textbbox((0, 0), label, font=self.M(22))
        self.d.rounded_rectangle([x, y, x + (bb[2] - bb[0]) + 24, y + 34], radius=9, fill=col)
        self.text(x + 12, y + 4, label, self.M(22), (252, 250, 244))

    def footer(self):
        d = self.d
        d.rectangle([0, self.H - 64, self.W, self.H], fill=BLACK)
        self.text(50, self.H - 50, "変態か、", self.M(32), (245, 242, 236))
        self.text(220, self.H - 50, "変態以外か。", self.M(32), SHU)
        self.text(self.W - 50, self.H - 46, "#浦和競馬 #南関", self.M(22), (200, 196, 188), anchor="ra")
        d.rectangle([7, 7, self.W - 8, self.H - 8], outline=GOLD, width=5)
        d.rectangle([18, 18, self.W - 19, self.H - 19], outline=GOLDL, width=2)

    def save(self, path):
        self.im.save(path, quality=95)


def pct(n, d):
    return 100 * n / d if d else 0


# ====================== 3枚の描画 ======================
def render_p1(A, sub, out):
    c = Canvas(1080, 1720); c.header("①", "三日間データ総括", sub)
    X, CW, y = 46, 1080 - 92, 178
    # 騎手
    cx, cy = c.card(X, y, CW, 322, "騎手 ｜ JOCKEY")
    for i, (nm, w, p, n) in enumerate(A["jockey"]):
        yy = cy + i * 40; rate = pct(p, n)
        c.text(cx, yy, nm[:5], c.M(30), INK); c.text(cx + 150, yy + 1, f"{w}勝", c.M(28), SHU)
        c.hbar(cx + 250, yy + 5, 420, rate, 70, SHU if rate >= 50 else (96, 90, 86), h=22)
        c.text(cx + 686, yy, f"{rate:.0f}% ({p}/{n})", c.M(23), GRAY)
    if A["jockey"]:
        top = A["jockey"][0]
        c.text(cx, cy + 212, f"◎軸={top[0][:4]}({pct(top[2],top[3]):.0f}%・{top[1]}勝)が筆頭。",
               c.M(25), SHU_D)
    y += 322 + 22
    # 厩舎
    cx, cy = c.card(X, y, CW, 256, "厩舎 ｜ TRAINER")
    mxw = max((w for _, w, _, _ in A["trainer"]), default=1)
    for i, (nm, w, p, n) in enumerate(A["trainer"]):
        yy = cy + i * 38
        c.text(cx, yy, nm[:5], c.M(30), INK)
        c.hbar(cx + 170, yy + 5, 500, w, mxw, SHU if w >= 10 else GOLD, h=22)
        c.text(cx + 686, yy, f"{w}勝 ({p}/{n})", c.M(24), GRAY)
    if A["trainer"]:
        t = A["trainer"][0]
        c.text(cx, cy + 162, f"★{t[0][:4]}が{t[1]}勝/{t[3]}頭と突出＝最重要厩舎。", c.M(25), SHU_D)
    y += 256 + 22
    # 血統
    cx, cy = c.card(X, y, CW, 262, "血統(父) ｜ SIRE")
    c.text(cx, cy, "勝ち身が強い", c.M(26), SHU)
    for i, (nm, w, p, n) in enumerate(A["sire_win"]):
        c.text(cx + 6, cy + 42 + i * 38, f"・{nm[:11]}", c.M(28), INK)
        c.text(cx + 600, cy + 42 + i * 38, f"{w}勝", c.M(28), SHU)
    if A["sire_stable"]:
        names = " / ".join(s[0][:10] for s in A["sire_stable"])
        c.text(cx, cy + 170, f"連対安定: {names}", c.M(23), GRAY)
    y += 262 + 22
    # 馬番
    cx, cy = c.card(X, y, CW, 360, "馬番バイアス ｜ POST")
    z = A["post_zone"]
    c.text(cx, cy, f"内枠優勢 ▶ 内(1-4) {z['inner_w']}勝 / 中(5-8) {z['mid_w']}勝 / 外(9-) {z['outer_w']}勝",
           c.M(27), SHU_D)
    wins = A["post_wins"]; nums = sorted(wins)
    mx = max((wins[u][0] for u in nums), default=1); bw, gap, bx, by = 74, 10, cx + 6, cy + 250
    for i, u in enumerate(nums):
        wv = wins[u][0]; h = int(118 * wv / mx) if mx else 0
        col = SHU if u <= 4 else (GOLD if u <= 8 else MUTE)
        xx = bx + i * (bw + gap)
        c.d.rounded_rectangle([xx, by - h, xx + bw, by], radius=5, fill=col)
        c.text(xx + bw // 2, by + 6, str(u), c.M(22), GRAY, anchor="ma")
        c.text(xx + bw // 2, by - h - 26, str(wv), c.M(22), INK, anchor="ma")
    y += 360 + 22
    # 遠征
    cx, cy = c.card(X, y, CW, 158, "遠征馬(前走 他場) ｜ SHIP-IN")
    e = A["ensei"]
    c.text(cx, cy, f"前走≠浦和 {e['n']}頭 → 3着内 {pct(e['t3'],e['n']):.0f}%"
           f"（平均{A['meta']['base']*100:.0f}%）", c.M(26), INK)
    srcs = " / ".join(f"{t}{n}頭{pct(p,n):.0f}%" for t, n, p in e["src"])
    c.text(cx, cy + 42, f"前走場: {srcs}", c.M(24), GRAY)
    c.footer(); c.save(out)


def render_p2(A, sub, out):
    c = Canvas(1080, 1180); c.header("②", "三日間データ②", sub)
    X, CW, y = 46, 1080 - 92, 178

    def section(title, rows, h, note, mxrate=42):
        nonlocal y
        cx, cy = c.card(X, y, CW, h, title)
        for i, (nm, n, w, p) in enumerate(rows):
            yy = cy + i * 44; rate = pct(p, n)
            c.text(cx, yy, nm, c.M(28), INK); c.text(cx + 250, yy + 3, f"{w}勝", c.M(24), SHU)
            c.hbar(cx + 360, yy + 4, 300, rate, mxrate,
                   SHU if rate >= 35 else (GOLD if rate >= 33 else MUTE), h=26)
            c.text(cx + 676, yy, f"{rate:.0f}% ({n})", c.M(22), GRAY)
        c.text(cx, cy + len(rows) * 44 + 14, note, c.M(24), SHU_D)
        y += h + 24

    section("年齢 ｜ AGE", A["age"], 358,
            "◎3歳が優勢の年は内枠ほど信頼。6歳以降は割引傾向。")
    section("前走比 距離 ｜ DISTANCE", A["dchg"], 254,
            "延長有利・短縮割引なら、極端な距離替わりは慎重に。")
    cx, cy = c.card(X, y, CW, 300, "近5走 平均上り ｜ LAST-3F")
    for i, (nm, n, w, p) in enumerate(A["agari"]):
        yy = cy + i * 44; rate = pct(p, n)
        c.text(cx, yy, nm, c.M(27), INK); c.text(cx + 270, yy + 3, f"{w}勝", c.M(23), SHU)
        c.hbar(cx + 360, yy + 4, 300, rate, 42, SHU if rate >= 35 else MUTE, h=26)
        c.text(cx + 676, yy, f"{rate:.0f}% ({n})", c.M(22), GRAY)
    wv, av = A["agari_avg"]
    c.text(cx, cy + 150, f"上りが速い馬が優位。勝ち馬平均{wv:.2f}秒 ＜ 全体{av:.2f}秒。",
           c.M(24), SHU_D)
    c.footer(); c.save(out)


def _class_tag(b):
    if b["rough"] >= 0.40:
        return "荒れ", SHU
    if b["rough"] >= 0.25:
        return "中波乱", ORANGE
    if b["p1"] >= 0.6 or b["avgpop"] <= 1.5:
        return "鉄板", GREEN
    if b["inner"] >= 0.55:
        return "内枠堅", BLU
    return "堅い", BLU


def _dist_tag(b):
    if b["rough"] >= 0.35:
        return ("荒れ・内枠" if b["inner"] >= 0.5 else "荒れ"), SHU
    if b["outer"] >= 0.45:
        return "外枠注意", ORANGE
    if b["p1"] >= 0.6:
        return "1人気軸", BLU
    return ("堅・内枠" if b["inner"] >= 0.5 else "堅め"), BLU


def render_p3(A, sub, out):
    c = Canvas(1080, 1300); c.header("③", "三日間データ③", sub)
    X, CW, y = 46, 1080 - 92, 178

    def row(cx, yy, name, b, tagfn):
        rough = b["rough"] * 100
        c.text(cx, yy, name, c.M(29), INK)
        bx, barw = cx + 150, 180
        c.hbar(bx, yy + 4, barw, rough, 55,
               SHU if rough >= 40 else (GOLD if rough >= 25 else MUTE), h=26)
        c.text(bx + barw + 12, yy + 2, f"荒{rough:.0f}%", c.M(22),
               SHU_D if rough >= 40 else GRAY)
        stat = f"内勝{b['inner']*100:.0f}% 1人{b['p1']*100:.0f}%"
        c.text(bx + barw + 118, yy + 3, stat, c.M(21), GRAY)
        tg, col = tagfn(b)
        bb = c.d.textbbox((0, 0), tg, font=c.M(22))
        c.tag(cx + 904 - (bb[2] - bb[0] + 24), yy - 1, tg, col)

    cb = A["class_bias"][:6]
    hA = 96 + len(cb) * 52 + 40
    cx, cy = c.card(X, y, CW, hA, "クラス別 ｜ CLASS （バー=5番人気↓勝率＝荒れ度）")
    for i, b in enumerate(cb):
        row(cx, cy + i * 52, b["key"], b, _class_tag)
    c.text(cx, cy + len(cb) * 52 + 8, "◎荒れる=上段／堅い=下段。クラスで狙いを切り替える。",
           c.M(24), SHU_D)
    y += hA + 24
    db = A["dist_bias"][:6]
    hB = 96 + len(db) * 52 + 40
    cx, cy = c.card(X, y, CW, hB, "距離別 ｜ DISTANCE （バー=荒れ度）")
    for i, b in enumerate(db):
        row(cx, cy + i * 52, f"{b['key']}m", b, _dist_tag)
    c.text(cx, cy + len(db) * 52 + 8, "◎距離で枠・人気の傾きが変わる。荒れ距離×内枠が穴の軸。",
           c.M(24), SHU_D)
    c.footer(); c.save(out)


# ====================== main ======================
def ensure_fonts(download: bool):
    FONT_DIR.mkdir(exist_ok=True)
    for fn, slug in GOOGLE_FONTS.items():
        p = FONT_DIR / fn
        if p.exists():
            continue
        if not download:
            print(f"[警告] フォントが無い: {p}  (--download で取得 / または手動取得)")
            continue
        url = f"https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}"
        try:
            urllib.request.urlretrieve(url, p)
            print(f"  取得: {fn}")
        except Exception as ex:  # noqa: BLE001
            print(f"[警告] {fn} 取得失敗: {ex}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", choices=list(NANKAN_CODES), default="浦和")
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    ap.add_argument("--dates", nargs="*", help="YYYY-MM-DD を直接列挙(--from/--to の代わり)")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--download", action="store_true", help="fonts/ が無ければ取得を試みる")
    args = ap.parse_args()

    if args.dates:
        ymds = [d.replace("-", "") for d in args.dates]
        tag_from, tag_to = args.dates[0], args.dates[-1]
    elif args.d_from and args.d_to:
        ymds = daterange(args.d_from, args.d_to)
        tag_from, tag_to = args.d_from, args.d_to
    else:
        ap.error("--from/--to か --dates を指定してください")

    ensure_fonts(args.download)
    client = PoliteClient(use_cache=not args.no_cache)
    print(f"収集中: {args.place} {tag_from}〜{tag_to} ({len(ymds)}日)…")
    races, runners = collect(ymds, args.place, client)
    if not races:
        raise SystemExit("対象レースが見つかりません(開催日/結果未確定の可能性)")
    A = aggregate(races, runners, args.place)
    m = A["meta"]
    sub = (f"{tag_from}〜{tag_to}  全{m['nraces']}R・出走{m['nrunners']}頭"
           f"  ※平均3着内率 {m['base']*100:.0f}%")
    print(f"  {m['nraces']}R / {m['nrunners']}頭 集計完了")

    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.place}_{tag_from}_{tag_to}".replace("-", "")
    p1 = outdir / f"{stem}_p1.png"; p2 = outdir / f"{stem}_p2.png"; p3 = outdir / f"{stem}_p3.png"
    render_p1(A, sub, p1); render_p2(A, sub, p2); render_p3(A, sub, p3)
    print(f"出力: {p1}\n      {p2}\n      {p3}")


if __name__ == "__main__":
    main()
