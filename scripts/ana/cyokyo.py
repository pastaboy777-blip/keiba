"""競馬ブックの調教ページを読む（kb.conf のcookieが要る）。

  python3 cyokyo.py 2026101305 1023 1 2 3 4 5 6   # rid頭10桁 日付4桁 R...
  python3 cyokyo.py 2026101305 1023 --all         # 1R〜12R
  python3 cyokyo.py 2026171001 1116 --all --json cyokyo1116.json
      ↑ 鞍→馬番で引ける形で保存する。`tenkai_zu.py --cyokyo <json>` に渡すと
        図に「調子上向き」「追い切りなし」の札が出る（CLAUDE.md ルール48）。

取れるもの（1頭ぶん）
  追い切り短評 … 「攻め強化」「多少上向く」など、競馬ブックの一言
  矢印        … ↑ → ↓（競馬ブックの上昇/平行/下降）
  1本ずつの時計 … 日付・コース・馬場・各ハロンの時計・脚色・短評
  ★ 日付の頭の「*」= その馬の調教が11日以上空いている（紙面の注記そのまま）

「*」は『どれくらいフレッシュか』をそのまま出している数少ない材料。
前走からの間隔とは別で、**間隔が空いていても攻めている馬**と
**間隔が詰まっているのに攻めていない馬**を分けられる。
"""
import re, os, sys, json, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "kb.conf")
URL = "https://p.keibabook.co.jp/chihou/cyokyo/1/0/"
COLS = ["1哩", "7F", "6F", "5F", "半哩", "3F", "1F"]


def get(rid):
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-K", CONF, URL + rid],
                       capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def txt(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def parse(h):
    out = []
    for blk in re.findall(r'<table class="default cyokyo"[^>]*>(.*?)</table><!-- /.１頭終了',
                          h, re.S):
        mu = re.search(r'class="umaban">\s*(\d+)', blk)
        mn = re.search(r'umacd="(\d+)"[^>]*>([^<]+)</a>', blk)
        if not (mu and mn):
            continue
        head = blk.split('<td class="cyokyo" colspan')[0]
        # 先頭の表だけ thead に「追い切り短評」の文字が入る。実際の短評は最後のセル
        tp = [x for x in re.findall(r'class="tanpyo">([^<]*)<', head)
              if x.strip() and x.strip() != "追い切り短評"]
        # 矢印は空のことが多い。空セルのときに次の馬まで飲み込まないよう閉じタグで止める
        my = re.search(r'class="yajirusi">\s*(?:<span[^>]*>([^<]*)</span>)?\s*</td>', head)
        runs = []
        for tr in re.findall(r'<tr class="(time|oikiri)">(.*?)</tr>', blk, re.S):
            kind, row = tr
            c = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(c) < 16:
                continue
            d = txt(c[2])
            runs.append({"oikiri": kind == "oikiri",
                         "mark": txt(c[0]), "norite": txt(c[1]),
                         "date": d.lstrip("*"), "gap11": d.startswith("*"),
                         "course": txt(c[3]), "baba": txt(c[4]),
                         "times": {k: txt(v) for k, v in zip(COLS, c[5:12]) if txt(v)},
                         "asiiro": txt(c[13]), "tanpyo": txt(c[14])})
        out.append({"ub": int(mu.group(1)), "umacd": mn.group(1),
                    "name": mn.group(2).strip(),
                    "tanpyo": txt(tp[-1]) if tp else "",
                    "ya": txt(my.group(1) or "") if my else "",
                    "runs": runs,
                    "gap11": any(r["gap11"] for r in runs),
                    "nrun": len(runs)})
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    head, mmdd = sys.argv[1], sys.argv[2]
    rs = (range(1, 13) if "--all" in sys.argv
          else [int(x) for x in sys.argv[3:] if x.isdigit()])
    # ★ 2026-11-15 --json 出力.json … 取った分をファイルに残す（展開図 tenkai_zu.py --cyokyo 用）。
    #   取り直しで競馬ブックを叩かないため。中身は有料欄なので **data/ と同じくコミットしない**。
    #   既にあるファイルには**鞍ごとに追記**する（1鞍ずつ間を空けて取る運用のため）。
    # ★ 2026-11-17 統合 ── 形は {R: [1頭ぶん, ...]}（鞍→馬のリスト）を既定にした。
    #   `--json-ub` を付けると {R: {馬番: 1頭ぶん}}（鞍→馬番）で保存する。
    #   tenkai_zu.py / obi.py の --cyokyo は**どちらの形でも読む**（tenkai_zu.load_cyokyo）。
    js = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    by_ub = "--json-ub" in sys.argv
    keep = json.load(open(js)) if js and os.path.exists(js) else {}
    for R in rs:
        rid = "%s%02d%s" % (head, R, mmdd)
        hs = parse(get(rid))
        if js and hs:
            keep[str(R)] = ({str(z["ub"]): z for z in hs} if by_ub else hs)
            json.dump(keep, open(js, "w"), ensure_ascii=False)
        print("=" * 94)
        print("%2dR  %d頭" % (R, len(hs)))
        if not hs:
            print("   調教が載っていません"); time.sleep(0.5); continue
        for z in hs:
            star = " ★11日以上あいた" if z["gap11"] else ""
            print("  %2d %-13s %-8s %s  本数%d%s" % (
                z["ub"], z["name"][:13], z["tanpyo"], z["ya"], z["nrun"], star))
            for r in z["runs"]:
                t = " ".join("%s%s" % (k, v) for k, v in r["times"].items())
                print("      %s%-11s %-7s %s  %-28s %-5s %s" % (
                    "*" if r["gap11"] else " ", r["date"], r["course"][:7],
                    r["baba"], t, r["asiiro"], r["tanpyo"]))
        time.sleep(0.5)
    if js:
        print("\n→ %s（%d鞍・%d頭）" % (js, len(keep), sum(len(v) for v in keep.values())))


if __name__ == "__main__":
    main()
