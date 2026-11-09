"""1日ぶんずつ、ゆっくり集める ── 結果 → 馬名 → netkeibaのID → 5代 → 10代。

  python3 harvest.py check <base16>              # 1ページだけ試す（必ず最初にこれ）
  python3 harvest.py res   <base16> <ラベル>     # その日の結果（楽天）
  python3 harvest.py ids   <ラベル>              # 馬名→netkeibaのID
  python3 harvest.py ped5  <ラベル>              # 5代血統表
  python3 harvest.py deep  <ラベル> [--gen 10]   # 10代まで展開
  python3 harvest.py stat  <ラベル>              # どこまで進んだか

base16 は楽天の RACEID の頭16桁。その日の一覧から拾う。

  https://keiba.rakuten.co.jp/race_card/list/RACEID/<日付8桁>0000000000

  例  2026100420151001  = 2026/10/04 大井（場20・第10回・第1日）
      2026102620151101  = 2026/10/26 大井（第11回・第1日）
      2026102318130705  = 2026/10/23 浦和（場18・第7回・第5日）

── ★ 2026-10-24 に学んだこと（必ず読むこと）

短時間に叩きすぎて **楽天に絞られた**。

  楽天     … ページが約3,000文字のスタブ（「JavaScriptが無効の為…」）だけになり、
             1時間前に取れていたページまで同じ状態になった

同時に「netkeibaの馬名検索が0バイトを返す」とも書いたが、**これは誤診だった**
（2026-10-24 に判明）。完全一致が1頭だけのとき netkeiba は一覧を出さず
`/horse/<ID>/` へ **302で飛ばす**。`-L` なしで本文だけ見ると0バイトになる。
名前次第で通ったり落ちたりしていたのはそのため。`nk_search()` で直した。
**「0バイト＝絞られている」と決めつける前に HTTPコードを見ること。**

その日のうちに、楽天（浦和5日分の結果・ラップ・出馬表・日程走査）、競馬ブック
（調教・血統60鞍）、netkeiba（菊花賞253ページ＋浦和の途中まで）を重ねたのが原因。
**リトライを続けると悪化するだけ**なので、気づいたら止めて時間を空ける。

だからこのファイルの既定値はこうしてある。

  SLEEP = 4.0 秒    1本ずつ。同時に2本走らせない
  1日ぶんずつ        まとめて回さない
  必ず resumable     途中で止めても積み上がる
  check を先に       いきなり長いのを回さない

ページが短すぎたら（STUB_LEN 未満）**その場で止める**。粘らない。
"""
import re, os, sys, json, time, subprocess, html, urllib.parse, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "harvest")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
SLEEP = 4.0
STUB_LEN = 20000          # 楽天の正常なページはこれより長い
NK = "https://db.netkeiba.com"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/"
GEN = {16: 1, 8: 2, 4: 3, 2: 4, 1: 5}


class Blocked(Exception):
    pass


MARK = "\n@@EFFECTIVE@@"


def _curl(url, enc="utf-8", follow=False):
    """follow=True のとき、本文のあとに最終URLを付けて返す（リダイレクト先を見るため）"""
    cmd = ["curl", "-sS", "--max-time", "45", "-A", UA]
    if follow:
        cmd += ["-L", "-w", MARK + "%{url_effective}"]
    r = subprocess.run(cmd + [url], capture_output=True, timeout=70)
    return r.stdout.decode(enc, "replace")


def rk(url):
    """楽天のページ。**0字と「短いページ」は別の症状**なので分けて扱う。

      0字              … 通信が落ちただけ（curl が何も持って帰らない）。リトライする
      3,000字前後       … 「JavaScriptが無効の為…」のスタブ。絞られている。止める

    同じ扱いにしていたため、1回のタイムアウトで1日ぶんの取得が止まっていた
    （2026-10-24、大井10/6の3Rで0字が返って10鞍落とした）。
    """
    for wait in (5, 15, None):
        h = _curl(url)
        if len(h) >= STUB_LEN:
            return h
        if len(h) > 0:                      # スタブが返っている → 粘らない
            break
        if wait is None:
            break
        time.sleep(wait)
    raise Blocked("楽天が %d字 を返しました。%s" % (
        len(h), "通信が3回続けて落ちました" if not h else
                "スタブです（絞られています）。時間を空けてください"))


def nk(url):
    h = _curl(url, "euc-jp")
    if len(h) < 3000:
        raise Blocked("netkeibaが %d字 しか返しません。絞られています。"
                      "時間を空けてください" % len(h))
    return h


