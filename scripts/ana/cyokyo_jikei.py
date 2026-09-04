#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""調教を【時系列】で並べる ── 状態が上がってきている馬を探す。

既存の cyokyo2.py / cyokyo_ana.py は【最新の1本】しか見ていない。
だが知りたいのは1本の良し悪しではなく、**変化の向き**。

    「未来を予想するということは、馬の状態が上がっている馬を探す作業でもある」

そのために全本数を日付順に並べ、末3Fの推移・脚色の推移・併せの結果を並走させる。

★いちばん大事な交絡（返し馬の強度と同じ罠）:
  **強く追えば時計は速くなる。**
  だから「脚色を上げて時計が縮んだ」は、ほぼ当たり前で情報が薄い。
  価値があるのは【同じ脚色のまま時計が縮んだ】ほう。手応えが変わっている。
  本ツールはこの2つを別々に表示し、前者を ○、後者を ★ で区別する。

読み方:
    本数    … 乗り込み量。間隔が空いた馬は本数で仕上がりを補う
    末3F   … 締めの3F。小さいほど速い
    脚色    … 馬なり/余力 < 強め < 一杯。追った強さ
    併せ    … 遅れ < 同入 < 先着
    ■/◇   … 競馬ブックの直近週/前週マーク（拾えた場合）

使い方:
    python3 scripts/ana/cyokyo_jikei.py 2026090521150601
    python3 scripts/ana/cyokyo_jikei.py <rid> --up          # 上げてきている馬だけ
    python3 scripts/ana/cyokyo_jikei.py <rid> --horse ウマノナマエ

前提:
    scripts/ana/kb.conf（競馬ブックのcookie）が要る。無いと302で弾かれる。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

SP = os.path.dirname(os.path.abspath(__file__))
ARC = os.path.join(SP, "arc")
CONF = os.path.join(SP, "kb.conf")
BASE = "https://p.keibabook.co.jp"

# 脚色の強さ。数字が大きいほど強く追っている
ASHI = [("一杯", 3), ("強目", 2), ("強め", 2), ("馬なり", 1), ("馬也", 1), ("余力", 1)]
# 併せ馬の結果
AWASE = [("先着", 1), ("同入", 0), ("遅れ", -1)]

HEAD = re.compile(
    r'<td class="umaban">(\d+)</td>\s*<td class="kbamei"><a[^>]*>([^<]+)</a></td>'
    r'\s*<td class="tanpyo">([^<]*)</td>\s*<td class="yajirusi"><span[^>]*>([^<]*)</span>')
DATE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:\(([月火水木金土日])\))?")


def fetch(rid, force=False):
    os.makedirs(ARC, exist_ok=True)
    out = os.path.join(ARC, f"cyo_{rid}.html")
    if force or not os.path.exists(out) or os.path.getsize(out) < 2000:
        if not os.path.exists(CONF):
            sys.exit(f"× {CONF} がありません。競馬ブックのcookieを置いてください。")
        subprocess.run(["curl", "-s", "-L", "-K", CONF, f"{BASE}/chihou/cyokyo/1/0/{rid}",
                        "-o", out], check=False)
    h = open(out, encoding="utf-8", errors="replace").read()
    if "umaban" not in h:
        sys.exit("× 調教データが取れていません。ログインが切れている可能性があります"
                 f"（{out} を確認）。")
    return h


def rank(text, table):
    for k, v in table:
        if k in text:
            return k, v
    return None, None


def rows_of(seg):
    """1頭ぶんの断片から、追い切り1本ずつを日付順に取り出す。"""
    cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
             for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S)]
    idx = [i for i, c in enumerate(cells) if DATE.match(c)]
    out = []
    for k, i in enumerate(idx):
        blk = cells[i: idx[k + 1] if k + 1 < len(idx) else min(i + 18, len(cells))]
        m = DATE.match(blk[0])
        joined = " ".join(blk)
        # 時計。累積(5F→4F→3F)は20秒以上、1Fは20秒未満
        t = [float(x) for x in re.findall(r"\b(\d{2,3}\.\d)\b", joined)]
        cum = sorted([x for x in t if x >= 20], reverse=True)
        f1 = min([x for x in t if x < 20], default=None)
        ash, av = rank(joined, ASHI)
        aw, wv = rank(joined, AWASE)
        note = next((c for c in blk[1:] if len(c) >= 4
                     and not re.search(r"\d\.\d", c)
                     and not re.match(r"^[0-9/()]+$", c)), "")
        out.append(dict(mm=int(m.group(1)), dd=int(m.group(2)), yobi=m.group(3) or "",
                        course=blk[1] if len(blk) > 1 else "", baba=blk[2] if len(blk) > 2 else "",
                        cum=cum, f3=(cum[-1] if cum else None), f1=f1,
                        ashi=ash, av=av, awase=aw, wv=wv, note=note[:22],
                        mark=("■" if "■" in joined else ("◇" if "◇" in joined else " ")),
                        load=("☆" if "☆" in joined else " ")))
    # 月をまたぐ並べ替え（12月→1月の折り返しを吸収）
    if out and max(r["mm"] for r in out) - min(r["mm"] for r in out) > 6:
        for r in out:
            if r["mm"] <= 6:
                r["mm"] += 12
    out.sort(key=lambda r: (r["mm"], r["dd"]))
    for r in out:
        r["mm"] = (r["mm"] - 1) % 12 + 1
    return out


