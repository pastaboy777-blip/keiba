"""当日用のワンコマンド ── 出馬表を取り直して、図とPNGと表を一度に出す。

  python3 tojitsu.py <base16> --ven 大井 --date "2026.11.16 MON" \
      [--R 1-12] [--baba 重] [--out <出力ディレクトリ>] [--plain] [--no-img]

CLAUDE.md ルール3 ──「**馬体重は発走30分前に取り直す**」。
「買う馬リストの組み方」末尾 ──「**前日カードは下見。発走30分前に取り直して
印を打ち直すのが本来の形**」。
その「取り直し」を手で3〜4コマンド叩いていたのを1本にしただけのもの。
**中身の判断は何も足していない**（印も買い目も出さない）。

やること（この順）

  ① `syutuba.py`   出馬表＋過去5走を取る            → card.json
  ② `tenkai_zu.py` 1コーナーの隊列図               → zu.html
  ③ Chromium       画像にして下の余白を切る         → zu.png（長ければ zu_1.png …）
  ④ `ninki.py`     1頭1行の表（標準出力にも出す）   → hyo.txt

既定の出力先は
  /tmp/claude-0/-home-user-keiba/<id>/scratchpad/tojitsu/<日付8桁>/
（`--out` で変えられる。`$TOJITSU_OUT` でも。）

── 渡せるもの

  --R 7-12      鞍の範囲（既定 1-12）。`syutuba.py` と `tenkai_zu.py` と `ninki.py` に同じ値が行く
  --baba 重     馬場。**未発表のときは付けない**（CLAUDE.md ルール27）。
                効くのは `tenkai.sui()`＝ペースの水準だけで、隊列は動かない（ルール40）
  --plain       人に見せる版（図の数値を落とす）
  --no-img      画像化を飛ばす（HTMLと表だけ）
  --card <json> **出馬表を取り直さない**。既にある card.json で図と表を引き直すだけ。
                楽天を叩かないので、図を描き直すだけのときはこちら
  --out <dir>   出力先
  --ab          **同じ鞍を2枚出す**（CLAUDE.md ルール59）。
                A版 … `--pos-mazeru` あり（地点を混ぜる・いまの既定）→ `<out>/a/`
                B版 … `--pos-mazeru` なし（地点をそろえる）        → `<out>/b/`
                **他の口は両版でまったく同じ**にするので、差は「地点をそろえたか」だけ。
                **出馬表は1回だけ取る** ── A版で取った card.json をB版が `--card` で
                読み直す（2回引くとオッズが動いて差が地点だけでなくなる）。
                どちらを既定にするかは**ユーザーが決める**（ルール51・59）。

  ★ `tenkai_zu.py` 側の口はそのまま通る ──
    `--pace 7:S` `--ana 7:3,5` `--ana2` `--swap` `--soto` `--uchi` `--flip` `--migi`
    `--noswap` `--odds` `--res` `note:7=見解`
    `--no-agari`（推定の括弧の「・上がり」を出さない）
    `--no-baba-n`（道悪の札の回数 0/3 を出さない）
    `--no-marulegend`（「●赤丸＝狙い」の凡例を出さない）。
    `--` のあとに書いたものも全部 `tenkai_zu.py` に渡す。
    ★ 「鞍:値」を並べる口は**引用符でくくっても空白で区切っても同じ**
      （`--pace "1:S 2:M"` も `--pace 1:S 2:M` も同じ／2026-11-15 に直した。
      　それまで引用符つきは**黙って全鞍Mに落ちていた**。`tenkai_zu.kv()` の★★）。
    図の向き（鏡にするか）は**距離から自動**（ルール39・43）。何も渡さなくてよい。

── 触っていないもの

  `syutuba.py` / `tenkai_zu.py` / `ninki.py` は**読んで呼ぶだけ**で、1行も直していない。
  `soto.py --build` / `jk_soto.py --build` / `tenkai.py --build` は**呼ばない**
  （harvest が無いので走らせると参照ファイルが空になる ── handoff_ooi_202611.md §9）。

── 気をつける所

  ・`tenkai.py` を**単体で**走らせるときは場をファイル名の頭3字で決めている
    （`VEN = {"ooi": "大井", ...}`）。ここが出す card.json は名前が `card.json` なので、
    `python3 tenkai.py <out>/card.json` と直に叩くと**船橋の水準**で計算される。
    `tojitsu.py` の中（`tenkai_zu.py` / `ninki.py`）は `--ven` を渡しているので影響しない。
  ・Chromium は `/opt/pw-browsers/` から**探す**（`chromium-1194` → `1243` で
    決め打ちが壊れた経緯がある）。見つからなければ画像だけ飛ばして、HTMLと表は出す。
"""
import sys, os, re, io, json, glob, shutil, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEF_OUT = ("/tmp/claude-0/-home-user-keiba/"
           "5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/tojitsu")
