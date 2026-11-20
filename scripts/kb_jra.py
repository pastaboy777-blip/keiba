"""競馬ブック（中央）の「厩舎の話」と「推定タイム」を取る（scripts/ana/kb.conf のcookieが要る）。

  python3 scripts/kb_jra.py --date 2026-11-15            # 取得 → data/kb/danwa_20261115.jsonl
  python3 scripts/kb_jra.py --date 2026-11-15 --summary  # 馬場・位置取りなどのキーワードを馬ごとに表示
  python3 scripts/kb_jra.py --date 2026-11-15 --summary --race 京都11 東京12

手順
  1. 日程ページ /cyuou/nittei/<YYYYMMDD> から /cyuou/cyokuzen/<12桁> を拾う
     12桁 = 年4 + 回2 + 場2 + 日2 + R2。場コードは競馬ブック独自（JRAと違う）なので、
     日程ページの「東京4日目」などの見出しの位置で場名を決める（例 2026-11-15: 04=東京 00=京都 06=福島）
  2. 厩舎の話 /cyuou/danwa/0/<12桁> を1本ずつ、5秒以上あけて取る
  3. 1鞍1行で保存。既に取った鞍は飛ばす（再実行で続きから）
  4. 403/429 などが返ったら即中止（回避しない）

出力1行: {date, place, race_no, race_name, kb_id, course, distance, tenki_baba,
          est_time:{良:秒, 重:秒}, horses:[{umaban, name, mark, short, trainer, comment}]}

data/kb/ は競馬ブックの有料の中身。コミットも外部送信もしない。kb.conf の中身は出さない。
"""
import argparse, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "scripts", "ana", "kb.conf")
OUTDIR = os.path.join(ROOT, "data", "kb")
RAWDIR = os.path.join(OUTDIR, "raw")
BASE = "https://p.keibabook.co.jp"
WAIT = 5.5
PLACES = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]

_last = [0.0]


class Stop(Exception):
    pass


def fetch(path, cache=None):
    """1本取る。前回から WAIT 秒以上あける。200以外は Stop。"""
    if cache and os.path.exists(cache) and os.path.getsize(cache) > 2000:
        return open(cache, encoding="utf-8", errors="replace").read()
    dt = time.time() - _last[0]
    if dt < WAIT:
        time.sleep(WAIT - dt)
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-K", CONF,
                        "-w", "\n__HTTP__%{http_code}", BASE + path], capture_output=True)
    _last[0] = time.time()
    body = r.stdout.decode("utf-8", "replace")
    m = re.search(r"\n__HTTP__(\d+)$", body)
    code = m.group(1) if m else "000"
    body = body[:m.start()] if m else body
    if code != "200":
        raise Stop(f"HTTP {code} {path}")
    # 「まだ提供を開始していない」ページは残さない(残すと公開後の再実行でも空のまま読まれる)
    if cache and "指定されたページは存在しません" not in body:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            f.write(body)
    return body


