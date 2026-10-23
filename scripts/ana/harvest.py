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
    h = _curl(url)
    if len(h) < STUB_LEN:
        raise Blocked("楽天が短いページ（%d字）を返しました。絞られています。"
                      "時間を空けてください" % len(h))
    return h


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


ROW = re.compile(r"(?=(?<!\d)\d{1,2}\s+\d\s+\d{1,2}\s+[ァ-ヶー]{2,}\s+[牡牝セ騸扇]\d)")


def do_res(base, label):
    store = load(label, "res")
    for R in range(1, 17):
        key = str(R)
        if key in store:
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
        rows = []
        for p in ROW.split(t[i:i + 5000])[1:]:
            m = re.match(r"(\d{1,2})\s+\d\s+(\d{1,2})\s+([ァ-ヶー]{2,})\s", p)
            if not m:
                continue
            nums = re.findall(r"(?<![\d.:])(\d{1,2})(?![\d.:])", p)
            mw = re.search(r"\s(\d{3})\s+([-+±]\d+)\s", p)
            mag = re.search(r"\s([34]\d\.\d)\s", p)
            rows.append({"chaku": int(m.group(1)), "ub": int(m.group(2)),
                         "name": m.group(3), "nk": int(nums[-1]) if nums else None,
                         "w": int(mw.group(1)) if mw else None,
                         "agari": float(mag.group(1)) if mag else None})
        store[key] = {"R": R, "dist": int(md.group(2).replace(",", "")) if md else None,
                      "tenko": mb.group(1) if mb else None,
                      "baba": mb.group(2) if mb else None, "rows": rows}
        w = [x for x in rows if x["chaku"] == 1]
        print("%2dR %4dm %-3s %2d頭  1着 %-12s %s人気" % (
            R, store[key]["dist"] or 0, store[key]["baba"] or "?", len(rows),
            w[0]["name"] if w else "?", w[0]["nk"] if w else "?"), flush=True)
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