WIN_W = 1060          # 図の幅は WID 900 + PAD 64*2 ＝ 1028
SCALE = 2             # --force-device-scale-factor
MAX_PNG = 8000        # これを超える画像は zu_1.png / zu_2.png … に割る
CROP_PAD = 40         # 下の余白（背景色と違う最後の行 + これ）

# tenkai_zu.py にそのまま流す口（値を1つ取るもの / 取らないもの）
ZU_VAL = ('--pace', '--ana', '--ana2', '--swap', '--soto', '--uchi',
          '--flip', '--migi', '--odds', '--res',
          # ★ 2026-11-15、調教（CLAUDE.md ルール48・tenkai_zu.py の cyo_tags）。
          #   `cyokyo.py --json` が出した json をそのまま流す。
          '--cyokyo')
ZU_FLAG = ('--noswap', '--c4', '--nomb', '--old', '--svg',
           '--no-cyokyo', '--cyokyo-hyo',
           # ★ 2026-11-15、他のプロジェクトの図に合わせて足した3つを止める口
           #   （tenkai_zu.py の agari / baba_tag / leg の★★）。
           #   --no-agari … 推定の括弧の「・上がり」を出さない
           #   --no-baba-n … 道悪の札の回数（0/3）を出さない
           #   --no-marulegend … 「●赤丸＝狙い」の凡例を出さない
           '--no-agari', '--no-baba-n', '--no-marulegend')


def die(msg, code=2):
    print("\n★ 止めました: %s" % msg)
    sys.exit(code)


def find_chrome():
    """Chromium を /opt/pw-browsers/ から探す。決め打ちしない。"""
    pats = ("/opt/pw-browsers/chromium-*/chrome-linux*/chrome",
            "/opt/pw-browsers/chromium_headless_shell-*/"
            "chrome-headless-shell-linux*/chrome-headless-shell")
    cs = []
    for rank, p in enumerate(pats):           # 版が同じなら handoff と同じ chrome 本体を採る
        for f in glob.glob(p):
            if os.path.isfile(f) and os.access(f, os.X_OK):
                n = re.search(r"-(\d+)/", f)
                cs.append((int(n.group(1)) if n else 0, -rank, f))
    if cs:
        return sorted(cs, reverse=True)[0][2]
    for n in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        f = shutil.which(n)
        if f:
            return f
    return None


def run_mod(mod, argv, quiet=False):
    """既存ツールの main() を、その子の argv を差し替えて呼ぶ。
       （どのツールも main() が sys.argv を読む作りなので、import してこう呼ぶのが素直）"""
    old = sys.argv
    sys.argv = [mod.__name__ + ".py"] + [str(x) for x in argv]
    buf = io.StringIO()
    try:
        if quiet:
            with contextlib.redirect_stdout(buf):
                mod.main()
        else:
            mod.main()
    except SystemExit as e:
        if e.code:
            print(buf.getvalue(), end="")
            die("%s.py が止まりました（終了コード %s）" % (mod.__name__, e.code))
    finally:
        sys.argv = old
    return buf.getvalue()


# ───────────────────────── 画像化 ─────────────────────────

