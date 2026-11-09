"""楽天競馬から結果を取る ── ラップ・コーナー通過順・着順を、ログイン無しで。

競馬ブックは cookie が切れると通過順もラップも ＊＊＊＊ になる（10/22に実際に切れた）。
楽天は会員登録なしで、しかも **コーナー通過順が括弧つきの生の形** で載っている。
競馬ブックより取れる情報が多い場面があるので、こちらを基本線にしてよい。

  python3 rakuten.py 2026 10 22 18            # 年 月 日 場コード（浦和18）
  python3 rakuten.py 2026 10 22 18 --save     # rakuten_lap.jsonl に追記
  python3 rakuten.py --lap33                  # 貯めたぶんの33ラップ一覧

RACEID の作り方（トップページの「本日のレース」リンクから取る）
  20261022 1813070400  =  日付8桁 + 場2 + 回2 + ？2 + 日2 + R2
  最後の2桁だけ 01〜12 に差し替えれば各鞍になる。
  場の2桁は 浦和18 / 川崎21 / 船橋19 / 大井20 / 笠松23 / 園田27 / 門別36。
  回・日の部分は開催ごとに変わるので、毎回トップから拾う（固定値を書かない）。

33ラップ = 前半3F − 後半3F（800mだけ 1F目 − 4F目）。プラスが瞬発力勝負、
マイナスが持久力勝負。notes/live/pdf_shinbun_bachu.md 参照。
"""
import re, os, sys, json, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "rakuten_lap.jsonl")
TOP = "https://keiba.rakuten.co.jp/"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/"
UA = "Mozilla/5.0"


def get(url):
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-A", UA, url],
                       capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def base_id(y, m, d, jyo):
    """その日・その場の RACEID の頭16桁をトップページから拾う"""
    key = "%04d%02d%02d%02d" % (y, m, d, jyo)
    h = get(TOP)
    for rid in re.findall(r"race_card/list/RACEID/(\d{18})", h):
        if rid.startswith(key):
            return rid[:16]
    return None


