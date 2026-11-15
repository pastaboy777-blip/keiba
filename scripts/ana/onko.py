"""東スポ競馬の連載「温故知新」（白井寿昭元調教師と学ぶ血統学）を手元に集める。

  python3 onko.py index          # 記事の一覧（ID・タイトル・日付）を作る
  python3 onko.py fetch          # まだ取っていない記事の本文を取る
  python3 onko.py grep <語>...   # 集めた本文から検索（複数語はAND）
  python3 onko.py stat           # 何話ぶん持っているか

本文は保存先 notes/onko/ に 1記事1ファイルで置く（<ID>.txt）。

── 取り方のメモ

本文はサーバーのHTMLには入っておらず、JavaScriptで後から差し込まれる。
curl で200は返るが中身は meta の description だけ。なので Chromium を
ヘッドレスで回して DOM を取る。

もう1つ罠がある。既定のヘッドレスのUser-Agentだと東スポのWAFに
「セキュリティ保護の仕組みにより、このアクセスが遮断されました」で弾かれる。
ふつうのChromeのUAを渡すと通る。--headless=new も必要。

1記事あたり6〜8秒かかるので、全話だと20分以上。間隔を空けて回すこと。
"""
import re, os, sys, html, time, subprocess, json

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "notes", "onko"))
IDX = os.path.join(OUT, "_index.json")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
BASE = "https://tospo-keiba.jp/onkochishin"


def render(url, budget=15000):
    r = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", "--user-agent=" + UA,
         "--virtual-time-budget=%d" % budget, "--dump-dom", url],
        capture_output=True, timeout=120)
    return r.stdout.decode("utf-8", "replace")


def text(h):
    t = re.sub(r"<script.*?</script>", "", h, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"</(p|div|h\d|li|tr)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    return [x.strip() for x in t.split("\n") if x.strip()]


def meta(h):
    """ld+json の headline と datePublished。

    headline は素の UTF-8 で入っている。ここで unicode_escape を噛ませると
    二重エンコードになって「ç½äºåèª¿æå¸«」のように化ける（実際に化かした）。
    エスケープは \\/ と \\" を戻すだけでよい。
    """
    m = re.search(r'"headline":"(.*?)","', h)
    d = re.search(r'"datePublished":"(\d{4}-\d\d-\d\d)', h)
    ttl = m.group(1) if m else ""
    return ttl.replace("\\/", "/").replace('\\"', '"'), (d.group(1) if d else "")


def repair():
    """化けたタイトル行を、本文1行目（DOM由来なので正しい）から作り直す"""
    store = json.load(open(IDX)) if os.path.exists(IDX) else {}
    n = 0
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".txt"):
            continue
        p = os.path.join(OUT, fn)
        ls = open(p).read().split("\n")
        body = [x for x in ls if x and not x.startswith("#")]
        if not body:
            continue
        ttl = body[0].split(" | ")[0].strip()
        if ls[0].startswith("# ") and ls[0][2:] == ttl:
            continue
        ls[0] = "# " + ttl
        open(p, "w").write("\n".join(ls))
        i = fn[:-4]
        store.setdefault(i, {})["title"] = ttl
        n += 1
    json.dump(store, open(IDX, "w"), ensure_ascii=False, indent=0)
    print("タイトルを直しました %d本" % n)


def build_index():
    os.makedirs(OUT, exist_ok=True)
    store = json.load(open(IDX)) if os.path.exists(IDX) else {}
    page, miss = 1, 0
    while miss < 3 and page <= 40:
        h = render("%s?page=%d" % (BASE, page), 12000)
        ids = sorted(set(re.findall(r"/onkochishin/(\d+)", h)))
        new = [i for i in ids if i not in store]
        for i in ids:
            store.setdefault(i, {})
        print("page %2d  リンク%3d  新規%3d  （累計 %d）" % (page, len(ids), len(new), len(store)),
              flush=True)
        miss = miss + 1 if not new else 0
        page += 1
        json.dump(store, open(IDX, "w"), ensure_ascii=False, indent=0)
        time.sleep(1.5)
    print("記事ID  %d本" % len(store))


def fetch():
    store = json.load(open(IDX))
    todo = [i for i in sorted(store, key=int)
            if not os.path.exists(os.path.join(OUT, i + ".txt"))]
    print("未取得 %d本" % len(todo), flush=True)
    for n, i in enumerate(todo, 1):
        try:
            h = render("%s/%s" % (BASE, i))
        except Exception as e:
            print("NG", i, e, flush=True); continue
        if "遮断されました" in h:
            print("WAFに弾かれました。時間を置いてください", flush=True); break
        ls = text(h)
        ttl, dt = meta(h)
        body = [x for x in ls if len(x) > 14]
        if len(body) < 5:
            print("%s 本文が取れません" % i, flush=True); time.sleep(3); continue
        store[i] = {"title": ttl, "date": dt, "n": len(body)}
        with open(os.path.join(OUT, i + ".txt"), "w") as f:
            f.write("# %s\n# %s\n# %s/%s\n\n" % (ttl, dt, BASE, i))
            f.write("\n".join(body))
        json.dump(store, open(IDX, "w"), ensure_ascii=False, indent=0)
        print("%3d/%d  %s  %s  %s" % (n, len(todo), i, dt, ttl[:50]), flush=True)
        time.sleep(2.0)


def grep(words):
    n = 0
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".txt"):
            continue
        s = open(os.path.join(OUT, fn)).read()
        if all(w in s for w in words):
            n += 1
            head = s.split("\n")[0][2:]
            print("── %s  %s" % (fn[:-4], head))
            for ln in s.split("\n"):
                if any(w in ln for w in words) and not ln.startswith("#"):
                    print("     " + ln[:170])
    print("\n該当 %d本" % n)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "index":
        build_index()
    elif cmd == "fetch":
        fetch()
    elif cmd == "grep":
        grep(sys.argv[2:])
    elif cmd == "repair":
        repair()
    elif cmd == "stat":
        store = json.load(open(IDX)) if os.path.exists(IDX) else {}
        got = [f for f in os.listdir(OUT) if f.endswith(".txt")] if os.path.isdir(OUT) else []
        print("ID %d本 ／ 本文を持っているもの %d本" % (len(store), len(got)))
        for i in sorted(store, key=int):
            z = store[i]
            if z.get("title"):
                print("  %-7s %s  %s" % (i, z.get("date", ""), z["title"][:60]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
