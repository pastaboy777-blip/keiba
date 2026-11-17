"""狙い ── 隊列図の読み方を、そのまま手順にしたもの（2026-11-17 にユーザーと決めた形）。

  python3 nerai.py <hyo.txt> [<hyo.txt> ...]
  python3 nerai.py <出力ディレクトリ>        # 中の r*/hyo.txt をまとめて読む

★ このスクリプトは **何も取りに行かないし、図も作らない**。
  `tojitsu.py` が出した `hyo.txt` を読んで、帯に分けて並べ替えるだけ。
  既存のツールの挙動は1バイトも変えていない（ルール20★・31★）。

── 手順（ユーザーが決めた4つ）

  ① 2枚目（直線の図）を3等分して帯を作る
     ＝ hyo.txt の「4角」の列で並べて、鞍の中で前／中／後ろに3等分する。
       直線の図はこの4角の値で隊列を組んでいるので、列を並べ替えるのと同じこと。
  ② 「終い◯位」の札が3位以内の馬だけ拾う
  ③ 前の帯のものが軸候補、中の帯のものが相手
  ④ 後ろの帯で終い札なしは全部消す

── なぜ「帯」なのか（2026-11-17 大井・12鞍／図の数字が取れた11鞍140頭）

  図が予想した4角と実際の4角のずれは **平均0.235**（13頭立てで±3着順）。
  図の4角1位が実際の1番手だったのは **4/11**。
  → **何番目かは当たらない。前か後ろかは分かる。** だから帯で読む。

  帯だけでは効かない ── 前26.0%(50中13) ／ 中**29.8%**(47中14) ／ 後ろ11.6%(43中5)。
  **前と中が逆転している。**

  終いの札と掛け合わせて初めて効く（基準22.9%）

      前の帯 × 札あり  **58.3%**(12中7)      前の帯 × 札なし 15.8%(38中6)
      中の帯 × 札あり    44.4%(9中4)        中の帯 × 札なし 26.3%(38中10)
      後ろ   × 札あり    25.0%(12中3)        後ろ   × 札なし **6.5%**(31中2)

  実際に走った位置で見ると、4角0.2以内×上がり3位以内が **10頭中10頭**、
  4角0.2超×上がり4位以下が **74頭中0頭**。
  図の予想がずれる分だけ 58.3%／6.5% に薄まっている、という関係。

── ★ いちばん効いた条件 ──「軸候補が1頭に絞れた鞍だけ買う」

  1頭の鞍 … 1R⑥・5R⑧・8R⑥・10R⑤・11R①・12R⑬ → **6鞍中5鞍で3着内**
  2頭の鞍 … 4R・7R・9R → 3鞍中2鞍（9Rは2頭とも外れ）
  0頭の鞍 … 2R・6R → 買わない

  2頭出てきた鞍は「どちらが来るか読めていない」ということ。
  表裏を取るか見送る（ルール8・35）。

★★ **これは 2026-11-17 の1日・11鞍140頭の数字で、しかも結果を見たあとに区切りを決めている。**
  明日同じに出る保証はない。何日か同じ手順で出して突き合わせるところから。
  **測るかどうかはユーザーが決める**（CLAUDE.md ★★★ 最優先）。

標準ライブラリのみ。
"""
import os
import re
import sys

# hyo.txt の1行。馬番 枠 馬名 騎手 人気 単勝 体重 平均差 増減 1角 gain 4角 内度 終い 印
ROW = re.compile(
    r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+"      # 馬番 枠 馬名 騎手 人気 単勝
    r"\S+\s+\S+\s+\S+\s+"                                        # 体重 平均差 増減
    r"([\d.]+|-)\s+([+\-][\d.]+|-)\s+([\d.]+|-)\s+([\d.]+)\s+"   # 1角 gain 4角 内度
    r"(\d+|-)"                                                   # 終い
)
HEAD = re.compile(r"━━\s*(\d+)R\s+(\S+)")

SHIMAI_MAX = 3      # 「終い◯位」の札を拾う上限（手順②）