def txt(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def tsec(s):
    """'2.11.0' -> 131.0 / '1.20.5' -> 80.5 / '59.8' -> 59.8"""
    p = s.split(".")
    try:
        if len(p) == 3:
            return int(p[0]) * 60 + int(p[1]) + int(p[2]) / 10
        if len(p) == 2:
            return float(s)
    except ValueError:
        pass
    return None


def races_from_nittei(h):
    """日程ページから [(kb_id, place)]。場名は直前の『◯◯N日目』見出しで決める。"""
    heads = [(m.start(), m.group(1)) for m in re.finditer(r"(%s)\d+日目" % "|".join(PLACES), h)]
    code2place = {}
    # 直前ページ(cyokuzen)は当日にならないと載らない。前日は出馬表・調教(syutuba/cyokyo)のリンクで場を決める
    for m in re.finditer(r"/cyuou/[a-z]+(?:/\d+)*/(\d{12})", h):
        rid = m.group(1)
        prev = [p for pos, p in heads if pos < m.start()]
        if prev and rid[6:8] not in code2place:
            code2place[rid[6:8]] = prev[-1]
    ids = sorted(set(re.findall(r"/cyuou/[a-z]+(?:/\d+)*/(\d{12})", h)))
    return [(rid, code2place.get(rid[6:8], "?" + rid[6:8])) for rid in ids], code2place


def split_paren(s):
    """'◎(降雨があっても)　友道師――…' -> mark, short, rest。括弧の入れ子に対応。"""
    s = s.strip()
    i = s.find("(")
    if i < 0 or i > 3:
        return "", "", s
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return s[:i].strip(), s[i + 1:j], s[j + 1:].strip(" 　")
    return s[:i].strip(), "", s[i:]


def parse_danwa(h):
    out = {}
    m = re.search(r'class="h1block">\s*<h1>(.*?)</h1>', h, re.S)
    out["race_name"] = txt(m.group(1)) if m else ""
    m = re.search(r'class="raceshibada">\s*\(?([^<)]*)\)?', h)
    out["course"] = txt(m.group(1)) if m else ""
    m = re.search(r'class="racekyori"><button[^>]*>(\d+)m', h)
    out["distance"] = int(m.group(1)) if m else None
    m = re.search(r'class="tenkibaba">([^<]*)<', h)
    out["tenki_baba"] = txt(m.group(1)) if m else ""
    est = {}
    m = re.search(r'class="racenametime">(.*?)</div>', h, re.S)
    if m:
        for k, v in re.findall(r"<p>\s*(良|稍|重|不)\s*([\d.]+)\s*</p>", m.group(1)):
            est[k] = tsec(v)
        r = re.search(r"<p>\s*レコード\s*([\d.]+)", m.group(1))
        if r:
            out["record"] = tsec(r.group(1))
    out["est_time"] = est
    horses = []
    tb = re.search(r'<table class="default danwa".*?</table>', h, re.S)
    for tr in re.findall(r"<tr>(.*?)</tr>", tb.group(0) if tb else "", re.S):
        mu = re.search(r'class="umaban">\s*(\d+)', tr)
        mn = re.search(r'umacd="\d+"[^>]*>([^<]+)</a>', tr)
        md = re.search(r'<td class="danwa">(.*?)</td>', tr, re.S)
        if not (mu and mn):
            continue
        cell = md.group(1) if md else ""
        # 印が画像(SVG)の馬がいる。円2つ(外枠＋塗り)は『◉』として残す
        cell = re.sub(r"<svg.*?</svg>",
                      lambda m: "◉" if m.group(0).count("<circle") >= 2 else "□", cell, flags=re.S)
        body = txt(cell)
        # 書式は2通り。重賞など『○(一言)　調教師――コメント』／条件戦『○【調教師】コメント』
        mb = re.match(r"^([^(（【\s]{0,2})【([^】]+)】(.*)$", body, re.S)
        if mb:
            mark, short, trainer, comment = mb.group(1), "", mb.group(2), mb.group(3)
        else:
            mark, short, rest = split_paren(body)
            trainer, comment = "", rest
            if "――" in rest:
                trainer, comment = rest.split("――", 1)
        horses.append({"umaban": int(mu.group(1)), "name": mn.group(1).strip(),
                       "mark": mark, "short": short, "trainer": trainer.strip(),
                       "comment": comment.strip()})
    out["horses"] = horses
    return out


def do_fetch(date):
    ymd = date.replace("-", "")
    path = os.path.join(OUTDIR, f"danwa_{ymd}.jsonl")
    done = set()
    if os.path.exists(path):
        for l in open(path, encoding="utf-8"):
            try:
                d = json.loads(l)
                if d.get("horses"):
                    done.add(d["kb_id"])
            except ValueError:
                pass
    h = fetch(f"/cyuou/nittei/{ymd}", os.path.join(RAWDIR, f"nittei_{ymd}.html"))
    races, c2p = races_from_nittei(h)
    print("場コード:", " ".join(f"{k}={v}" for k, v in sorted(c2p.items())), f"/ {len(races)}鞍")
    fails = []
    for rid, place in races:
        if rid in done:
            continue
        try:
            hh = fetch(f"/cyuou/danwa/0/{rid}", os.path.join(RAWDIR, f"danwa_{rid}.html"))
        except Stop as e:
            print("中止:", e)
            fails.append(rid)
            break
        d = parse_danwa(hh)
        if not d["horses"]:
            print(f"  {place}{int(rid[-2:])}R {rid}: 厩舎の話が読めない")
            fails.append(rid)
            continue
        rec = {"date": date, "place": place, "race_no": int(rid[-2:]), "kb_id": rid, **d}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  {place}{rec['race_no']:>2}R {rec['race_name'][:20]} {rec['course']} "
              f"推定{rec['est_time']} {len(d['horses'])}頭")
    n = len(load(date))
    print(f"保存 {path}: {n}/{len(races)}鞍" + (f" 失敗 {fails}" if fails else ""))
    check_names(date)


