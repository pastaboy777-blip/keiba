"""netkeiba の5代血統表を引いて、インブリード（クロス）を出す。

  python3 ped5.py <netkeibaの馬ID>            # 1頭ぶん
  python3 ped5.py --name <馬名>               # 馬名から引く
  python3 ped5.py --name <馬名> --full        # 62頭ぶんの並びも出す

競馬ブックの血統表は3代までで4代目がマスクされている。3×4の「奇跡の血量」は
そこからは見えない。netkeiba の /horse/ped/<ID>/ は **5代＝62頭** まで出るので、
3×3・3×4・4×4 といったクロスを実際に数えられる。

── 表の読み方

5列の表で、rowspan が 16/8/4/2/1 と減っていく。これがそのまま代になる。

  rowspan=16 →  2頭  1代（父・母）
  rowspan=8  →  4頭  2代
  rowspan=4  →  8頭  3代
  rowspan=2  → 16頭  4代
  rowspan=1  → 32頭  5代                合計 62頭

各代のセルは上から順に、父側→母側の並びで出てくるので、位置がそのまま決まる。

── 血量

ある祖先が n代前にいると (1/2)^n を寄与する。同じ馬が複数の位置に出てきたら
その合計が血量。3×4 なら 1/8 + 1/16 = 18.75%（いわゆる奇跡の血量）。

ページは EUC-JP。
"""
import re, sys, time, subprocess, html

BASE = "https://db.netkeiba.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
GEN = {16: 1, 8: 2, 4: 3, 2: 4, 1: 5}


def get(url):
    """netkeibaは連続で叩くと空を返すことがあるので、間を空けて何度か試す"""
    for i in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "40", "-A", UA, url],
                           capture_output=True, timeout=60)
        h = r.stdout.decode("euc-jp", "replace")
        if len(h) > 3000:
            return h
        time.sleep(2 * (i + 1))
    return h


def find_id(name):
    """馬名から netkeiba の馬IDを引く"""
    import urllib.parse
    u = BASE + "/?pid=horse_list&word=" + urllib.parse.quote(name, encoding="euc-jp")
    h = get(u)
    m = re.search(r'/horse/(\w{8,12})/?"[^>]*>\s*' + re.escape(name), h)
    if m:
        return m.group(1)
    ids = re.findall(r'/horse/(\w{10})/?"', h)
    return ids[0] if ids else None


def parse(h):
    """{位置: 名前} と、代ごとの並びを返す"""
    i = h.find("blood_table")
    if i < 0:
        return None
    seg = h[i:h.find("</table>", i)]
    cells = []
    # 属性をまとめて取ってから rowspan を探す。
    # 正規表現の中で rowspan を optional にすると、先頭の [^>]*? が空に食われて
    # いつも「rowspan なし＝5代」になってしまう（実際にそうなった）
    for m in re.finditer(r'<td([^>]*)>(.*?)</td>', seg, re.S):
        mr = re.search(r'rowspan="(\d+)"', m.group(1))
        rs = int(mr.group(1)) if mr else 1
        # netkeiba はクロスする祖先を <span class="red"> で囲む。
        # <a> の中身を [^<]+ で取ると **赤表示の馬だけ名前が取れない**。
        # つまりインブリードしている馬だけ落ちる、という一番まずいバグになる。
        # いったんタグごと取ってから、中のタグを剥がす。
        nm = re.search(r'/horse/\w+/?"[^>]*>(.*?)</a>', m.group(2), re.S)
        if not nm:
            nm = re.search(r'>\s*([^<>\n]{2,40}?)\s*<br', m.group(2))
        if not nm:
            continue
        name = re.sub(r"<[^>]+>", "", nm.group(1))
        name = html.unescape(name).replace("\u00a0", " ").strip()
        name = re.sub(r"\s*\(.+?\)\s*$", "", name)
        if not name:
            continue
        cells.append((GEN.get(rs, 5), name, 'class="red"' in m.group(2)))
    gens, red = {}, set()
    for g, n, r in cells:
        gens.setdefault(g, []).append(n)
        if r:
            red.add(n)
    gens['red'] = red
    return gens


def positions(gens):
    """代ごとの並びから {名前: [代, 代, ...]} を作る"""
    out = {}
    for g in sorted(k for k in gens if isinstance(k, int)):
        for n in gens[g]:
            out.setdefault(n, []).append(g)
    return out


def label(g):
    """1代目から数えた位置の呼び名（父/母 から順に）"""
    return "%d代" % g


def inbreed(gens):
    """同じ馬が2回以上出てきたものを、血量の大きい順に"""
    out = []
    for n, gs in positions(gens).items():
        if len(gs) < 2:
            continue
        blood = sum(0.5 ** g for g in gs)
        out.append((n, sorted(gs), round(100 * blood, 2)))
    return sorted(out, key=lambda x: -x[2])


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    if args[0] == "--name":
        name = args[1]
        hid = find_id(name)
        if not hid:
            print("馬が見つかりません:", name); return
        print("%s → %s/horse/%s/" % (name, BASE, hid))
    else:
        hid = args[0]
    gens = parse(get("%s/horse/ped/%s/" % (BASE, hid)))
    if not gens:
        print("血統表が読めません"); return
    ng = {g: v for g, v in gens.items() if isinstance(g, int)}
    print("  取れた頭数:", {("%d代" % g): len(v) for g, v in sorted(ng.items())},
          " 合計", sum(len(v) for v in ng.values()))
    print("\n  父 %s ／ 母 %s ／ 母父 %s" % (
        gens[1][0] if gens.get(1) else "?",
        gens[1][1] if gens.get(1) and len(gens[1]) > 1 else "?",
        gens[2][2] if gens.get(2) and len(gens[2]) > 2 else "?"))
    ib = inbreed(gens)
    print("\n■ インブリード（5代以内）")
    if not ib:
        print("  なし（完全アウトブリード）")
    for n, gs, b in ib:
        mark = "  ★奇跡の血量" if 18.0 <= b <= 19.0 else ""
        if n in gens.get('red', ()):
            mark += "  （netkeibaも赤表示）"
        print("  %-26s %-12s 血量 %5.2f%%%s" % (n, "×".join(str(g) for g in gs), b, mark))
    if "--full" in args:
        for g in sorted(k for k in gens if isinstance(k, int)):
            print("\n[%d代] %d頭" % (g, len(gens[g])))
            for k in range(0, len(gens[g]), 4):
                print("   " + " / ".join(gens[g][k:k + 4]))


if __name__ == "__main__":
    main()
