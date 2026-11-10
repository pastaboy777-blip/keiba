"""隊列表 ── 横＝4角の前後、縦＝内外（枠1枠ずつ＋騎手）。

  python3 taretsu_zu.py <card.json> <res.json> <out.html> --R 6-12 \\
      --ven 川崎 --date 2026.11.10 --baba 不良

★ 縦は推測ではなくデータ（2026-11-11 にユーザーと詰めて確定。CLAUDE.md ルール19・21）

  枠ごとの内率（4角で併走したとき内にいた割合／南関12,244頭）
    1枠79.8 2枠71.1 3枠60.5 4枠50.9 5枠45.0 6枠34.6 7枠30.8 8枠21.9 ／ 基準線44.9
    **1-2／3-6／7-8 の3束にしない。** 3枠(60.5)が4-6枠に丸められて③が沈んだ。

  騎手の内率（併走11,767回・107人／jk_soto.py）。基準線44.7との差を枠に足す。
    加藤雄56.5 櫻井光57.4 … 山口達30.9。母数60回未満は使わない。
    出馬表の騎手名には減量記号（△▲◇☆★）が付く。外さないと照合できない。

★ 狙う帯（スロー）… 内か中の帯で、4角の相対0.40まで

  遅い流れの3着内率 … 前(0-.2)64.3% ／ 中前(.2-.4)36.8% ／ **中(.4-.6)18.9%**
  0.40を越えると半分に落ちる。内枠でも後ろにいる馬は入れない。
  ミドル・ハイの帯はまだ決めていないので囲まない（決まったら足す）。

★ 過去走のない馬も出す。ただし前後は読めないので鞍の中央に置き、札で明記する。
"""
import sys, os, json, re, html, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from horse_svg import HORSE, CHEV
import tenkai as T

WAKU = {1: ('#ffffff', '#111'), 2: ('#1b1b1b', '#fff'), 3: ('#e03a30', '#fff'),
        4: ('#2d6fd0', '#fff'), 5: ('#f2d231', '#111'), 6: ('#2f9e57', '#fff'),
        7: ('#f08a24', '#111'), 8: ('#f29ab8', '#111')}
WK = {1: .798, 2: .711, 3: .605, 4: .509, 5: .450, 6: .346, 7: .308, 8: .219}
JK_BASE, JK_MIN = .447, 60
POS_MAX = 0.40          # スローもハイも、4角の相対はここまで
# 狙う帯 … スローは「内か中」、ハイは「中か外」。内外の向きだけが入れ替わる。
#   11/9 川崎6R（実測ハイ）は併走3組すべて外が内に勝ち、1着④(中)・2着⑦(外)・3着⑥(中)。
#   内の帯の①②③は 9着・11着・7着。
BAND_OK = {"s": (0, 1), "h": (1, 2), "m": (0, 1)}
WID, LANE, PAD, GAP = 900, 78, 58, 112
JK = json.load(open(os.path.join(HERE, "jk_soto.json"))) \
    if os.path.exists(os.path.join(HERE, "jk_soto.json")) else {}


def jk_rate(name):
    n = re.sub(r"^[△▲◇☆★◎]+", "", (name or "").strip())
    a = JK.get(n)
    if a and a[0] >= JK_MIN:
        return n, a[1] / a[0]
    return n, None


def rel(p, key):
    if not p.get(key) or not p.get("n"):
        return None
    return (p[key] - 1) / max(1, p["n"] - 1)


def prof_row(h, dist, res_row):
    P = h.get("past") or []
    c4 = [rel(p, "c4") for p in P]; c4 = [x for x in c4 if x is not None]
    per = []
    for p in P:
        a, b = rel(p, "c1"), rel(p, "c4")
        if a is not None and b is not None:
            per.append(a - b)
    e, l, _c, n, ext = T.prof(h, dist)
    w = (res_row or {}).get("waku") or h.get("waku") or 4
    jn, jr = jk_rate((res_row or {}).get("jk"))
    u = WK.get(w, .45) + ((jr - JK_BASE) if jr is not None else 0.0)
    return dict(ub=h["ub"], name=h["name"], waku=w, jk=jn, jr=jr, uchi=u,
                pos=(st.median(c4) if c4 else None),
                gain=(st.median(per) if per else None),
                l=l, runs=len(P),
                chaku=(res_row or {}).get("chaku"),
                c4=(res_row or {}).get("c4"), agari=(res_row or {}).get("agari"))