def load(date):
    path = os.path.join(OUTDIR, f"danwa_{date.replace('-', '')}.jsonl")
    if not os.path.exists(path):
        return []
    recs = {}
    for l in open(path, encoding="utf-8"):
        d = json.loads(l)
        recs[d["kb_id"]] = d
    return sorted(recs.values(), key=lambda d: (d["place"], d["race_no"]))


def check_names(date):
    """出馬表(data/jra/shutuba_YYYYMMDD.jsonl)と場・R・馬番で突き合わせ、馬名のずれを出す。"""
    sp = os.path.join(ROOT, "data", "jra", f"shutuba_{date.replace('-', '')}.jsonl")
    if not os.path.exists(sp):
        print("出馬表なし:", sp)
        return
    sh = {}
    for l in open(sp, encoding="utf-8"):
        d = json.loads(l)
        sh[(d["place"], int(d["race_id"][-2:]))] = {h["umaban"]: h["horse_name"] for h in d["result"]}
    bad, n = [], 0
    for d in load(date):
        s = sh.get((d["place"], d["race_no"]))
        if s is None:
            bad.append(f"{d['place']}{d['race_no']}R 出馬表に鞍がない")
            continue
        kb = {h["umaban"]: h["name"] for h in d["horses"]}
        for u in sorted(set(s) | set(kb)):
            n += 1
            if s.get(u) != kb.get(u):
                bad.append(f"{d['place']}{d['race_no']}R {u}番 出馬表={s.get(u)} 競馬ブック={kb.get(u)}")
    print(f"馬名照合: {n}頭中 ずれ {len(bad)}")
    for b in bad:
        print("  ", b)


# --summary のキーワード。NG は誤検出の多い語（重賞・体重・内容…）を先に消すためのもの
KW = {
    "馬場": (r"良馬場|良で|パンパン|道悪|重|渋|雨|時計のかかる",
           r"重賞|体重|重ね|慎重|重視|重要|貴重|重心|二重|比重|重い|重め|重厚|自重|雨天|消化不良|動きが渋"),
    "位置": (r"逃げ|ハナ|先手|積極|控え|後方|差し|内|外|揉まれ|単騎",
           r"内容|以内|案内|身内|内臓|外厩|以外|意外|案外|海外|外国|内心|差し支え|外す|外れ|外し|除外|度外視"),
    "気温": (r"寒い|暑い|夏場|冬", r""),
    "条件": (r"距離|延長|短縮|左回り|右回り|コース", r"コース取り"),
}


def hits(text):
    out = {}
    for k, (pat, ng) in KW.items():
        t = re.sub(ng, "＿", text) if ng else text
        w = sorted(set(re.findall(pat, t)))
        if w:
            out[k] = w
    return out


def sentences(text, pat, ng):
    t = re.sub(ng, lambda m: "\0" * len(m.group(0)), text) if ng else text
    res = []
    pos = 0
    for s in re.split(r"(?<=[。！？])", text):
        seg = t[pos:pos + len(s)]
        pos += len(s)
        if s.strip() and re.search(pat, seg):
            res.append(s.strip())
    return res


def do_summary(date, want):
    for d in load(date):
        tag = f"{d['place']}{d['race_no']}"
        if want and tag not in want:
            continue
        et = " ".join(f"{k}{v:.1f}秒" for k, v in d["est_time"].items() if v)
        print(f"\n== {d['place']}{d['race_no']}R {d['race_name']} {d.get('distance') or ''}m "
              f"{d['course']} {d.get('tenki_baba', '')} 推定[{et}]")
        for h in d["horses"]:
            text = h["short"] + "。" + h["comment"]
            hs = hits(text)
            if not any(k in hs for k in ("馬場", "位置", "気温", "条件")):
                continue
            print(f"  {h['umaban']:>2} {h['name']:<10} {h['mark'] or '-'}({h['short']}) "
                  + " ".join(f"[{k}:{'/'.join(v)}]" for k, v in hs.items()))
            for k, (pat, ng) in KW.items():
                if k in hs:
                    for s in sentences(h["comment"], pat, ng):
                        print(f"       {k}> {s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--check", action="store_true", help="出馬表との馬名照合だけ")
    ap.add_argument("--race", nargs="*", default=[], help="例: 京都11 東京12")
    a = ap.parse_args()
    if a.summary:
        do_summary(a.date, set(a.race))
    elif a.check:
        check_names(a.date)
    else:
        if not os.path.exists(CONF):
            sys.exit("kb.conf がない")
        do_fetch(a.date)


if __name__ == "__main__":
    main()
