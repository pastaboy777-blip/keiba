"""1鞍の結果を、**人気と払戻金つき**で取る ── 楽天の競走成績ページ。ログイン不要。

  python3 kekka.py <RACEID> [--json 出力.json]

RACEID は18桁。**base16（16桁）＋ RR（2桁）**。base16 の意味は syutuba.py の冒頭。

  例  202611132135090509  = 2026/11/13 川崎（場21・第9回・第5日）の 9R
      202611162015110101  = 2026/11/16 大井（場20・第11回・第1日）の 1R

  https://keiba.rakuten.co.jp/race_performance/list/RACEID/<RACEID>

── ★ なぜこれが必要か（CLAUDE.md ルール34）

  **人気は結果ページの人気欄から取る。harvest の `nk` は人気ではない。**

  `harvest.py` の `do_res()` は全着順の行を平らにしてから
  「行の中の最後の1〜2桁の数」を人気として拾っている（`nums[-1]`）。
  行の末尾に来るのは**調教師名のあとの数**なので、馬体重や増減や枠の数を
  拾ってしまう鞍がある。実際に 11/10 川崎7Rでは

    ②nk=7 → 実際**6人気** ／ ③nk=2 → 実際**10人気** ／ ⑦nk=1 → 実際**11人気**

  と3頭とも違っていた。**`nk` を人気として読んだ振り返りはすべて間違い。**
  このツールは `<td class="rank">` を直接読むので、ずれようがない。
  配当も同じ頁の「払戻金」表（`tbody class="repay"`）から取る。

  以前は `scratchpad/chaku.js` と `pay3.js` でやっていたが、一時ディレクトリに
  置いたままコンテナが作り直されて**失われた**。だからここ（リポジトリ）に置く。

── 取れるもの

  鞍    … 場・R・日付・距離・芝ダ・天候・馬場・発走時刻・クラス
          ハロンタイム・上がり4F/3F・コーナー通過順位
  馬    … 着順・枠・馬番・馬名・性齢・負担重量・馬体重と増減・騎手・調教師・
          **人気**・走破タイム・着差・推定上がり・通過順（c1 と c4）
  払戻金 … 単勝・複勝・枠単・枠複・馬複（＝馬連）・馬単・ワイド・三連複・三連単の
          組み合わせ・金額・何番人気

── ★ この頁に単勝オッズの欄は無い

  表の summary は「単勝/複勝オッズ」だが、列は人気までで**倍率は載っていない**。
  だから `odds` は**1着馬だけ**、払戻金の単勝（円÷100）から入れる。
  他の馬の確定オッズが要るなら odds/tanfuku 頁（`rk_odds.js`）を取る。

── ★ コーナーの札は繰り返す（向正面スタートの鞍）

  川崎2000mのような鞍は「３角・４角・１角・２角・３角・４角」と**6つ並ぶ**。
  だから `corner` は**頁に出てきた順のリスト**で返す。最初が最初に通った角、
  最後が最後の4角。`c1` は**最初の角**、`c4` は**最後の角**の位置。
  （`harvest.py` の `corners()` は札で `re.search` するので、こういう鞍では
  「１角」に2周目の手前が、「４角」に1周目の4角が入る。混ぜないこと。）
"""
import re, sys, json, time, unicodedata, subprocess

PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
SLEEP = 1.2
STUB_LEN = 20000          # 楽天の正常なページはこれより長い

# 払戻金の並べる順。馬複は他社の「馬連」
PAYORD = ["単勝", "複勝", "枠単", "枠複", "馬複", "馬単", "ワイド", "三連複", "三連単"]


class Blocked(Exception):
    pass


class NoRace(Exception):
    """絞られたのではなく、その鞍の結果が無い（未確定・取止め・鞍が無い）"""


def get(u):
    """★ 0字（通信落ち）と短いスタブ（絞り）は別物。前者だけリトライする。
       syutuba.py / harvest.py と同じ扱い。粘らない。"""
    h = ""
    for wait in (4, 12, None):
        r = subprocess.run(["curl", "-sS", "--max-time", "45", "-A", UA, u],
                           capture_output=True, timeout=70)
        h = r.stdout.decode("utf-8", "replace")
        if len(h) >= STUB_LEN:
            return h
        if len(h) > 0 or wait is None:
            break
        time.sleep(wait)
    raise Blocked("楽天が %d字 を返しました。%s" % (
        len(h), "通信が続けて落ちました" if not h else
                "スタブです（絞られています）。時間を空けてください"))