def band_of(r):
    return 0 if r["uchi"] >= .55 else (2 if r["uchi"] <= .40 else 1)


def pace_soutei(card_v, ven, baba=None):
    """★ 走る前の想定（2026-11-11 に追加）。

    結果のラップが無い鞍があるのと、そもそも**事前に出せるものを出す**ため。
    tenkai.race が返す推定前3F を、その場・距離・馬場の水準と比べる。
    推定は先頭に立つ3頭の前半速度から出しているので、1頭に引かれることがある
    （11/10 の8R・10R・12Rで実際に起きた）。あくまで想定。"""
    rows, p_ = T.race(card_v, ven, baba)
    if not p_ or not p_.get("base") or not p_.get("f3"):
        return None, None, None
    f3, b = p_["f3"], p_["base"]
    cls = "s" if f3 > b["f3"] + 0.3 else ("h" if f3 < b["f3"] - 0.3 else "m")
    return f3, b["f3"], cls


def pace_of(v, ven):
    """結果のラップから実際の流れを出す。ラップが無ければ None。"""
    L = v.get("lap") or []
    if not L or not v.get("dist"):
        return None, None, None
    full = L[1:] if L[0] < 10 else L
    if len(full) < 3:
        return None, None, None
    f3 = sum(full[:3])
    b = T.sui(ven, v["dist"], v.get("baba"))
    if not b:
        return f3, None, None
    cls = "s" if f3 > b["f3"] + 0.3 else ("h" if f3 < b["f3"] - 0.3 else "m")
    return f3, b["f3"], cls


LAB = {"s": ("S", "スロー想定"), "m": ("M", "ミドル想定"),
       "h": ("H", "ハイ想定"), None: ("?", "測れず")}
LAB_J = {"s": ("S", "スロー（実測）"), "m": ("M", "水準どおり（実測）"),
         "h": ("H", "ハイ（実測）"), None: ("?", "ラップなし")}


def place(rows):
    ps = [r["pos"] for r in rows if r["pos"] is not None]
    mid = st.median(ps) if ps else .5
    hs = sorted(rows, key=lambda r: (-r["uchi"], r["pos"] if r["pos"] is not None else mid))
    sub = {0: [], 1: [], 2: []}
    tmp = []
    for r in hs:
        b = band_of(r)
        p = r["pos"] if r["pos"] is not None else mid
        x = PAD + (1 - p) * (WID - 2 * PAD)
        for i, last in enumerate(sub[b]):
            if x < last - GAP:
                sub[b][i] = x; tmp.append((r, x, b, i)); break
        else:
            sub[b].append(x); tmp.append((r, x, b, len(sub[b]) - 1))
    base, n, span = {}, 0, []
    for b in (0, 1, 2):
        c = len(sub[b]); base[b] = n
        if c:
            span.append((b, n, c)); n += c
    return [(r, x, base[b] + i) for r, x, b, i in tmp], max(1, n), span


def ring(cells, ana):
    pts = [(x, ln) for r, x, ln in cells if r["ub"] in ana]
    if not pts:
        return ""
    xs = [p[0] for p in pts]; ls = [p[1] for p in pts]
    return ('<div class="ring" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
            % (int(min(xs) - 72), int(min(ls) * LANE + 6),
               int(max(xs) - min(xs) + 144), int((max(ls) - min(ls) + 1) * LANE - 14)))


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0c0c0e;color:#f2f2f4;width:1060px;padding:32px 38px 34px;
 font-family:"Noto Sans CJK JP","Hiragino Sans","Yu Gothic",sans-serif}