def load(path):
    """hyo.txt を読む -> (見出し, [馬])。馬は dict。"""
    title, rows = None, []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if title is None:
                m = HEAD.search(ln)
                if m:
                    title = ln.strip().lstrip("━").strip()
                    continue
            m = ROW.match(ln)
            if not m:
                continue
            g = m.groups()
            rows.append({
                "ub": int(g[0]), "waku": int(g[1]), "name": g[2],
                "jk": g[3], "nin": g[4], "odds": g[5],
                "c1": None if g[6] == "-" else float(g[6]),
                "gain": None if g[7] == "-" else float(g[7]),
                "c4": None if g[8] == "-" else float(g[8]),
                "uchi": float(g[9]),
                "shimai": None if g[10] == "-" else int(g[10]),
            })
    return title, rows


def bands(rows):
    """手順① ── 4角で並べて鞍の中で3等分。4角が無い馬（過去走なし）は別に返す。"""
    have = sorted((r for r in rows if r["c4"] is not None), key=lambda r: r["c4"])
    none = [r for r in rows if r["c4"] is None]
    n = len(have)
    out = ([], [], [])
    for i, r in enumerate(have):
        out[0 if i < n / 3 else (1 if i < 2 * n / 3 else 2)].append(r)
    return out, none


def shimai(r):
    """手順② ── 終いの札が3位以内か。"""
    return r["shimai"] is not None and r["shimai"] <= SHIMAI_MAX


def fmt(r):
    s = "%2d %-9s %s" % (r["ub"], r["name"][:9], ("%s人気 %s倍" % (r["nin"], r["odds"]))
                         if r["nin"] not in ("-", "None") else "")
    if r["c4"] is not None:
        s += "  4角%.2f" % r["c4"]
    if r["shimai"]:
        s += " 終い%d位" % r["shimai"]
    if r["gain"] is not None and r["gain"] >= 0.10:
        s += " ▲押し上げ"
    if r["gain"] is not None and r["gain"] <= -0.10:
        s += " ▼下がる"
    return s


def one(path):
    title, rows = load(path)
    if not rows:
        print("  （%s に馬の行が無い）" % path)
        return
    (mae, naka, ushiro), nopast = bands(rows)
    print("━━ %s" % (title or os.path.basename(path)))

    jiku = [r for r in mae if shimai(r)]
    aite = [r for r in naka if shimai(r)]
    keshi = [r for r in ushiro if not shimai(r)]
    nokori = [r for r in (mae + naka + ushiro)
              if r not in jiku and r not in aite and r not in keshi]

    print("  ③ 軸候補（前の帯 × 終い3位以内）")
    for r in jiku or []:
        print("       " + fmt(r))
    if not jiku:
        print("       なし ── この鞍は買わない")
    elif len(jiku) == 1:
        print("       → 1頭に絞れた。ここが狙いどころ")
    else:
        print("       → %d頭。どちらが来るかは読めていない。表裏を取るか見送る" % len(jiku))

    print("  ③ 相手（中の帯 × 終い3位以内）")
    for r in aite:
        print("       " + fmt(r))
    if not aite:
        print("       なし")

    if nopast:
        print("  ※ 過去走なし（位置が測れない。調教で見る ── ルール48）")
        for r in nopast:
            print("       " + fmt(r))

    print("  ④ 消し（後ろの帯 × 終いの札なし）")
    print("       " + (" ".join("%d%s" % (r["ub"], r["name"][:6]) for r in keshi)
                       if keshi else "なし"))
    if nokori:
        print("  －  残り（買いでも消しでもない）")
        print("       " + " ".join("%d%s" % (r["ub"], r["name"][:6]) for r in nokori))
    print()


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    paths = []
    for a in args:
        if os.path.isdir(a):
            for dp, _, fs in os.walk(a):
                if "hyo.txt" in fs:
                    paths.append(os.path.join(dp, "hyo.txt"))
        else:
            paths.append(a)
    if not paths:
        print("hyo.txt が見つからない")
        return

    def key(p):
        m = re.search(r"r(\d+)", p)
        return (int(m.group(1)) if m else 0, p)

    for p in sorted(set(paths), key=key):
        one(p)


if __name__ == "__main__":
    main()