def parse(rid, force=False):
    h = fetch(rid, force)
    heads = list(HEAD.finditer(h))
    out = {}
    for i, m in enumerate(heads):
        seg = h[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(h)]
        out[int(m.group(1))] = dict(
            name=m.group(2), soukan=m.group(3).strip(), arrow=m.group(4).strip(),
            rows=rows_of(seg))
    return out


def trend(rows):
    """変化の向き。★＝同じ脚色で時計が縮んだ（手応えが変わった） ○＝追って縮んだ"""
    ok = [r for r in rows if r["f3"]]
    if len(ok) < 2:
        return None, "本数不足"
    d3 = ok[-1]["f3"] - ok[0]["f3"]
    da = (ok[-1]["av"] or 0) - (ok[0]["av"] or 0)
    dw = (ok[-1]["wv"] if ok[-1]["wv"] is not None else 0) - \
         (ok[0]["wv"] if ok[0]["wv"] is not None else 0)
    if d3 <= -0.5 and da <= 0:
        return "★", f"同じ脚色のまま末3Fが {abs(d3):.1f}秒 縮んだ"
    if d3 <= -0.5 and da > 0:
        return "○", f"追って {abs(d3):.1f}秒 縮んだ（強度を上げた分は割り引く）"
    if d3 >= 0.5 and da >= 0:
        return "▽", f"強く追っているのに {d3:.1f}秒 かかっている"
    if dw > 0:
        return "○", "時計は横ばいだが併せの結果が良化"
    return "－", f"横ばい（末3F {d3:+.1f}秒）"


def show(ub, h, verbose=True):
    mk, why = trend(h["rows"])
    head = f"{ub:>2}番 {h['name']:<14}"
    if h["soukan"]:
        head += f" 総評:{h['soukan']}"
    if h["arrow"]:
        head += f" 矢印:{h['arrow']}"
    print(head)
    if verbose:
        for r in h["rows"]:
            t = "  ".join(f"{v:.1f}" for v in r["cum"]) or "—"
            one = f"{r['f1']:.1f}" if r["f1"] else "—"
            print(f"   {r['mark']}{r['load']} {r['mm']:>2}/{r['dd']:<2}({r['yobi'] or '?'}) "
                  f"{r['course'][:8]:<8}{r['baba'][:2]:<3}{t:<24}{one:>5}  "
                  f"{(r['ashi'] or '—'):<5}{(r['awase'] or ''):<4}{r['note']}")
    n = len(h["rows"])
    print(f"   └ {n}本   {mk or ' '} {why}\n")


def main():
    ap = argparse.ArgumentParser(description="調教を時系列で並べ、上げてきている馬を探す")
    ap.add_argument("rid", help="競馬ブックのレースID")
    ap.add_argument("--horse")
    ap.add_argument("--up", action="store_true", help="★ か ○ の馬だけ")
    ap.add_argument("--brief", action="store_true", help="明細を省いて結論だけ")
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して取り直す")
    a = ap.parse_args()

    D = parse(a.rid, a.force)
    print(f"■ {a.rid}   {len(D)}頭\n")
    print("  ★＝同じ脚色のまま時計が縮んだ（手応えが変わった）")
    print("  ○＝追って縮んだ／併せが良化   ▽＝強く追っても時計がかかる   －＝横ばい\n")
    for ub in sorted(D):
        h = D[ub]
        if a.horse and a.horse not in h["name"]:
            continue
        if a.up and (trend(h["rows"])[0] not in ("★", "○")):
            continue
        show(ub, h, verbose=not a.brief)
    print("  ※【強く追えば時計は速くなる】。だから ○ より ★ のほうが情報として強い。")
    print("    返し馬の強度を先に記録するのと同じ理由です。")


if __name__ == "__main__":
    main()
