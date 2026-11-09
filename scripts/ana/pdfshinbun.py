"""PDF新聞（鈴木ショータ）から、基準タイムとレース情報を抜く。

  python3 pdfshinbun.py <紙面.pdf>              # その日の各鞍を一覧
  python3 pdfshinbun.py <紙面.pdf> --save       # 基準タイムを kijun.json に貯める
  python3 pdfshinbun.py --kijun                 # 貯めた基準タイムの表を出す
  python3 pdfshinbun.py <紙面.pdf> --level      # レベル↔タイム指数の対応を集計

pdftotext -layout でテキストにしてから読む。紙面のヘッダはこの形で出る。

    10/22(木)
    ２歳(五)                                  ← クラス
                 12:20        超低レベル        ← 発走時刻 と その日の予想レベル
    浦和 1 ダ1400m 1:31.6(良馬場平均タイム）    ← 場・R・距離・良馬場平均タイム
                 前半38.0-上がり40.1           ← 平均の前半3F と 平均上がり3F

ここから計算できるもの（notes/live/pdf_shinbun_bachu.md 参照）

    基準の前半   = 良馬場平均タイム − 平均上がり3F
    ペース指数   = (実測の前半タイム − 基準の前半) × 10
    平均33ラップ = 平均の前半3F − 平均上がり3F
    タイム指数   = (基準タイム − 走破タイム) × 10

★「レベル」はタイム指数の水準を6段階に切ったもの（10/22の紙面372件で確認）
  ハイ 51 / やハ 39 / 水準 37 / や低 31 / 低 22.5 / 超低 11（いずれも中央値）
  一段あたり 0.6〜1.2秒。前走のレベルを自前で出すには、その日の基準が要る。
  この kijun.json を日々貯めれば、場×距離×クラスの基準表が埋まっていく。
"""
import sys, os, re, json, subprocess, statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
KIJUN = os.path.join(HERE, "kijun.json")
JYO = ("浦和|川崎|船橋|大井|門別|笠松|園田|金沢|高知|佐賀|盛岡|水沢|名古屋|姫路"
       "|中京|東京|中山|阪神|京都|新潟|小倉|福島|札幌|函館")
LV = ["超ハ", "ハイ", "やハ", "や低", "超低", "低"]      # 長いものから判定する


def totext(pdf):
    out = "/tmp/pdfshinbun.txt"
    subprocess.run(["pdftotext", "-layout", pdf, out], check=True)
    return open(out, encoding="utf-8", errors="replace").read().split("\n")


def sec(t):
    if ":" in t:
        m, s = t.split(":")
        return int(m) * 60 + float(s)
    return float(t)


def races(lines):
    """その日の各鞍のヘッダを拾う"""
    out = []
    hdr = re.compile(r"(%s)\s+(\d+)\s+(ダ|芝)(\d+)m\s+([\d:.]+)\(良馬場平均タイム" % JYO)
    for i, ln in enumerate(lines):
        m = hdr.search(ln)
        if not m:
            continue
        r = {"track": m.group(1), "R": int(m.group(2)), "surface": m.group(3),
             "dist": int(m.group(4)), "avg": sec(m.group(5))}
        for j in range(i, min(i + 5, len(lines))):      # 前半/上がりは1〜2行下
            mm = re.search(r"前半([\d.]+)-上がり([\d.]+)", lines[j])
            if mm:
                r["zen3"], r["ag3"] = float(mm.group(1)), float(mm.group(2))
                break
        # ヘッダの上に 日付 → (2行) → クラス → 発走時刻+予想レベル、の順で並ぶ
        for j in range(max(0, i - 8), i):
            mt = re.search(r"(\d+:\d\d)", lines[j])
            if mt: r["start"] = mt.group(1)
            ml = re.search(r"(超ハ|ハイ|やハ|や低|超低|低)レベル", lines[j])
            if ml: r["level"] = ml.group(1)
            md = re.search(r"(\d+/\d+)\(.\)", lines[j])
            if md:
                r["date"] = md.group(1)
                if j + 2 < len(lines):
                    # 右側の欄が同じ行に続くので、最初の空白2つ以上で切る
                    r["cls"] = re.split(r"\s{2,}", lines[j + 2].strip())[0]
        out.append(r)
    return out


def level_pairs(lines):
    """過去走の「タイム指数/レース総評」を拾って、レベルごとの指数分布を出す"""
    idx = re.compile(r"(-?\d+)/([^\s]+)")
    g = defaultdict(list)
    for ln in lines:
        for m in idx.finditer(ln):
            s = m.group(2)
            if re.match(r"^\d", s):
                continue
            lv = next((x for x in LV if s.startswith(x)), "水準")
            g[lv].append(int(m.group(1)))
    return g


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    store = json.load(open(KIJUN)) if os.path.exists(KIJUN) else {}

    if "--kijun" in sys.argv and not args:
        print("貯めてある基準タイム（場 距離 クラス → 良馬場平均 / 前半3F / 上がり3F）")
        for k in sorted(store):
            v = store[k]
            print("  %-26s 平均%7.1f  前半%5.1f  上がり%5.1f  → 基準前半%6.2f  平均33ラップ%+5.1f"
                  % (k, v["avg"], v["zen3"], v["ag3"], v["avg"] - v["ag3"], v["zen3"] - v["ag3"]))
        return

    if not args:
        print(__doc__); return
    lines = totext(args[0])
    rs = races(lines)
    if not rs:
        print("レースのヘッダが見つかりません。pdftotext の出力を確認してください。")
        return

    print("  日付     R  距離   良馬場平均  前半3F 上3F  基準前半  平均33ラップ  予想レベル  クラス")
    for r in sorted(rs, key=lambda x: x["R"]):
        if "zen3" not in r:
            continue
        print("  %-7s %2d %4d%s  %8.1f %6.1f %5.1f %8.2f %+10.1f   %-6s %s"
              % (r.get("date", "?"), r["R"], r["dist"], r["surface"], r["avg"],
                 r["zen3"], r["ag3"], r["avg"] - r["ag3"], r["zen3"] - r["ag3"],
                 r.get("level", "水準"), (r.get("cls") or "")[:22]))

    if "--level" in sys.argv:
        g = level_pairs(lines)
        print("\n  レベル別 タイム指数（この紙面の過去走すべて）")
        print("  %-5s %6s %8s %8s %8s" % ("レベル", "件数", "中央値", "下位1/4", "上位1/4"))
        for lv in ["超ハ", "ハイ", "やハ", "水準", "や低", "低", "超低"]:
            v = sorted(g.get(lv, []))
            if len(v) < 3:
                continue
            print("  %-5s %6d %8.1f %8d %8d"
                  % (lv, len(v), st.median(v), v[len(v) // 4], v[3 * len(v) // 4]))

    if "--save" in sys.argv:
        n = 0
        for r in rs:
            if "zen3" not in r:
                continue
            k = "%s %d%s %s" % (r["track"], r["dist"], r["surface"], (r.get("cls") or "?")[:18])
            store[k] = {"avg": r["avg"], "zen3": r["zen3"], "ag3": r["ag3"],
                        "date": r.get("date"), "level": r.get("level")}
            n += 1
        json.dump(store, open(KIJUN, "w"), ensure_ascii=False, indent=1)
        print("\n基準タイムを %d件 保存しました（累計 %d件）→ %s" % (n, len(store), KIJUN))


if __name__ == "__main__":
    main()