def flat(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def nosp(s):
    """名前から空白（全角スペースを含む）を落とす。
       楽天は1字姓を「所　蛍」と全角スペースで埋めてくる。jk_soto.json 側は素の3字。"""
    s = re.sub(r"\s+", "", s or "")
    return s or None


def secs(s):
    """走破タイム「2:18.1」「41.2」を秒に"""
    m, _, r = s.rpartition(":")
    try:
        return round(int(m) * 60 + float(r), 1) if m else float(r)
    except ValueError:
        return None


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def cell(blk, cls):
    """`class="order"` のような1セルの中身を平らにして返す。th でも td でもよい"""
    m = re.search(r'<(?:td|th) class="%s"[^>]*>(.*?)</(?:td|th)>' % cls, blk, re.S)
    return flat(m.group(1)) if m else None


def br(blk, cls):
    """<br> 区切りのセルを行のリストで返す（馬体重「460<br>+3」・騎手「新原周<br>(川崎)」）"""
    m = re.search(r'<(?:td|th) class="%s"[^>]*>(.*?)</(?:td|th)>' % cls, blk, re.S)
    if not m:
        return []
    return [x for x in (flat(y) for y in re.split(r"<br\s*/?>", m.group(1))) if x]


def seq(s):
    """「(9,12),13-3,6」を [[9,12],[13],[3],[6]] に。括弧内は同位（併走）"""
    out = []
    for g in re.findall(r"\(([\d,]+)\)|(\d+)", s):
        out.append([int(x) for x in g[0].split(",")] if g[0] else [int(g[1])])
    return out


def pos_of(sq, ub):
    """括弧つきの並びから、その馬番の順位（括弧内は同位）"""
    p = 1
    for g in sq:
        if ub in g:
            return p
        p += len(g)
    return None


def pay_of(h):
    """払戻金の表（`tbody class="repay"`）→ {券種: [{combi, yen, nin}, …]}

    1つの <tr> に2券種ぶん（左右）入っている。複勝とワイドは <br> で3件。
    """
    m = re.search(r'<tbody class="repay">(.*?)</tbody>', h, re.S)
    if not m:
        return {}
    out = {}
    pat = re.compile(
        r'<th scope="row">\s*([^<\s][^<]*?)\s*</th>\s*'
        r'<td class="number"[^>]*>(.*?)</td>\s*'
        r'<td class="money"[^>]*>(.*?)</td>\s*'
        r'<td class="rank"[^>]*>(.*?)</td>', re.S)
    for lab, cmb, yen, nin in pat.findall(m.group(1)):
        if lab == "備考":
            continue
        cs = [flat(x) for x in re.split(r"<br\s*/?>", cmb)]
        ys = [flat(x) for x in re.split(r"<br\s*/?>", yen)]
        ns = [flat(x) for x in re.split(r"<br\s*/?>", nin)]
        rec = []
        for i, c in enumerate(cs):
            if not c:
                continue
            y = re.search(r"([\d,]+)", ys[i] if i < len(ys) else "")
            n = re.search(r"(\d+)", ns[i] if i < len(ns) else "")
            rec.append({"combi": c, "yen": int(y.group(1).replace(",", "")) if y else None,
                        "nin": int(n.group(1)) if n else None})
        if rec:
            out[lab] = rec
    return out


def parse(h, rid):
    t = flat(h)
    mv = re.search(r'class="racePlace">\s*([^<]+?)\s*<', h)
    mr = re.search(r'class="raceNumber"><span class="num">\s*(\d+)\s*<', h)
    md = re.search(r"(ダ|芝)\s*([\d,]+)m", t)
    mdt = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", t)
    mb = re.search(r"天候：\s*(\S+?)\s+(?:ダ|芝)：\s*(\S+?)\s+発走時刻\s*(\d+:\d\d)", t)
    mc = re.search(r"発走時刻\s*\d+:\d\d\s+(\S+)", t)
    ml = re.search(r"ハロンタイム\s+([\d.\- ]+?)\s+(?:上がり|■|$)", t)
    ma = re.search(r"上がり\s+4F\s+([\d.]+)\s*-\s*3F\s+([\d.]+)", t)

    # ── コーナー通過順位。★ 札は繰り返す（向正面スタート）ので頁の順のまま持つ
    corner = []
    mcn = re.search(r'summary="コーナー通過順位"(.*?)</table>', h, re.S)
    if mcn:
        for kaku, raw in re.findall(
                r'<th scope="row">\s*([１２３４1234])角\s*</th>\s*'
                r'<td[^>]*>\s*([0-9(),=\- ]+?)\s*</td>', mcn.group(1), re.S):
            corner.append({"kaku": kaku + "角", "raw": raw, "seq": seq(raw)})

    # ── 全着順
    i = h.find("全着順")
    if i < 0:
        raise NoRace("全着順が見つかりません（未確定・取止め・鞍が無い のどれか）")
    seg = h[i:h.find("</table>", i)]
    horses, order = {}, []
    for blk in re.split(r"<tr[^>]*>", seg)[1:]:
        if 'class="order"' not in blk:
            continue                                   # thead の見出し行
        ch = cell(blk, "order")
        mu = cell(blk, "number")
        mn = re.search(r'class="horse"[^>]*>\s*(?:<a[^>]*>)?\s*([^<]+?)\s*(?:</a>)?\s*</td>',
                       blk, re.S)
        if not (mu and mu.isdigit() and mn):
            continue
        ub = int(mu)
        wt = br(blk, "weight")                         # 馬体重 / 増減
        jk = br(blk, "jockey")                         # 騎手 / (所属)
        tm = cell(blk, "time")
        sq1 = corner[0]["seq"] if corner else None
        sq4 = corner[-1]["seq"] if corner else None
        rec = {
            "ub": ub,
            # 着順。取消・除外・中止の鞍は数字でないので chaku=None にして status に残す
            "chaku": int(ch) if ch and ch.isdigit() else None,
            "status": None if (ch and ch.isdigit()) else (ch or None),
            "waku": int(cell(blk, "position") or 0) or None,
            "name": mn.group(1).strip(),
            "sei": (cell(blk, "state") or "").replace(" ", "") or None,
            "kin": num(cell(blk, "weightTax")),
            "w": int(wt[0]) if wt and wt[0].isdigit() else None,
            "dw": wt[1].replace("±", "+") if len(wt) > 1 else None,
            # 減量記号（△▲◇☆★◎）は外す ── CLAUDE.md ルール21★
            "jk": nosp(re.sub(r"^[△▲◇☆★◎]+", "", jk[0])) if jk else None,
            "jk_shozoku": jk[1].strip("()（）") if len(jk) > 1 else None,
            "tr": nosp(cell(blk, "tamer")),
            # ★★ これが本命。頁の人気欄をそのまま読む（harvest の nk は人気ではない）
            "nin": int(cell(blk, "rank")) if (cell(blk, "rank") or "").isdigit() else None,
            "t": secs(tm) if tm else None,
            "sa": cell(blk, "lead") or None,
            "agari": num(cell(blk, "spurt")),
            "odds": None,                              # ★ この頁に倍率の欄は無い（1着だけ後で入れる）
            "tsuka": [pos_of(c["seq"], ub) for c in corner],
            "c1": pos_of(sq1, ub) if sq1 else None,
            "c4": pos_of(sq4, ub) if sq4 else None,
        }
        horses[str(ub)] = rec
        if rec["chaku"]:
            order.append((rec["chaku"], ub))

    pay = pay_of(h)
    # 1着の単勝オッズだけ、払戻金から埋める（円÷100）
    for p in pay.get("単勝", []):
        if p["combi"] in horses and p["yen"]:
            horses[p["combi"]]["odds"] = round(p["yen"] / 100.0, 1)

    return {
        "rid": rid,
        "venue": mv.group(1).strip() if mv else None,
        "R": int(mr.group(1)) if mr else (int(rid[-2:]) if rid[-2:].isdigit() else None),
        "date": "%04d-%02d-%02d" % tuple(int(x) for x in mdt.groups()) if mdt else None,
        "dist": int(md.group(2).replace(",", "")) if md else None,
        "sur": md.group(1) if md else None,
        "tenko": mb.group(1) if mb else None,
        "baba": mb.group(2) if mb else None,
        "start": mb.group(3) if mb else None,
        "cls": mc.group(1) if mc else None,
        "lap": [float(v) for v in ml.group(1).split("-")] if ml else [],
        "agari4": num(ma.group(1)) if ma else None,
        "agari3": num(ma.group(2)) if ma else None,
        "corner": corner,
        "chaku": [u for _, u in sorted(order)],
        "horses": horses,
        "pay": pay,
    }


def w(s):
    """全角を2、半角を1で数えた表示幅"""
    return sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - w(s))


