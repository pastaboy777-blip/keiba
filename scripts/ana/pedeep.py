"""血統表を再帰的にたどって10代まで展開し、奥のクロスを数える。

  python3 pedeep.py <netkeibaの馬ID> [--gen 10] [--only Son-in-Law,Hyperion]

netkeiba の血統表は1ページ5代ぶん。5代目の馬のページをもう一度引けば、
元の馬から見て6〜10代が埋まる。それを繰り返せば何代でも伸ばせる。

  1頭を10代まで = 1 + 32 = 33ページ
  11〜15代まで  = さらに 32×32 = 1024ページ（重複を除けばもっと少ない）

望田潤氏らが言う「ハイインロー」= Hyperion × Son-in-Law、「ナスキロ」=
Nasrullah × Princequillo は 8〜12代前の話で、5代血統表には映らない。
そこを見るためのもの。

祖先は共有されるので、**キャッシュが効く**。Hyperion や Son-in-Law のような
古い馬は何百回も出てくるが、ページを引くのは1回でよい。
複数の馬を調べるほど1頭あたりのページ数は減る。

血量は、ある祖先が n代前にいるとき (1/2)^n の合計。
10代前は 0.098% なので、本数（出現回数）のほうが実感に近い。
"""
import re, os, sys, json, time, subprocess, html

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "ped_cache.json")
BASE = "https://db.netkeiba.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
GEN = {16: 1, 8: 2, 4: 3, 2: 4, 1: 5}
_cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
_fetched = [0]


def get(url):
    for i in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "40", "-A", UA, url],
                           capture_output=True, timeout=60)
        h = r.stdout.decode("euc-jp", "replace")
        if len(h) > 3000:
            return h
        time.sleep(2 * (i + 1))
    return h


def five(hid):
    """その馬の5代血統表を {代: [(名前, ID), ...]} で返す。キャッシュする"""
    if hid in _cache:
        return {int(k): [tuple(x) for x in v] for k, v in _cache[hid].items()}
    h = get("%s/horse/ped/%s/" % (BASE, hid))
    _fetched[0] += 1
    i = h.find("blood_table")
    out = {}
    if i >= 0:
        seg = h[i:h.find("</table>", i)]
        for m in re.finditer(r"<td([^>]*)>(.*?)</td>", seg, re.S):
            mr = re.search(r'rowspan="(\d+)"', m.group(1))
            rs = int(mr.group(1)) if mr else 1
            nm = re.search(r'/horse/\w+/?"[^>]*>(.*?)</a>', m.group(2), re.S)
            if not nm:
                continue
            name = re.sub(r"<[^>]+>", "", nm.group(1))
            name = html.unescape(name).replace(" ", " ").strip()
            name = re.sub(r"\s*\(.+?\)\s*$", "", name)
            if not name:
                continue
            mid = re.search(r"/horse/(\w{8,12})/", m.group(2))
            out.setdefault(GEN.get(rs, 5), []).append((name, mid.group(1) if mid else None))
    _cache[hid] = {str(k): v for k, v in out.items()}
    json.dump(_cache, open(CACHE, "w"), ensure_ascii=False)
    time.sleep(1.0)
    return out


def expand(hid, maxgen=10, log=True):
    """{名前: [代, 代, ...]} を maxgen まで"""
    found = {}
    frontier = [(hid, 0)]
    while frontier:
        nxt = []
        for h, base in frontier:
            if base >= maxgen:
                continue
            g5 = five(h)
            for g, lst in g5.items():
                gg = base + g
                if gg > maxgen:
                    continue
                for name, i in lst:
                    found.setdefault(name, []).append(gg)
                    if gg == maxgen - 4 and i and base + 5 <= maxgen:
                        pass
            # 5代目の馬を次の起点にする（そこから6〜10代が埋まる）
            if base + 5 < maxgen:
                for name, i in g5.get(5, []):
                    if i:
                        nxt.append((i, base + 5))
        if log:
            print("   …%d代まで / 取得ページ %d / 祖先 %d頭"
                  % (min(maxgen, 5 + len(nxt) and maxgen), _fetched[0], len(found)), flush=True)
        frontier = nxt
    return found


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    hid = args[0]
    mg = int(args[args.index("--gen") + 1]) if "--gen" in args else 10
    only = args[args.index("--only") + 1].split(",") if "--only" in args else None
    print("馬ID %s を %d代まで展開します" % (hid, mg), flush=True)
    t0 = time.time()
    found = expand(hid, mg)
    print("  取得したページ %d / 祖先のべ %d / 実数 %d / %.0f秒"
          % (_fetched[0], sum(len(v) for v in found.values()), len(found), time.time() - t0))
    rows = []
    for n, gs in found.items():
        if len(gs) < 2:
            continue
        if only and not any(o.lower() in n.lower() for o in only):
            continue
        blood = sum(0.5 ** g for g in gs)
        rows.append((n, sorted(gs), len(gs), round(100 * blood, 3)))
    rows.sort(key=lambda x: -x[2])
    print("\n■ %d代以内に2回以上出てくる祖先（本数の多い順）" % mg)
    print("  %-26s %5s %-30s %s" % ("", "本数", "代", "血量"))
    for n, gs, c, b in rows[:40]:
        g = "・".join(str(x) for x in gs[:12]) + ("…" if len(gs) > 12 else "")
        print("  %-26s %5d %-30s %6.3f%%" % (n[:26], c, g, b))
    if only:
        print("\n（--only 指定あり。該当のみ表示）")


if __name__ == "__main__":
    main()