.head{border-bottom:2px solid #e8362f;padding-bottom:13px;margin-bottom:16px}
.kicker{color:#e8362f;font-size:13px;letter-spacing:.14em;font-weight:700}
h1{font-size:30px;font-weight:800;margin:5px 0 6px}
.sub{color:#8c8c96;font-size:12.4px;line-height:1.8}.sub b{color:#f2f2f4}
.race{background:#16161a;border:1px solid #2a2a31;border-radius:10px;margin-bottom:14px;overflow:hidden}
.rh{padding:10px 16px;background:#121216;border-bottom:1px solid #2a2a31;display:flex;align-items:center;gap:10px}
.rn{font-size:19px;font-weight:800}.rd{font-size:12px;color:#8c8c96}.rd b{color:#f2f2f4}
.pace{margin-left:auto;font-size:17px;font-weight:800;border-radius:7px;padding:3px 14px;border:2px solid}
.pace b{font-size:20px;margin-right:8px}
.p-s{color:#8fbcf2;border-color:rgba(57,135,229,.5);background:rgba(57,135,229,.16)}
.p-m{color:#e0bd72;border-color:rgba(216,168,74,.45);background:rgba(216,168,74,.14)}
.p-h{color:#f08d88;border-color:rgba(232,54,47,.5);background:rgba(232,54,47,.15)}
.p-x{color:#8c8c96;border-color:#3a3a44}
.pbar{margin:11px 16px 4px;padding:10px 14px;border:1px solid;border-radius:9px}
.pbar.p-s{background:rgba(57,135,229,.07);border-color:rgba(57,135,229,.5)}
.pbar.p-m{background:rgba(216,168,74,.06);border-color:rgba(216,168,74,.45)}
.pbar.p-h{background:rgba(232,54,47,.07);border-color:rgba(232,54,47,.5)}
.pbar.p-x{background:#17171c;border-color:#3a3a44}
.gauge{position:relative;display:flex;height:22px;border-radius:5px;overflow:hidden;border:1px solid #33333c}
.gz{flex:1;font-size:10px;line-height:20px;text-align:center;color:#9a9aa4;font-weight:700}
.z1{background:rgba(57,135,229,.2)}.z2{background:rgba(216,168,74,.16)}.z3{background:rgba(232,54,47,.2)}
.gmark{position:absolute;top:-4px;bottom:-4px;width:4px;background:#fff;border-radius:2px;
 transform:translateX(-2px);box-shadow:0 0 0 2px rgba(0,0,0,.6)}
.peff{font-size:13px;color:#e4e4ea;margin-top:7px;font-weight:600}.peff b{color:#fff}
.view{margin:0 16px 12px;background:#121216;border:1px solid #2a2a31;
 border-left:3px solid #3987e5;border-radius:8px;padding:11px 14px}
.view h4{font-size:11px;color:#3987e5;letter-spacing:.1em;margin-bottom:6px;font-weight:700}
.view p{font-size:12.5px;line-height:1.9;color:#c9c9d2}.view b{color:#f2f2f4}
.pnum{font-size:11.5px;color:#8c8c96;margin:8px 16px 0}
.track{position:relative;margin:8px 16px 10px;border-radius:7px;
 background:repeating-linear-gradient(90deg,#3b3027 0 56px,#342a22 56px 58px);
 border-top:3px solid #d9d9de}
.goal{position:absolute;right:24px;top:0;bottom:0;width:2px;background:rgba(232,54,47,.8)}
.bz{position:absolute;left:5px;right:5px;border-radius:7px;z-index:0;pointer-events:none}
.bz.zi{background:rgba(95,224,122,.09);box-shadow:inset 0 0 0 1px rgba(95,224,122,.38)}
.bz.zm{background:rgba(216,168,74,.05);box-shadow:inset 0 0 0 1px rgba(216,168,74,.22)}
.bz.zo{background:rgba(255,159,82,.075);box-shadow:inset 0 0 0 1px rgba(255,159,82,.35)}
.bzl{position:absolute;left:9px;top:5px;font-size:10px;font-weight:800;padding:1px 7px;border-radius:4px}
.zi .bzl{background:rgba(95,224,122,.9);color:#0c0c0e}
.zm .bzl{background:rgba(216,168,74,.85);color:#0c0c0e}
.zo .bzl{background:rgba(255,159,82,.9);color:#0c0c0e}
.ring{position:absolute;border:3px solid #e8362f;border-radius:34px;z-index:1;
 box-shadow:0 0 18px rgba(232,54,47,.45);pointer-events:none}
.h{position:absolute;transform:translate(-50%,0);text-align:center;width:124px;white-space:nowrap;z-index:2}
.fig{display:flex;align-items:flex-end;justify-content:center;gap:1px;height:30px}
.fig svg{width:42px;height:28px}
.lab{margin-top:-1px}
.n{display:inline-block;min-width:20px;height:20px;line-height:20px;border-radius:50%;
 border:2px solid rgba(255,255,255,.45);font-size:11.5px;font-weight:800;vertical-align:middle;margin-right:3px}
.nm{font-size:10.2px;font-weight:700;color:#f6f1e8;vertical-align:middle;text-shadow:0 1px 4px rgba(0,0,0,.95)}
.ch{display:block;font-size:10px;font-weight:800;color:#5fe07a}
.t{display:block;font-size:9px;font-weight:800}
.up{color:#6fc0ff}.dn{color:#e58b86}
.sm{display:block;font-size:9px;color:#15110d;background:#5fe07a;border-radius:3px;
 padding:0 5px;font-weight:800;margin:1px auto 0;width:max-content}
.jin{display:block;font-size:8.8px;color:#0c0c0e;background:#5fe07a;border-radius:3px;
 padding:0 5px;font-weight:800;margin:1px auto 0;width:max-content}
.jout{display:block;font-size:8.8px;color:#0c0c0e;background:#ff9f52;border-radius:3px;
 padding:0 5px;font-weight:800;margin:1px auto 0;width:max-content}
.nx{display:block;font-size:8.8px;color:#0c0c0e;background:#e8a0a0;border-radius:3px;
 padding:0 5px;font-weight:800;margin:1px auto 0;width:max-content}
.xlab{display:flex;justify-content:space-between;margin:0 16px 10px;font-size:11px;color:#8c8c96;font-weight:700}
.tail{margin-top:12px;font-size:11px;color:#5f5f69;line-height:1.7}
"""


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        print(__doc__); return
    card, res, out = a[0], a[1], a[2]
    ven = a[a.index("--ven") + 1] if "--ven" in a else "川崎"
    date = a[a.index("--date") + 1] if "--date" in a else ""
    rng = a[a.index("--R") + 1] if "--R" in a else "1-12"
    baba = a[a.index("--baba") + 1] if "--baba" in a else None
    lo, _, hi = rng.partition("-")
    lo, hi = int(lo), int(hi or lo)
    global soutei_g
    soutei_g = "--soutei" in a
    global NOTE
    NOTE = {}
    for tok in a:
        if tok.startswith("note:"):
            r_, _, t_ = tok[5:].partition("=")
            NOTE[r_] = t_
    C = json.load(open(card)); R = json.load(open(res))
    body = []
    for k in sorted(C, key=lambda x: C[x]["R"]):
        v = C[k]
        if not (lo <= v["R"] <= hi):
            continue
        rv = R.get(str(v["R"])) or {}
        rr = {x["ub"]: x for x in (rv.get("rows") or [])}
        rows = [prof_row(h, v["dist"], rr.get(h["ub"])) for h in v["horses"]]
        # 終い順位（小さいほど速い）
        for i, r in enumerate(sorted([x for x in rows if x["l"] is not None],
                                     key=lambda x: x["l"]), 1):
            r["srank"] = i
        for r in rows:
            r.setdefault("srank", None)
        soutei = soutei_g
        if soutei:
            f3, base, pc = pace_soutei(dict(v, baba=baba), ven, baba)
        else:
            f3, base, pc = pace_of(dict(rv, dist=v["dist"]), ven)
        cells, NL, SPAN = place(rows)
        ana = set()
        if pc in BAND_OK:
            okb = BAND_OK[pc]
            ana = {r["ub"] for r in rows if band_of(r) in okb
                   and (r["pos"] is None or r["pos"] <= POS_MAX)}
        tag, nm = (LAB if soutei else LAB_J)[pc]
        hh = []
        for r, x, ln in cells:
            col = "#f2d231" if (r["chaku"] or 99) <= 3 else "#d8c7ae"
            wc = WAKU.get(r["waku"], ("#15110d", "#f2f2f4"))
            ex = ""
            if r["gain"] is not None and r["gain"] >= .20:
                ex += '<span class="t up">▲押し上げ</span>'
            elif r["gain"] is not None and r["gain"] <= -.20:
                ex += '<span class="t dn">▼下がる</span>'
            if r["srank"] and r["srank"] <= 3:
                ex += '<span class="sm">終い%d位</span>' % r["srank"]
            if r["jr"] is not None and r["jr"] >= .53:
                ex += '<span class="jin">%s 内%.0f%%</span>' % (html.escape(r["jk"]), r["jr"] * 100)
            elif r["jr"] is not None and r["jr"] <= .40:
                ex += '<span class="jout">%s 内%.0f%%</span>' % (html.escape(r["jk"]), r["jr"] * 100)
            if not r["runs"]:
                ex += '<span class="nx">過去走なし・前後は不明</span>'
            hh.append('<div class="h" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
                      '<div class="lab"><span class="n" style="background:%s;color:%s">%d</span>'
                      '<span class="nm">%s</span></div>'
                      '<span class="ch">%s</span>%s</div>'
                      % (int(x), 10 + ln * LANE, HORSE.format(c=col),
                         CHEV.format(c=col if (r["chaku"] or 99) <= 3 else "#b9b9c4"),
                         wc[0], wc[1], r["ub"], html.escape(r["name"]),
                         ("%d着" % r["chaku"]) if r["chaku"] else "", ex))
        body.append(
            '<div class="race"><div class="rh"><span class="rn">%dR</span>'
            '<span class="rd">ダ<b>%dm</b> ／ %d頭 ／ %s</span>'
            '<span class="pace p-%s"><b>%s</b> %s</span></div>'
            '<div class="pbar p-%s"><div class="gauge"><div class="gz z1">ゆっくり</div>'
            '<div class="gz z2">ふつう</div><div class="gz z3">速い</div>'
            '<div class="gmark" style="left:%d%%"></div></div>'
            '<div class="peff">→ %s<span class="pnum" style="margin:0 0 0 12px">%s</span></div></div>'
            '<div class="track" style="height:%dpx"><div class="goal"></div>%s%s%s</div>'
            '<div class="xlab"><span>後方</span><span>中団</span><span>前　→　ゴール</span></div>%s</div>'
            % (v["R"], v["dist"], len(v["horses"]), html.escape(v.get("cls") or ""),
               (pc or "x"), tag, nm, (pc or "x"),
               {"s": 22, "m": 50, "h": 78}.get(pc, 50),
               {"s": "前に行った馬が<b>そのまま残る</b>",
                "m": "<b>中団から前へ出てくる馬</b>まで",
                "h": "前が<b>垂れる</b>。終いのある馬が届く"}.get(pc, "流れが出せません"),
               ("%s前3F %.1f（%s%dm%sの水準 %.1f）"
                % ("推定" if soutei else "実測", f3, ven, v["dist"],
                   ("・" + baba) if baba else "", base)) if (f3 and base)
               else ("先頭に立つ馬の前半速度が測れないので想定が出せません" if soutei
                     else "ラップが取れていないので流れは測れません"),
               NL * LANE + 16,
               "".join('<div class="bz %s" style="top:%dpx;height:%dpx">'
                       '<span class="bzl">%s</span></div>'
                       % (("zi", "zm", "zo")[b], s_ * LANE + 3, c * LANE - 4,
                          ("内 ラチ沿い", "中", "外")[b])
                       for b, s_, c in SPAN),
               ring(cells, ana), "\n".join(hh),
               ('<div class="view"><h4>見解</h4><p>%s</p></div>' % NOTE[str(v["R"])])
               if str(v["R"]) in NOTE else ""))
    open(out, "w").write(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<title>隊列表</title><style>%s</style></head><body>'
        '<div class="head"><div class="kicker">%s — %s</div>'
        '<h1>隊列表 ── 横は4コーナーの前後、縦は内外</h1>'
        '<div class="sub"><b>縦は枠と騎手で出しています。</b>枠は1枠ずつ '
        '1枠79.8%% / 2枠71.1%% / 3枠60.5%% / 4枠50.9%% / 5枠45.0%% / 6枠34.6%% / 7枠30.8%% / 8枠21.9%% '
        '（4コーナーで併走したとき内にいた割合・南関12,244頭）。'
        '騎手は併走60回以上の人だけ、基準線44.7%%との差を足しています（11,767回・107人）。<br>'
        '<b>赤い囲みが狙う範囲</b> —— <b>スローとミドルは内か中の帯、ハイは中か外の帯</b>で、'
        'どちらも4コーナーの相対0.40まで。'
        '遅い流れの3着内率は 前(0-.2)64.3%% ／ 中前(.2-.4)36.8%% ／ 中(.4-.6)18.9%%。<br>'
        '黄色い馬が3着内。%s</div></div>'
        '%s<div class="tail">印は買い目の保証ではありません。</div></body></html>'
        % (CSS, date, ven,
           ('ペースは<b>走る前の想定</b>です（先頭に立つ3頭の前半速度から推定）。'
            if soutei_g else 'ペースは<b>結果のラップから実測</b>したものです。'),
           "\n".join(body)))
    print("%d鞍 → %s" % (len(body), out))


if __name__ == "__main__":
    main()
