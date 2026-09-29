#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chokyo_dayrank.py の出力を読んでカードにする。

手で数字を書き写すと間違える（3Rの距離を1200と書いてしまった）ので、
出力をそのまま読む。

使い方:
  python3 scripts/chokyo_dayrank.py --date 20260928 --place 船橋 --all > out.txt
  python3 scripts/chokyo_card.py out.txt --title "9/28(月) 船橋" \
      --from-r 6 --to-r 12 --out notes/live/2026-09-28/funabashi_chokyo_6_12.html
"""
from __future__ import annotations
import argparse, os, re

SRCV = "/home/user/keiba/notes/live/2026-08-26/funabashi_baba_manga_1.html"
CSS = """
.box{background:#fff;border:3px solid #111;border-radius:6px;padding:12px 18px 10px;margin:11px 0}
.bt{font-size:29px;font-weight:900;color:#111;border-bottom:5px solid #e8232a;display:inline-block;padding-bottom:2px;margin-bottom:9px}
.r{color:#e8232a;font-weight:900}.b{color:#1f4e9c;font-weight:900}.c{color:#555;font-weight:700}
table.t{width:100%;border-collapse:collapse;font-size:23px}
table.t th{background:#111;color:#fff;font-weight:900;padding:7px 5px;font-size:19px;border:2px solid #111}
table.t td{border:2px solid #ccc;padding:7px 5px;font-weight:800;color:#111;text-align:center;background:#fff}
table.t td.l{text-align:left;font-size:24px}
table.t td.hi{background:#fdeaea;color:#e8232a;font-weight:900}
table.t td.lo{background:#eef1f7;color:#1f4e9c;font-weight:900}
table.t td.gr{background:#f4f4f4;color:#999;font-size:20px}
table.t td.thin{color:#aaa;font-size:20px}
table.t tr.none td{background:#f7f7f7;color:#999}
table.t tr.none td.l{color:#111}
table.t td.lred{background:#f4c4c4;color:#8f1016;font-weight:900}
.warn{background:#ffd400;border:4px solid #111;border-radius:6px;padding:11px 18px;margin:9px 0;
  font-size:22px;font-weight:900;line-height:1.5;color:#111}
.warn b{color:#e8232a}
.rn{font-size:26px;font-weight:900;color:#111;margin:0 0 5px}
.rn span{background:#111;color:#fff;padding:2px 12px;border-radius:4px;margin-right:9px}
</style></head>
"""
MIN_POOL = 20
WARN_COLOR = ('<div class="warn">読み方 ── <b>「追組／流組」を見る。</b>'
              '脚色を無視した「その日全体」は、流した馬が下に沈むだけ。'
              '<b>本数が20を下回る日は灰色</b>にした。'
              '上位4分の1に入った馬は馬名を赤くしてある。時計そのものは出していない。</div>')
WARN_PLAIN = ('<div class="warn">読み方 ── <b>「追組／流組」を見る。</b>'
              '脚色を無視した「その日全体」は、流した馬が下に沈むだけ。'
              '分母が小さい日は順位に意味がないので、頭数を見て判断する。'
              '色は付けていない。時計そのものは出していない。</div>')
HEAD = re.compile(r"^■ (\d+)R (\S+) ── (\d+)頭")
ROW = re.compile(
    r"^\s*(\d+) (.+?)\s+(\d\d/\d\d) (\S+) ([良稍重不]) ／ (\S+?)\s*\(負荷[\d.]+\) ／ "
    r"([追流])組 (\S+)\s+／ その日 (\S+)\s+／ 同脚色 (\S+)\s+／ (\d+)本")
NONE = re.compile(r"^\s*(\d+) (.+?)\s+日付のある追い切りなし")


def parse(path: str):
    races, cur, meta = [], None, ""
    for ln in open(path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        # 日付の見出し。"■ 2R ダ1200 ──" と紛れるので8桁の日付で判定する。
        if re.match(r"^■ \d{8} ", ln):
            meta = ln.lstrip("■ ").strip()
            continue
        m = HEAD.match(ln)
        if m:
            cur = dict(r=int(m.group(1)), dist=m.group(2), n=int(m.group(3)), rows=[])
            races.append(cur)
            continue
        if cur is None:
            continue
        m = NONE.match(ln)
        if m:
            cur["rows"].append(dict(u=int(m.group(1)), nm=m.group(2).strip(), none=True))
            continue
        m = ROW.match(ln)
        if m:
            cur["rows"].append(dict(
                u=int(m.group(1)), nm=m.group(2).strip(), d=m.group(3).lstrip("0").replace("/0", "/"),
                course=m.group(4), baba=m.group(5), kyaku=m.group(6), bk=m.group(7),
                bucket=m.group(8), day=m.group(9), n=int(m.group(11)), none=False))
    return meta, races


def frac(s: str):
    m = re.match(r"^(\d+)/(\d+)$", s)
    return (int(m.group(1)), int(m.group(2))) if m else None


def cls(s: str) -> str:
    f = frac(s)
    if not f:
        return "gr"
    p, n = f
    if n < MIN_POOL:
        return "thin"
    q = (p - 1) / float(n)
    return "hi" if q <= 0.25 else "lo" if q >= 0.75 else ""


def race_block(rc: dict) -> str:
    s = ['<div class="box"><div class="rn"><span>%dR</span>%s ／ %d頭</div>'
         % (rc["r"], rc["dist"], rc["n"])]
    s.append('<table class="t"><tr>'
             '<th style="width:56px">馬番</th><th style="width:300px">馬名</th>'
             '<th style="width:86px">追日</th><th style="width:96px">コース</th>'
             '<th style="width:60px">馬場</th><th style="width:118px">脚色</th>'
             '<th style="width:170px">追組／流組</th><th style="width:150px">その日全体</th>'
             '<th style="width:80px">本数</th></tr>')
    for w in rc["rows"]:
        if w["none"]:
            # 空欄が目立つと、どの馬のデータを持っていないかが外から分かる。
            # 他の行と同じ見た目にして、値だけ伏せる。
            s.append('<tr><td>%d</td><td class="l">%s</td>%s</tr>'
                     % (w["u"], w["nm"], "<td>─</td>" * 7))
            continue
        cb, cd = cls(w["bucket"]), cls(w["day"])
        co = w["course"].replace("船橋", "").replace("調教場", "") or w["course"]
        s.append('<tr><td>%d</td><td class="%s">%s</td><td>%s</td><td>%s</td><td>%s</td>'
                 '<td>%s</td><td class="%s">%s組 %s</td><td class="%s">%s</td>'
                 '<td>%d</td></tr>'
                 % (w["u"], "l lred" if "hi" in (cb, cd) else "l", w["nm"], w["d"], co,
                    w["baba"], w["kyaku"], cb, w["bk"], w["bucket"], cd, w["day"], w["n"]))
    s.append("</table></div>")
    return "".join(s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--no-color", action="store_true",
                    help="赤・青を付けず、数字だけ並べる")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-r", type=int, default=1)
    ap.add_argument("--to-r", type=int, default=12)
    a = ap.parse_args()
    if a.no_color:
        global cls
        cls = lambda s: ""
    meta, races = parse(a.src)
    use = [r for r in races if a.from_r <= r["r"] <= a.to_r]
    if not use:
        raise SystemExit("該当レースなし")
    head = open(SRCV, encoding="utf-8").read().split("</style>")[0] + CSS
    html = (head +
            '<body><div class="card"><div class="lines"></div><div class="tone"></div>'
            '<div class="inner">\n'
            '<div class="kicker">変態か、変態以外か。 ── AIズブ穴</div>\n'
            '<div class="head"><div class="gekiga">調</div>'
            '<div class="dateblk"><div class="d1">%s %dR〜%dR ── 調教</div>'
            '<div class="d2">追った日ごとに順位 ／ %s</div></div>'
            '<div class="burst"><span>日ごとの<br>順位</span></div></div>\n'
            % (a.title, use[0]["r"], use[-1]["r"], meta)
            + (WARN_PLAIN if a.no_color else WARN_COLOR)
            + "".join(race_block(r) for r in use)
            + "</div></div></body></html>")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    print("%s ／ %dR〜%dR ／ %d頭"
          % (a.out, use[0]["r"], use[-1]["r"], sum(len(r["rows"]) for r in use)))


if __name__ == "__main__":
    main()
