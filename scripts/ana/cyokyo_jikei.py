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

★残っている弱点（読むときに割り引くこと）:
  末3F は「累積タイムのいちばん小さい値」で拾っている。
  だが追い切りの距離は毎回同じではないので、5F追いの3F(37秒台)と
  4F追いの4F(45秒台)を並べてしまう回がある。
  **3〜4秒級の変化が出たら、まず距離違いを疑う。**明細を目で見て確認すること。

使い方:
    python3 scripts/ana/cyokyo_jikei.py 2026131005100904
    python3 scripts/ana/cyokyo_jikei.py <rid> --back 5      # ★過去5走ぶんを繋ぐ
    python3 scripts/ana/cyokyo_jikei.py <rid> --back 5 --up # 上げてきている馬だけ
    python3 scripts/ana/cyokyo_jikei.py <rid> --brief       # 結論だけ

URL（2026-09時点）:
    調教   /chihou/cyokyo/1/0/{rid}   ※提供のある会場だけ。無いと302で出馬表へ
    馬     /db/uma/{umacd}            過去走のレースIDが取れる
レースIDは 年(4)+開催コード(6)+R(2)+MMDD(4)。**真ん中は日付順ではない**ので
文字列比較で並べてはいけない（ymd() を使う）。

前提:
    scripts/ana/kb.conf（競馬ブックのcookie）が要る。無いと302で弾かれる。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
import sys

SP = os.path.dirname(os.path.abspath(__file__))
ARC = os.path.join(SP, "arc")
CONF = os.path.join(SP, "kb.conf")
BASE = "https://p.keibabook.co.jp"

# 脚色の強さ。数字が大きいほど強く追っている
ASHI = [("一杯", 3), ("強目", 2), ("強め", 2), ("馬なり", 1), ("馬也", 1), ("余力", 1)]
# 併せ馬の結果
AWASE = [("先着", 1), ("同入", 0), ("遅れ", -1)]
# 傾きを見る窓。直近この本数だけで判定する（半年前と比べても意味がない）
WINDOW = 4

HEAD = re.compile(
    r'<td class="umaban">(\d+)</td>\s*<td class="kbamei"><a[^>]*>([^<]+)</a></td>'
    r'\s*<td class="tanpyo">([^<]*)</td>\s*<td class="yajirusi"><span[^>]*>([^<]*)</span>')
UMACD = re.compile(r'<td class="umaban">(\d+)</td>.{0,600}?umacd="(\d+)"', re.S)
PASTID = re.compile(r'href="/(?:chihou|cyuou)/seiseki/(\d{16})"')
DATE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:\(([月火水木金土日])\))?")

# コースの系統。坂路と周回コースは時計のスケールが違うので絶対に混ぜない
def kind(course):
    c = course or ""
    if "坂" in c:
        return "坂路"
    if "プール" in c or "游" in c:
        return "プール"
    return "コース"


def get(url, out, force=False, minsize=2000):
    os.makedirs(ARC, exist_ok=True)
    if force or not os.path.exists(out) or os.path.getsize(out) < minsize:
        if not os.path.exists(CONF):
            sys.exit(f"× {CONF} がありません。競馬ブックのcookieを置いてください。")
        subprocess.run(["curl", "-s", "-L", "-K", CONF, url, "-o", out], check=False)
        time.sleep(0.4)                       # 相手方に負荷をかけない
    if not os.path.exists(out):               # 提供の無いページは空で返る
        return ""
    return open(out, encoding="utf-8", errors="replace").read()


def fetch(rid, force=False):
    h = get(f"{BASE}/chihou/cyokyo/1/0/{rid}", os.path.join(ARC, f"cyo_{rid}.html"), force)
    if "umaban" not in h:
        return None                            # 調教の提供が無いレース
    return h


def ymd(rid):
    """レースIDから開催日を取り出す。★並べ替えのキー。

    IDは 年(4) + 開催コード(6) + R(2) + MMDD(4)。
    真ん中の開催コードは日付順ではないので、IDの文字列比較で並べてはいけない。
    """
    return rid[:4] + rid[12:16]


def past_rids(umacd, n, before):
    """その馬の過去走のレースIDを、新しい順に n 本。before の日より前のものだけ。"""
    h = get(f"{BASE}/db/uma/{umacd}", os.path.join(ARC, f"uma_{umacd}.html"), minsize=20000)
    ids = sorted(set(PASTID.findall(h)), key=ymd, reverse=True)
    b = ymd(before)
    return [r for r in ids if ymd(r) < b][:n]


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
    if h is None:
        return {}
    cd = {int(a): b for a, b in UMACD.findall(h)}
    heads = list(HEAD.finditer(h))
    out = {}
    for i, m in enumerate(heads):
        seg = h[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(h)]
        ub = int(m.group(1))
        out[ub] = dict(name=m.group(2), soukan=m.group(3).strip(),
                       arrow=m.group(4).strip(), umacd=cd.get(ub), rows=rows_of(seg))
    return out


CARD = re.compile(
    r'<td class="umaban">(\d+)</td>.{0,1200}?<a href="/db/uma/(\d+)"[^>]*>([^<]+)</a>', re.S)


def card_runners(rid):
    """出馬表から出走馬を取る。

    ★今走の調教がまだ公開されていない開催でも、出馬表は先に出る。
      だから「月曜出走の馬の、過去5走の調教」は今日のうちに集められる。
    """
    h = get(f"{BASE}/chihou/syutuba/{rid}", os.path.join(ARC, f"syu_{rid}.html"))
    out = {}
    for ub, cd, nm in CARD.findall(h):
        out.setdefault(int(ub), dict(name=nm.strip(), umacd=cd, soukan="", arrow="", rows=[]))
    return out