HIT = re.compile(r'/horse/(\w{8,12})/?"[^>]*>\s*([^<]{1,24}?)\s*</a>')


def nk_search(name, maxpage=10):
    """馬名から netkeiba の馬IDを引く。

    ★ 完全一致が1頭だけのとき、netkeiba は一覧を出さずに
      /horse/<ID>/ へ **302で飛ばす**。-L を付けずに本文だけ見ると0バイトになり、
      「絞られている」と誤判定する（2026-10-24 に実際にそう読み違えた）。
      だからここはリダイレクト先のURLから拾う。

    ★ 検索は**部分一致**で、1ページ20頭ずつ。「ウズ」「ジュリ」のような短い馬名は
      「メイショウウズマサ」などに埋もれて1ページ目に出てこない（180件ヒットした）。
      完全一致が見つかるまでページを送る。
    """
    w = urllib.parse.quote(name, encoding="euc-jp")
    for page in range(1, maxpage + 1):
        u = NK + "/?pid=horse_list&word=" + w + ("&page=%d" % page if page > 1 else "")
        out = _curl(u, "euc-jp", follow=True)
        body, _, eff = out.rpartition(MARK)
        if not body:
            body, eff = out, ""
        m = re.search(r"/horse/(\w{8,12})", eff)
        if m:                               # 1頭に確定 → 飛ばされた先がその馬
            return m.group(1)
        if len(body) < 3000:
            raise Blocked("netkeibaが %d字 しか返しません（リダイレクトでもない）。"
                          "絞られています。時間を空けてください" % len(body))
        hits = HIT.findall(body)
        for i, nm in hits:
            if nm.strip() == name:
                return i
        if len(hits) < 20:                  # 最終ページまで見た
            return None
        time.sleep(SLEEP)
    return None


def path(label, kind):
    os.makedirs(DATA, exist_ok=True)
    return os.path.join(DATA, "%s_%s.json" % (label, kind))


def load(label, kind):
    p = path(label, kind)
    return json.load(open(p)) if os.path.exists(p) else {}


def save(label, kind, obj):
    json.dump(obj, open(path(label, kind), "w"), ensure_ascii=False)