def shot(chrome, html, raw, h):
    import subprocess
    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--force-device-scale-factor=%d" % SCALE,
           "--window-size=%d,%d" % (WIN_W, h),
           "--screenshot=" + raw, "file://" + os.path.abspath(html)]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if not os.path.exists(raw):
        return r.stderr.decode("utf-8", "replace")[-400:] or "画像が出ませんでした"
    return None


def bottom_of(im):
    """背景色と違う最後の行（下の余白を切る位置）"""
    w, h = im.size
    px = im.load()
    bg = px[w - 2, h - 2]
    for y in range(h - 1, -1, -1):
        if any(sum(abs(a - b) for a, b in zip(px[x, y], bg)) > 12
               for x in range(0, w, 7)):
            return y
    return 0


def make_png(chrome, html, out_dir, nraces):
    """HTML → PNG。高さは当てずに、下まで入るまで広げる。8000px超は割る。"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    raw = os.path.join(out_dir, "zu_raw.png")
    for f in glob.glob(os.path.join(out_dir, "zu.png")) + \
             glob.glob(os.path.join(out_dir, "zu_[0-9].png")):
        os.remove(f)                      # 前の回の割れた画像を残さない
    h = min(max(1400, 700 * max(1, nraces) + 700), 16000)
    im = None
    for _ in range(4):
        err = shot(chrome, html, raw, h)
        if err:
            print("   ※ 画像化に失敗: %s" % err)
            return []
        im = Image.open(raw).convert("RGB")
        last = bottom_of(im)
        if last < im.size[1] - 4 or h >= 30000:
            break
        h = min(int(h * 1.8), 30000)       # 下まで入っていない。窓を広げて撮り直す
        print("   ※ 下まで入らなかったので窓を %dpx に広げて撮り直します" % h)
    w, ih = im.size
    last = bottom_of(im)
    im = im.crop((0, 0, w, min(ih, last + CROP_PAD)))
    w, ih = im.size
    outs = []
    if ih <= MAX_PNG:
        p = os.path.join(out_dir, "zu.png")
        im.save(p)
        outs.append((p, w, ih))
    else:
        n = (ih + MAX_PNG - 1) // MAX_PNG
        for i in range(n):
            y0, y1 = i * MAX_PNG, min(ih, (i + 1) * MAX_PNG)
            p = os.path.join(out_dir, "zu_%d.png" % (i + 1))
            im.crop((0, y0, w, y1)).save(p)
            outs.append((p, w, y1 - y0))
    try:
        os.remove(raw)
    except OSError:
        pass
    return outs


# ───────────────────────── 本体 ─────────────────────────

def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    if "--" in a:                      # -- のあとは全部 tenkai_zu.py へ
        i = a.index("--")
        a, extra = a[:i], a[i + 1:]
    else:
        extra = []
    if "--ab" in a:                    # 2枚出す（ルール59）。既定の挙動はこの下のまま
        return run_ab(a, extra)
    run(a, extra)


def strip_val(a, keys):
    """値を1つ取る口（--out / --card）を並びから抜く。`--ab` の中で差し替えるため。"""
    out, i = [], 0
    while i < len(a):
        if a[i] in keys:
            i += 2
            continue
        out.append(a[i])
        i += 1
    return out


def run_ab(a, extra):
    """同じ鞍をA版（地点を混ぜる＝`--pos-mazeru`）とB版（地点をそろえる）の2枚出す。

    CLAUDE.md ルール59 ──「当面、図は鞍ごとに2枚出す。どちらを既定にするかは保留」。
    **差が「地点をそろえたかどうか」だけになるように**、他の口は両版へそのまま同じ値で渡す。
    **出馬表は1回だけ取る** ── A版で取った card.json をB版は `--card` で読み直すので、
    楽天へ行くのは1回だけ（2回引くとオッズが動いて差が地点だけでなくなる）。
    """
    a = [t for t in a if t != "--ab"]
    g = lambda k, d=None: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d
    base = a[0] if a and not a[0].startswith("-") else None
    card_in = g("--card")
    # 出力先は `--out` の下に a/ と b/ を作る（`--out` 無しのときの決め方は run() と同じ）
    root = (g("--out") or os.environ.get("TOJITSU_OUT")
            or (os.path.dirname(os.path.abspath(card_in)) if card_in and not base
                else os.path.join(DEF_OUT, (base or "card")[:8])))
    rest = strip_val(a, ("--out", "--card"))
    ex = [t for t in extra if t != "--pos-mazeru"]   # A版だけに付ける。重ねない
    oa, ob = os.path.join(root, "a"), os.path.join(root, "b")

    print("━━ 2枚出します（ルール59。どちらを既定にするかはユーザーが決める）")
    print("   A版 地点を混ぜる（--pos-mazeru・いまの既定） → %s" % oa)
    print("   B版 地点をそろえる                          → %s" % ob)
    print("   ※ 他の口は両版でまったく同じ。出馬表は1回だけ取ります"
          "（B版はA版の card.json を読み直す）")

    print("\n══════════ A版（地点を混ぜる／--pos-mazeru） ══════════")
    run(rest + (["--card", card_in] if card_in else []) + ["--out", oa],
        ex + ["--pos-mazeru"])

    print("\n══════════ B版（地点をそろえる） ══════════")
    run(rest + ["--card", os.path.join(oa, "card.json"), "--out", ob], ex)

    print("\n━━ 2枚そろいました")
    print("   A版 %s" % os.path.join(oa, "zu.html"))
    print("   B版 %s" % os.path.join(ob, "zu.html"))


def run(a, extra):
    g = lambda k, d=None: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d

    base = a[0] if not a[0].startswith("-") else None
    card_in = g("--card")
    if not base and not card_in:
        die("base16（16桁）か --card <json> のどちらかが要ります。使い方は --help")
    if base and not re.fullmatch(r"\d{16}", base):
        die("base16 が '%s' になっています。**16桁の数字**です"
            "（例 2026111620151201 ＝ 日付8桁+場20+中間15+回12+日01）。\n"
            "  その日の一覧頁で確かめてください ──\n"
            "  https://keiba.rakuten.co.jp/race_card/list/RACEID/<日付8桁>0000000000" % base)

    ven = g("--ven", "大井")
    date = g("--date", "")
    rr = g("--R", "1-12")
    if not re.fullmatch(r"\d{1,2}(-\d{1,2})?", rr):
        die("--R が '%s' になっています。'7' か '7-12' の形です" % rr)
    lo, _, hi = rr.partition("-")
    lo, hi = int(lo), int(hi or lo)
    baba = g("--baba")
    plain = "--plain" in a
    no_img = "--no-img" in a

    out = (g("--out") or os.environ.get("TOJITSU_OUT")
           # --card だけのときは、その card.json が置いてある所に出す
           or (os.path.dirname(os.path.abspath(card_in)) if card_in and not base
               else os.path.join(DEF_OUT, (base or "card")[:8])))
    try:
        os.makedirs(out, exist_ok=True)
    except OSError as e:
        die("出力先 %s を作れません（%s）" % (out, e))
    card = os.path.join(out, "card.json")
    zu = os.path.join(out, "zu.html")
    hyo = os.path.join(out, "hyo.txt")

    print("━━ 当日ワンコマンド  %s %s  %dR〜%dR%s%s" % (
        ven, date or (base or "")[:8], lo, hi,
        ("  馬場 " + baba) if baba else "  （馬場は未指定＝未発表のあいだはこのまま／ルール27）",
        "  [人に見せる版]" if plain else ""))
    print("   出力先 %s" % out)

    # ① 出馬表 ─────────────────────────────────────
    if card_in:
        if not os.path.exists(card_in):
            die("--card の %s がありません" % card_in)
        if os.path.abspath(card_in) != os.path.abspath(card):
            shutil.copyfile(card_in, card)
        print("\n① 出馬表 … --card なので取り直しません（%s）" % card_in)
    else:
        print("\n① 出馬表を取り直します（馬体重・増減・オッズ・人気は当日に入る／ルール3）")
        import syutuba
        run_mod(syutuba, [base, card, "--R", "%d-%d" % (lo, hi)])
    try:
        C = json.load(open(card))
    except Exception as e:
        die("card.json が読めません（%s）" % e)
    if not C:
        if card_in:
            die("%s に鞍が1つも入っていません" % card_in)
        die("出馬表が1鞍も取れませんでした。base16 '%s' がその日のものか、\n"
            "  一覧頁で確かめてください ──\n"
            "  https://keiba.rakuten.co.jp/race_card/list/RACEID/%s0000000000"
            % (base, base[:8]))
    nraces = sum(1 for v in C.values() if lo <= v["R"] <= hi)
    if not nraces:
        die("card.json に %dR〜%dR が入っていません（入っているのは %s）"
            % (lo, hi, ",".join(str(v["R"]) + "R" for v in C.values())))
    nw = sum(1 for v in C.values() for x in v["horses"] if x.get("w"))
    nod = sum(1 for v in C.values() for x in v["horses"] if x.get("odds"))
    print("   %d鞍 ／ 馬体重が入っている馬 %d頭 ／ オッズが入っている馬 %d頭%s" % (
        nraces, nw, nod, "" if (nw and nod) else "  ← 前日はここが空（ルール3）"))

    # ② 隊列図 ─────────────────────────────────────
    print("\n② 隊列図（向きは距離から自動／ルール39・43）")
    zu_args = [card, zu, "--ven", ven, "--R", "%d-%d" % (lo, hi)]
    if date:
        zu_args += ["--date", date]
    if baba:
        zu_args += ["--baba", baba]
    if plain:
        zu_args += ["--plain"]
    for k in ZU_VAL:                   # --pace 7:S のように値が続く口はまとめて渡す
        if k in a:
            zu_args.append(k)
            for tok in a[a.index(k) + 1:]:
                if tok.startswith("--") or tok.startswith("note:"):
                    break
                zu_args.append(tok)
    zu_args += [k for k in ZU_FLAG if k in a]
    zu_args += [t for t in a if t.startswith("note:")]
    zu_args += extra
    import tenkai_zu
    run_mod(tenkai_zu, zu_args)

    # ③ 画像 ───────────────────────────────────────
    pngs = []
    if no_img:
        print("\n③ 画像化 … --no-img なので飛ばします")
    else:
        chrome = find_chrome()
        if not chrome:
            print("\n③ 画像化 … ★ Chromium が /opt/pw-browsers/ に見つかりません。"
                  "HTMLと表だけ作って終わります。")
            print("     探した所: /opt/pw-browsers/chromium-*/chrome-linux*/chrome")
        else:
            print("\n③ 画像化（%s）" % chrome)
            pngs = make_png(chrome, zu, out, nraces)
            for p, w, h in pngs:
                print("   %s  %dx%d" % (p, w, h))

    # ④ 表 ───────────────────────────────────────
    print("\n④ 表（1頭1行。1角posの順／◎は4角0.2以内 ── ルール33・36）\n")
    import ninki
    nargs = [card, "--ven", ven, "--R", "%d-%d" % (lo, hi)]
    if baba:
        nargs += ["--baba", baba]
    txt = run_mod(ninki, nargs, quiet=True)
    print(txt, end="" if txt.endswith("\n") else "\n")
    open(hyo, "w").write(txt)

    # ⑤ どこに何ができたか ───────────────────────────
    print("━━ できたもの")
    print("   出馬表   %s" % card)
    print("   図(HTML) %s" % zu)
    if pngs:
        for p, _, _ in pngs:
            print("   図(PNG)  %s" % p)
    print("   表       %s" % hyo)
    print("   ※ 馬場が出たら --baba を付けて引き直す（ルール27）。"
          "発走30分前にもう一度これを走らせる（ルール3）。")


if __name__ == "__main__":
    main()