def with_history(rid, back, force=False):
    """今走の調教に、過去 back 走ぶんの調教を継ぎ足して1本の時系列にする。

    1レースぶんの調教ページには直近1〜3本しか載らない。
    「状態が上がってきているか」を見るには、走ごとの仕上げを並べる必要がある。
    """
    cur = parse(rid, force)
    if not cur:                        # 今走の調教がまだ出ていない開催
        cur = card_runners(rid)
    for ub, h in sorted(cur.items()):
        h["rows"] = [dict(r, rid=rid, cur=True) for r in h["rows"]]
        if not h["umacd"]:
            continue
        for pr in past_rids(h["umacd"], back, rid):
            p = parse(pr)
            me = next((q for q in p.values() if q["name"] == h["name"]), None)
            if me:
                h["rows"] += [dict(r, rid=pr, cur=False) for r in me["rows"]]
        h["rows"] = order(h["rows"])
    return cur


def order(rows):
    """走をまたいで日付順に。年をまたぐ折り返しは、レースIDの年で解決する。"""
    for r in rows:
        y = int(r.get("rid", "0000")[:4] or 0)
        # 調教は開催の1〜2か月前まで。開催が1〜2月で調教が11〜12月なら前年
        rm = int(r.get("rid", "00000000000000")[12:14] or 0)
        r["_y"] = y - 1 if (rm and rm <= 2 and r["mm"] >= 11) else y
    rows.sort(key=lambda r: (r["_y"], r["mm"], r["dd"]))
    return rows


def trend(rows):
    """変化の向き。★＝同じ脚色で時計が縮んだ（手応えが変わった） ○＝追って縮んだ

    ★坂路と周回コースは時計のスケールがまるで違うので、必ず同じ系統の中だけで比べる。
      （混ぜると 坂路24.9 → コース38.3 を「13秒悪化」と読んでしまう）
    """
    best = (None, "本数不足")
    for k in ("コース", "坂路"):
        ok = [r for r in rows if r["f3"] and kind(r["course"]) == k]
        # ★直近だけを見る。半年前と比べても「状態が上がっている」の答えにならない
        ok = ok[-WINDOW:]
        if len(ok) < 2:
            continue
        d3 = ok[-1]["f3"] - ok[0]["f3"]
        da = (ok[-1]["av"] or 0) - (ok[0]["av"] or 0)
        dw = (ok[-1]["wv"] if ok[-1]["wv"] is not None else 0) - \
             (ok[0]["wv"] if ok[0]["wv"] is not None else 0)
        n = f"{k}{len(ok)}本"
        if d3 <= -0.5 and da <= 0:
            return "★", f"{n} 同じ脚色のまま末3Fが {abs(d3):.1f}秒 縮んだ"
        if d3 <= -0.5 and da > 0:
            cand = ("○", f"{n} 追って {abs(d3):.1f}秒 縮んだ（強度の分は割り引く）")
        elif d3 >= 0.5 and da >= 0:
            cand = ("▽", f"{n} 強く追っているのに {d3:.1f}秒 かかっている")
        elif dw > 0:
            cand = ("○", f"{n} 時計は横ばいだが併せの結果が良化")
        else:
            cand = ("－", f"{n} 横ばい（末3F {d3:+.1f}秒）")
        if best[0] is None or cand[0] in ("★", "○"):
            best = cand
    return best


def show(ub, h, verbose=True):
    mk, why = trend(h["rows"])
    head = f"{ub:>2}番 {h['name']:<14}"
    if h["soukan"]:
        head += f" 総評:{h['soukan']}"
    if h["arrow"]:
        head += f" 矢印:{h['arrow']}"
    print(head)
    if verbose:
        prev = None
        for r in h["rows"]:
            if prev and r.get("rid") != prev:
                print("   " + "·" * 68)          # 走の切れ目
            prev = r.get("rid")
            t = "  ".join(f"{v:.1f}" for v in r["cum"]) or "—"
            one = f"{r['f1']:.1f}" if r["f1"] else "—"
            print(f"   {r['mark']}{r['load']}{'*' if r.get('cur') else ' '}"
                  f"{r.get('_y', 0) % 100:>3}/{r['mm']:>2}/{r['dd']:<2}({r['yobi'] or '?'}) "
                  f"{r['course'][:7]:<7}{r['baba'][:2]:<3}{t:<22}{one:>5}  "
                  f"{(r['ashi'] or '—'):<5}{(r['awase'] or ''):<4}{r['note']}")
    n = len(h["rows"])
    print(f"   └ {n}本   {mk or ' '} {why}\n")


def main():
    ap = argparse.ArgumentParser(description="調教を時系列で並べ、上げてきている馬を探す")
    ap.add_argument("rid", help="競馬ブックのレースID")
    ap.add_argument("--horse")
    ap.add_argument("--back", type=int, default=0,
                    help="過去何走ぶんの調教を継ぎ足すか（例 5）")
    ap.add_argument("--up", action="store_true", help="★ か ○ の馬だけ")
    ap.add_argument("--brief", action="store_true", help="明細を省いて結論だけ")
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して取り直す")
    a = ap.parse_args()

    if a.back:
        print(f"  過去{a.back}走ぶんを取得中（初回はキャッシュが無いので時間がかかります）…")
        D = with_history(a.rid, a.back, a.force)
    else:
        D = parse(a.rid, a.force)
        for h in D.values():
            h["rows"] = [dict(r, cur=True) for r in h["rows"]]
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