def flat(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def secs(s):
    """走破タイム「1:14.8」「48.2」を秒に"""
    m, _, r = s.rpartition(":")
    try:
        return round(int(m) * 60 + float(r), 1) if m else float(r)
    except ValueError:
        return None


ROW = re.compile(r"(?=(?<!\d)\d{1,2}\s+\d\s+\d{1,2}\s+[ァ-ヶー]{2,}\s+[牡牝セ騸扇]\d)")


def corners(t):
    """「１角 (3,6),(2,9),11,8…」を {角: [[同着グループ], …]} に。rakuten.py と同じ形。

    ★ 記号つきの生の文字列も返す（2026-11-01 に直した）。

      通過順の記号は**間隔**を表している。順位だけ見ていると全部捨ててしまう。

        ( )  ほぼ横並び（同じ位置）
        ,    1馬身以内
        -    1〜2馬身あいた
        =    大きくあいた

      例 … ４角 `(3,5),7=4-1,6,2=8`
           3と5は横並び、7は1馬身以内、そこから4まで**大きく開き**、
           4と1は1〜2馬身、1と6と2は1馬身以内、2と8は大きく開く。

      括弧（併走）は前から保存できていた（手元1,300鞍のうち1,268鞍に入っている）。
      落としていたのは **群と群のあいだの , - = だけ**。これを corner_raw に残す。
    """
    out, raw = {}, {}
    for k, lab in ((1, "１角"), (2, "２角"), (3, "３角"), (4, "４角")):
        m = re.search(lab + r"\s+([0-9(),=\- ]+?)(?:[１-４]角|■|$)", t)
        if not m:
            continue
        s = m.group(1).strip()
        seq = []
        for g in re.findall(r"\(([\d,]+)\)|(\d+)", s):
            seq.append([int(x) for x in g[0].split(",")] if g[0] else [int(g[1])])
        if seq:
            out[k] = seq
            raw[k] = s
    return out, raw


def pos_of(seq, ub):
    """括弧つきの並びから、その馬番の順位（括弧内は同位）"""
    p = 1
    for g in seq:
        if ub in g:
            return p
        p += len(g)
    return None


def do_res(base, label):
    store = load(label, "res")
    for R in range(1, 17):
        key = str(R)
        # ★ corner_raw（記号つき）まで入っていれば飛ばす。
        #   古いファイルは corner しか無いので、その鞍だけ取り直しになる
        if key in store and store[key].get("corner_raw"):
            continue
        t = flat(rk(PERF + base + "%02d" % R))
        i = t.find("全着順")
        if i < 0 or "取止" in t[:i + 3000]:
            print("%2dR なし" % R, flush=True)
            if R > 12:
                break
            time.sleep(SLEEP); continue
        md = re.search(r"(ダ|芝)([\d,]+)m", t)
        mb = re.search(r"天候：\s*(\S+)\s+(?:ダ|芝)：\s*(\S+)", t)
        ml = re.search(r"ハロンタイム\s+([\d.\- ]+?)\s+上がり", t)
        cn, cnraw = corners(t)
        rows = []
        for p in ROW.split(t[i:i + 5000])[1:]:
            m = re.match(r"(\d{1,2})\s+(\d)\s+(\d{1,2})\s+([ァ-ヶー]{2,})\s", p)
            if not m:
                continue
            nums = re.findall(r"(?<![\d.:])(\d{1,2})(?![\d.:])", p)
            mw = re.search(r"\s(\d{3})\s+([-+±]\d+)\s", p)
            mdw = re.search(r"\s\d{3}\s+([-+±]\d+)\s", p)
            # 騎手は「▲西優哉 (大井)」。そのうしろは タイム → 着差 → 上がり → 調教師 → 人気
            mj = re.search(r"([^\s(]{2,10})\s*\((?:大井|川崎|船橋|浦和|門別|高知|佐賀|"
                           r"金沢|笠松|園田|姫路|名古屋|盛岡|水沢|帯広|美浦|栗東)\)", p)
            # ★ 上がりを「行頭から最初の [34]x.x」で取ってはいけない（2026-11-01 に直した）。
            #   800m の走破タイムは 48.2 のような形で、[34]\d\.\d に当たってしまう。
            #   浦和800mの8鞍で、上がり3Fの欄に**走破タイムが入っていた**。
            #   騎手の（場）より後ろだけを見て、タイム・着差・上がりを順に取る。
            tail = p[mj.end():] if mj else ""
            mtm = re.match(r"\s*(\d:\d\d\.\d|\d{1,2}\.\d)\s", tail)
            rest = tail[mtm.end():] if mtm else tail
            mag = re.search(r"([34]\d\.\d)\s", rest)
            mt = re.search(r"[34]\d\.\d\s+([ァ-ヶー一-龥]{2,6})\s+\d{1,2}(?!\d)", rest)
            # 着差 … タイムと上がりのあいだ。「クビ」「アタマ」「１」「３／４」「大差」など
            sa = rest[:mag.start()].strip() if mag else ""
            ub = int(m.group(3))
            rows.append({"chaku": int(m.group(1)), "waku": int(m.group(2)), "ub": ub,
                         "name": m.group(4), "nk": int(nums[-1]) if nums else None,
                         "w": int(mw.group(1)) if mw else None,
                         "dw": mdw.group(1).replace("±", "+") if mdw else None,
                         "agari": float(mag.group(1)) if mag else None,
                         "t": secs(mtm.group(1)) if mtm else None,
                         "sa": sa or None,
                         # 1角と4角の通過順。gain = 1角 − 4角（プラスが押し上げた）
                         "c1": pos_of(cn[1], ub) if 1 in cn else None,
                         "c4": pos_of(cn[4], ub) if 4 in cn else None,
                         "jk": re.sub(r"^[▲△☆★◇◎]", "", mj.group(1)) if mj else None,
                         "tr": mt.group(1) if mt else None})
        store[key] = {"R": R, "dist": int(md.group(2).replace(",", "")) if md else None,
                      "tenko": mb.group(1) if mb else None,
                      "baba": mb.group(2) if mb else None,
                      "lap": [float(v) for v in ml.group(1).split("-")] if ml else [],
                      "corner": {str(k): v for k, v in cn.items()},
                      # ★ 記号つきの生の通過順。間隔（, - =）はここにしか残らない
                      "corner_raw": {str(k): v for k, v in cnraw.items()},
                      "rows": rows}
        w = [x for x in rows if x["chaku"] == 1]
        print("%2dR %4dm %-3s %2d頭  1着 %-12s %s人気  角%s ラップ%d" % (
            R, store[key]["dist"] or 0, store[key]["baba"] or "?", len(rows),
            w[0]["name"] if w else "?", w[0]["nk"] if w else "?",
            "".join(str(k) for k in sorted(cn)) or "なし", len(store[key]["lap"])), flush=True)
        save(label, "res", store)
        time.sleep(SLEEP)
    names = sorted({x["name"] for v in store.values() for x in v["rows"]})
    save(label, "names", names)
    print("\n%d鞍 / 実数 %d頭" % (len(store), len(names)))


def do_ids(label):
    names = load(label, "names") or []
    store = load(label, "ids")
    todo = [n for n in names if n not in store]
    print("未取得 %d頭" % len(todo), flush=True)
    for k, n in enumerate(todo, 1):
        store[n] = nk_search(n)
        if k % 10 == 0 or k == len(todo):
            save(label, "ids", store)
            print("  %4d/%d  取れた %d" % (k, len(todo),
                  sum(1 for v in store.values() if v)), flush=True)
        time.sleep(SLEEP)
    save(label, "ids", store)


def five(hid):
    h = nk("%s/horse/ped/%s/" % (NK, hid))
    i = h.find("blood_table")
    if i < 0:
        return None
    seg = h[i:h.find("</table>", i)]
    out = {}
    for m in re.finditer(r"<td([^>]*)>(.*?)</td>", seg, re.S):
        mr = re.search(r'rowspan="(\d+)"', m.group(1))
        rs = int(mr.group(1)) if mr else 1
        nm = re.search(r'/horse/\w+/?"[^>]*>(.*?)</a>', m.group(2), re.S)
        if not nm:
            continue
        name = re.sub(r"<[^>]+>", "", nm.group(1))
        name = html.unescape(name).replace(" ", " ").strip()
        name = re.sub(r"\s*\(.+?\)\s*$", "", name)
        if name:
            out.setdefault(GEN.get(rs, 5), []).append(name)
    return out


def do_ped5(label):
    ids = load(label, "ids")
    store = load(label, "ped5")
    todo = [(n, i) for n, i in ids.items() if i and n not in store]
    print("未取得 %d頭" % len(todo), flush=True)
    for k, (n, i) in enumerate(todo, 1):
        g = five(i)
        store[n] = {str(a): b for a, b in g.items()} if g else None
        if k % 10 == 0 or k == len(todo):
            save(label, "ped5", store)
            print("  %4d/%d" % (k, len(todo)), flush=True)
        time.sleep(SLEEP)
    save(label, "ped5", store)


def do_deep(label, maxgen=10):
    spec = importlib.util.spec_from_file_location("pd", os.path.join(HERE, "pedeep.py"))
    pd = importlib.util.module_from_spec(spec); spec.loader.exec_module(pd)
    ids = load(label, "ids")
    store = load(label, "deep")
    todo = [(n, i) for n, i in ids.items() if i and n not in store]
    print("未取得 %d頭（祖先のキャッシュ %d頭）" % (len(todo), len(pd._cache)), flush=True)
    for k, (n, i) in enumerate(todo, 1):
        f = pd.expand(i, maxgen, log=False)
        store[n] = {a: sorted(b) for a, b in f.items() if len(b) >= 2}
        save(label, "deep", store)
        print("  %4d/%d %-16s クロス%3d件 キャッシュ%4d頭"
              % (k, len(todo), n[:16], len(store[n]), len(pd._cache)), flush=True)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    try:
        if cmd == "check":
            t = flat(rk(PERF + a[1] + "01"))
            print("楽天 OK  %d字  全着順=%s" % (len(t), "全着順" in t))
            h = nk(NK + "/horse/ped/2017100720/")
            print("netkeiba OK  %d字  血統表=%s" % (len(h), "blood_table" in h))
            print("\n両方通りました。res から始めてください。")
        elif cmd == "res":
            do_res(a[1], a[2])
        elif cmd == "ids":
            do_ids(a[1])
        elif cmd == "ped5":
            do_ped5(a[1])
        elif cmd == "deep":
            g = int(a[a.index("--gen") + 1]) if "--gen" in a else 10
            do_deep(a[1], g)
        elif cmd == "stat":
            for k in ("res", "names", "ids", "ped5", "deep"):
                v = load(a[1], k)
                print("  %-6s %d" % (k, len(v)))
        else:
            print(__doc__)
    except Blocked as e:
        print("\n★ 止めました:", e)
        print("  粘らないこと。数時間空けてから check でやり直す。")
        sys.exit(1)


if __name__ == "__main__":
    main()
