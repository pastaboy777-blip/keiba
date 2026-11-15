"""出馬表から**父と母父**を抜く ── netkeiba も血統キャッシュも要らない。

  python3 ketto.py <base16> <ラベル>      # その日の全鞍ぶん取って保存
  python3 ketto.py --show <ラベル>        # 取ったものを出す

── ★ 2026-11-01 に気づいたこと

楽天の出馬表には、はじめから **父馬 ／ 馬名 ／ 母馬 ／（母父馬）** が並んでいる。

    消 シャンハイボビー カンサッリス ニシノアスカ (ドリームジャーニー)
       └父─────────┘ └馬名──┘ └母────┘  └母父────────┘

`syutuba.py` は同じページを取りながら、ここを読んでいなかった。
**血統のために netkeiba を叩く必要はない。**出馬表1ページで父と母父が揃う。

── 何に使うか

血統ペース理論（MASA氏）の判定のうち、**機械で引けるのはB条件だけ**。

    C … 形相遺伝系統が逃げ馬の系統と親和性のある範囲にある
          → 形相遺伝対象（どの先祖を見るか）は人の判断。**引けない**
    B … さらに **父系と母父系の組み合わせ**まで一致する
          → 父と母父が分かれば引ける。**ここだけが機械で出せる**

★ 系統（Kingmambo系・Northern Dancer系…）に畳むには種牡馬→系統の対応表が要る。
  父と母父の「名前そのもの」の一致なら、対応表なしで今すぐ引ける。
  名前一致は当たりが少ない（南関は種牡馬が分散している）ので、系統に畳むのが本筋。
"""
import sys, json, os, re, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import syutuba as S

SLEEP = 4.0


def parse(t, names):
    """出馬表の本文から {馬名: {"f": 父, "mf": 母父, "m": 母}} を作る。

    ★ 父も母父も外国名だと空白を含む（例 `Ｙｅｓ Ｉｔ’ｓ Ｔｒ`）ので、
      区切りを空白に頼ると壊れる。**既知の馬名で挟み撃ちにする。**

    ★ 1回目の作りはここを間違えた（2026-11-01）。
      `消\\s+(.+?)\\s+<馬名>...` で探すと、その馬の直前の「消」ではなく
      **もっと前の馬の「消」から始まって、間の過去走を全部飲み込む**ことがある。
      非貪欲でも、始点が手前にあれば止まらない。
      **「消 」で切ってから、その塊の先頭だけを見る。**
    """
    out, want = {}, set(names)
    for chunk in t.split("消 "):
        head = chunk[:120]
        # その塊の先頭に現れる既知の馬名（いちばん手前のもの）
        cand = [(head.find(n), n) for n in want if head.find(n) > 0]
        if not cand:
            continue
        i, nm = min(cand)
        f = head[:i].strip()
        if not f or len(f) > 22:          # 父の位置に別の何かが来ている
            continue
        m = re.match(r"\s*(.+?)\s*\(([^)]*)\)", chunk[i + len(nm):i + len(nm) + 80])
        if m:
            out[nm] = {"f": f, "m": m.group(1).strip(), "mf": m.group(2).strip()}
    return out


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--show" in a:
        lab = a[a.index("--show") + 1]
        D = json.load(open(os.path.join(HERE, "harvest", lab + "_ketto.json")))
        for nm in sorted(D):
            print("%-18s 父 %-18s 母父 %s" % (nm, D[nm]["f"], D[nm]["mf"]))
        print("\n%d頭" % len(D))
        return
    base, lab = a[0], a[1]
    card = a[a.index("--card") + 1] if "--card" in a else None
    want = {}
    if card:
        C = json.load(open(card))
        for k in C:
            want[C[k]["R"]] = [h["name"] for h in C[k]["horses"]]
    path = os.path.join(HERE, "harvest", lab + "_ketto.json")
    out = json.load(open(path)) if os.path.exists(path) else {}
    for R in range(1, 13):
        names = want.get(R)
        if not names:
            continue
        if all(n in out for n in names):
            print("%2dR 取得済み" % R); continue
        # ★ 生ページを残す。パーサを直すたびに取り直すのは楽天に無駄な負荷をかける
        raw = os.path.join(HERE, "harvest", "%s_card%02d.txt" % (lab, R))
        if os.path.exists(raw):
            t = open(raw, encoding="utf-8").read()
        else:
            t = S.flat(S.get(S.CARD + base + "%02d" % R))
            open(raw, "w", encoding="utf-8").write(t)
            time.sleep(SLEEP)
        got = parse(t, names)
        out.update(got)
        print("%2dR %2d頭中 %2d頭  例 %s" % (
            R, len(names), len(got),
            next(("%s（父%s・母父%s）" % (n, got[n]["f"], got[n]["mf"])
                  for n in names if n in got), "なし")), flush=True)
        json.dump(out, open(path, "w"), ensure_ascii=False, indent=0, sort_keys=True)
    print("\n計 %d頭" % len(out))


if __name__ == "__main__":
    main()
