"""馬体重を「その馬が走れた体重帯」から見る。

  python3 taiju.py <card.json> [R...]        # 鞍ごとに全頭
  python3 taiju.py <card.json> --warn        # 注意が要る馬だけ

card.json は card23.py（楽天の出馬表）が吐く形。各過去走に馬体重(w)が入っている。

── なぜ「前走からの増減」だけでは足りないか

白井寿昭調教師の考え方（鈴木ショータ氏のコラムより）。

  「必要な肉を付け、余計な肉が落ちていくと、競走馬の体重はデビューした頃に戻っていく」

スペシャルウィークはデビュー464kg、引退の有馬記念も464kg。唯一の惨敗だった
京都大賞典が **キャリア最高の486kg**、次走の天皇賞(秋)はそこから −16kg で復活。
ジェンティルドンナのジャパンカップも −14kg が狙い通りの数字だった。

つまり見るべきは「増えたか減ったか」ではなく、

  ① その馬が3着内に来たときの体重帯（＝走れる体重）から、今どれだけ離れているか
  ② 前走がキャリア最高体重ではなかったか（＝余計な肉が乗っていた可能性）
  ③ 前走がキャリア最低体重ではなかったか（＝細すぎ・消耗）

出すのは3つ。

  好走帯   … 3着内のときの馬体重の平均（なければ全走の平均）
  前走差   … 前走の体重 − 好走帯
  最高/最低 … 前走がキャリアの最高体重／最低体重だったか

★ 当日の体重は出馬表に入る（kb.syutuba の w / dw）。前日は空。
  CLAUDE.md ルール3・4 のとおり、**発走30分前に取り直して、
  そのレースの平均との差でも見る**。このファイルは前日に出せるぶんだけ。
"""
import sys, json, os, statistics as st


def prof(h):
    runs = [r for r in h.get("past", []) if r.get("w")]
    if not runs:
        return None
    ws = [r["w"] for r in runs]
    good = [r["w"] for r in runs if r["chaku"] <= 3]
    band = st.mean(good) if good else st.mean(ws)
    p = runs[0]
    return {"n": len(runs), "band": round(band, 1), "ngood": len(good),
            "pw": p["w"], "pchaku": p["chaku"], "pdate": p.get("date"),
            "d": round(p["w"] - band, 1),
            "hi": max(ws), "lo": min(ws),
            "at_hi": p["w"] == max(ws) and len(runs) >= 3,
            "at_lo": p["w"] == min(ws) and len(runs) >= 3,
            "range": max(ws) - min(ws)}


def note(z):
    """買い方に効く一言。無ければ空。

    出馬表に載る過去走は5走ぶんしかないので「キャリア最高体重」とは言えない。
    言えるのは「直近5走のなかで最も重かった／軽かった」まで。しかも体重が
    数キロしか動かない馬ではその最高・最低に意味がないので、
      ・3着内の実績があること（好走帯が実在すること）
      ・直近5走の体重の幅が10kg以上あること
      ・好走帯から6kg以上ずれていること
    の3つを満たしたときだけ出す。
    """
    if not z["ngood"] or z["range"] < 10:
        return ""
    if z["d"] >= 6 and z["pchaku"] > 3:
        return "★好走帯より%+.0fkg。前走は直近で最も重く着外%s" % (
            z["d"], "" if z["at_hi"] else "（最重ではない）")
    if z["d"] >= 6 and z["pchaku"] <= 3:
        return "好走帯より%+.0fkgでも好走。重いほうが走るタイプ" % z["d"]
    if z["d"] <= -6:
        return "▲好走帯より%.0fkg軽い%s" % (
            z["d"], "。直近で最も細い" if z["at_lo"] else "")
    return ""


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    D = json.load(open(sys.argv[1]))
    rs = [int(x) for x in sys.argv[2:] if x.isdigit()] or sorted(int(k) for k in D)
    warn = "--warn" in sys.argv
    for R in rs:
        v = D[str(R)]
        print("=" * 92)
        print("%2dR %sm %s  %d頭" % (R, v["dist"], v.get("cls", ""), len(v["horses"])))
        print("   馬番 馬名           走数 好走帯  前走体重(着)   帯との差  幅   備考")
        for h in v["horses"]:
            z = prof(h)
            if not z:
                if not warn:
                    print("   %2d  %-13s  （過去の体重が引けません）" % (h["ub"], h["name"][:13]))
                continue
            nt = note(z)
            if warn and not nt:
                continue
            print("   %2d  %-13s %3d %6.1f  %4d(%2d着)%s%s %7.1f %4d  %s" % (
                h["ub"], h["name"][:13], z["n"], z["band"], z["pw"], z["pchaku"],
                "最高" if z["at_hi"] else ("最低" if z["at_lo"] else "　　"),
                "", z["d"], z["range"], nt))


if __name__ == "__main__":
    main()