def flat(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def corners(t):
    """「１角 (3,6),(2,9),11,8...」を {角: [[同着グループ], ...]} に"""
    out = {}
    for k, lab in ((1, "１角"), (2, "２角"), (3, "３角"), (4, "４角")):
        m = re.search(lab + r"\s+([0-9(),=\- ]+?)(?:[１-４]角|■|$)", t)
        if not m:
            continue
        seq = []
        for g in re.findall(r"\(([\d,]+)\)|(\d+)", m.group(1)):
            seq.append([int(x) for x in g[0].split(",")] if g[0] else [int(g[1])])
        if seq:
            out[k] = seq
    return out


def pos_of(seq, ub):
    """括弧つきの並びから、その馬番の順位（括弧内は同位）を出す"""
    p = 1
    for g in seq:
        if ub in g:
            return p
        p += len(g)
    return None


def parse(h):
    t = flat(h)
    rec = {}
    m = re.search(r"ハロンタイム\s+([\d.\- ]+?)\s+上がり", t)
    rec["lap"] = [float(v) for v in m.group(1).split("-")] if m else []
    m = re.search(r"上がり\s*4F\s*([\d.]+)\s*-\s*3F\s*([\d.]+)", t)
    rec["race_4f"] = float(m.group(1)) if m else None
    rec["race_3f"] = float(m.group(2)) if m else None
    m = re.search(r"(ダ|芝)([\d,]+)m", t)                 # 「ダ1,500m」とカンマが入る
    rec["dist"] = int(m.group(2).replace(",", "")) if m else None
    m = re.search(r"天候：\s*(\S+)\s+(?:ダ|芝)：\s*(\S+)", t)
    rec["tenko"], rec["baba"] = (m.group(1), m.group(2)) if m else (None, None)
    cn = corners(t)
    rec["corner"] = {str(k): v for k, v in cn.items()}

    rows = []
    # 「着 枠 馬番 馬名 性齢/毛色 斤量 馬体重 増減 騎手(所属) タイム 着差 上がり 調教師 人気」
    # 増減は「±0」と全角の記号で出る。着差は「１ １／２」のように全角で空白を含む。
    # 走破タイムは 1400m なら「1:31.0」、800m なら「47.7」と分が付かない。
    pat = re.compile(
        r"(\d+)\s+\d+\s+(\d+)\s+([ァ-ヶー]{2,})\s+[牡牝セ騸扇]\d+\s*/\S+\s+[\d.]+\s+"
        # 騎手名は「☆所 蛍 (船橋)」のように減量記号と空白が入ることがある
        r"(\d+)\s+([-+±]\d+)\s+[^()0-9]{1,14}?\s*\([^)]*\)\s+"
        r"(?:(\d+):)?(\d+\.\d)[^0-9]{0,16}?([34]\d\.\d)\s+\S+?\s+(\d+)\b")
    # 800m は3角・4角しかない。最初に出てくる角を「道中の位置」として使う
    first = min(cn) if cn else None
    for m in pat.finditer(t):
        ch, ub, nm, wt, dw, mi, se, ag, nk = m.groups()
        rows.append({"chaku": int(ch), "ub": int(ub), "name": nm,
                     "wt": int(wt), "dw": int(dw.replace("±", "")),
                     "time": (int(mi) * 60 if mi else 0) + float(se),
                     "agari": float(ag), "nk": int(nk),
                     "c1": pos_of(cn.get(first, []), int(ub)) if first else None,
                     "c4": pos_of(cn.get(4, []), int(ub))})
    rec["rows"] = rows
    return rec


def lap33(lap):
    """33ラップ = 前半3F − 後半3F。

    1500m は先頭が100mの端数区間（7.4秒など）で出る。これを1Fとして数えると
    前半3Fが500mぶんになり、−9.4 のような他距離と比べられない値になる。
    10秒未満の先頭区間は端数とみなして落とし、最初の「丸い3F」から数える。
    """
    lap = list(lap)
    if lap and lap[0] < 10.0:
        lap = lap[1:]
    if len(lap) < 4:
        return None
    if len(lap) == 4:                       # 800m は 1F目 − 4F目
        return round(lap[0] - lap[3], 2)
    return round(sum(lap[:3]) - sum(lap[-3:]), 2)


def main():
    if "--lap33" in sys.argv and len(sys.argv) == 2:
        if not os.path.exists(DATA):
            print("まだ何も貯まっていません"); return
        print("  日付        R 距離  33ラップ  ハロン")
        for l in open(DATA):
            r = json.loads(l)
            v = lap33(r["lap"])
            print("  %s %2d %4d  %+7.1f  %s" % (r["date"], r["R"], r["dist"] or 0,
                  v if v is not None else 0, "-".join("%.1f" % x for x in r["lap"])))
        return
    if len(sys.argv) < 5:
        print(__doc__); return
    y, m, d, jyo = (int(x) for x in sys.argv[1:5])
    bid = base_id(y, m, d, jyo)
    if not bid:
        print("トップページにその日・その場のレースが見つかりません。"
              "開催日か場コードを確認してください。"); return
    print("RACEID の頭:", bid, flush=True)
    seen = set()
    if os.path.exists(DATA):
        seen = {json.loads(l)["rid"] for l in open(DATA) if l.strip()}
    out = []
    for R in range(1, 13):
        rid = "%s%02d" % (bid, R)
        if rid in seen and "--save" in sys.argv:
            print("%2dR skip" % R, flush=True); continue
        rec = parse(get(PERF + rid))
        if not rec["lap"]:
            print("%2dR ラップなし（未発走か、ページ構造が変わっています）" % R, flush=True)
            time.sleep(0.6); continue
        rec.update(rid=rid, R=R, date="%04d-%02d-%02d" % (y, m, d))
        out.append(rec)
        w = [x for x in rec["rows"] if x["chaku"] == 1]
        v = lap33(rec["lap"])
        print("%2dR %4dm 33ラップ%+6.1f  %s   1着 %s" %
              (R, rec["dist"] or 0, v if v is not None else 0,
               "-".join("%.1f" % x for x in rec["lap"]),
               w[0]["name"] if w else "?"), flush=True)
        time.sleep(0.6)
    if "--save" in sys.argv and out:
        with open(DATA, "a") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("保存 %d鞍 → %s" % (len(out), DATA))


if __name__ == "__main__":
    main()