def show(v):
    print("%s %dR  %s  %s%sm  %s/%s  %s発走  %s" % (
        v["venue"] or "?", v["R"] or 0, v["date"] or "?", v["sur"] or "",
        v["dist"] or 0, v["tenko"] or "?", v["baba"] or "?",
        v["start"] or "?", v["cls"] or ""))
    if v["lap"]:
        print("  ハロン %s   上がり 4F %s - 3F %s" % (
            "-".join("%.1f" % x for x in v["lap"]), v["agari4"], v["agari3"]))
    for c in v["corner"]:
        print("  %s %s" % (c["kaku"], c["raw"]))
    print()
    print("着 枠 馬番 %s %s %s タイム   %s 上り  通過" % (
        pad("馬名", 18), pad("騎手", 8), pad("人気", 6), pad("着差", 9)))
    rows = sorted(v["horses"].values(),
                  key=lambda x: (x["chaku"] is None, x["chaku"] or 0, x["ub"]))
    for x in rows:
        print("%s %s %s  %s %s %s %s %s %s  %s" % (
            pad(x["chaku"] if x["chaku"] else (x["status"] or "-"), 2),
            pad(x["waku"] or "-", 2), pad(x["ub"], 3),
            pad(x["name"], 18), pad(x["jk"] or "?", 8),
            pad("%d人気" % x["nin"] if x["nin"] else "?", 6),
            pad(("%d:%04.1f" % (int(x["t"] // 60), x["t"] % 60))
                if x["t"] and x["t"] >= 60
                else (("%.1f" % x["t"]) if x["t"] else "-"), 7),
            pad(x["sa"] or "", 9), pad(x["agari"] or "-", 5),
            "-".join(str(p) if p else "?" for p in x["tsuka"]) or "-"))
    if v["horses"]:
        print()
        print("  ".join("%d着 %s番%s" % (
            v["horses"][str(u)]["chaku"], u,
            "(%d人気)" % v["horses"][str(u)]["nin"] if v["horses"][str(u)]["nin"] else "")
            for u in v["chaku"][:3]))
    pay = v.get("pay") or {}
    if pay:
        print("\n── 払戻金")
        for lab in PAYORD + [k for k in pay if k not in PAYORD]:
            for p in pay.get(lab, []):
                print("  %s %-10s %9s円  %s" % (
                    pad(lab, 6), p["combi"],
                    "{:,}".format(p["yen"]) if p["yen"] else "?",
                    "%d番人気" % p["nin"] if p["nin"] else ""))


def main():
    a = sys.argv[1:]
    if not a or not re.fullmatch(r"\d{18}", a[0]):
        print(__doc__); return
    rid = a[0]
    out = a[a.index("--json") + 1] if "--json" in a else None
    try:
        v = parse(get(PERF + rid), rid)
    except Blocked as e:
        print("★ 止めました:", e)
        print("  粘らないこと。時間を空けてやり直す。")
        sys.exit(1)
    except NoRace as e:
        print("★ %s  RACEID=%s" % (e, rid))
        sys.exit(2)
    if out:
        json.dump(v, open(out, "w"), ensure_ascii=False, indent=1)
        print("%s %dR  %d頭  人気%d頭  払戻%d券種 → %s" % (
            v["venue"], v["R"] or 0, len(v["horses"]),
            sum(1 for x in v["horses"].values() if x["nin"]),
            len(v["pay"]), out))
    else:
        show(v)


if __name__ == "__main__":
    main()
