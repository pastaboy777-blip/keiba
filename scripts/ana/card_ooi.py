"""大井の印 ── 前開催（第10回・10/4〜10/9）の64鞍712頭で測った形。

  python3 card_ooi.py <card.json> [ped.json] [R...]
  python3 card_ooi.py ... --why 5      # その鞍の内訳を全部出す

  card.json … syutuba.py が吐く楽天の出馬表（過去5走・枠つき）
  ped.json  … kettou.py の parse 結果を鞍ごとに並べたもの（任意）

── ★ なぜ card.py（浦和用）と別ファイルなのか

  同じ物差しが使えない。数字が逆を向いている。詳細は notes/live/ketto_ooi.md

  | | 浦和 | 大井 |
  |---|---|---|
  | 位置    | 中団前めが最上位。「差し馬から選ぶ」 | **4角先頭〜2番手が最強**。中団2.9〜7.1% |
  | gain    | 穴の主役（押し上げた馬） | **効かない**。+3以上10.5% ≒ 不動12.9% |
  | 上がり  | 点数の主軸 | **主変数にならない**（幅が4.0秒に届かない） |
  | 馬体重  | 効かなかった | **効く**。平均−20kg以下は172頭で4勝 |
  | 血統    | 母系SSが説明に使えた | 位置をそろえると消える |

  分岐で済ませると、どちらの場の話か読めなくなる。場ごとにファイルを分ける。

── 何を見るか（効く順）

  ① 位置    過去走の4角相対位置。前め型を上に、後方型を強く下げる
  ② 下げない 道中で順位を下げる型を減点（gainの加点はしない）
  ③ 枠      1200m以下は3〜5枠、1400mは1〜2枠。1600m以上は不問
  ④ 馬体重  そのレースの平均との差。軽い馬を切る（★当日に取り直す）
  ⑤ 上がり  補助。同じ距離帯のみ（ルール2）。点は小さい
  ⑥ 父      AEI/CPI（NAR版）の上位40位に入る種牡馬か

── ⑥を入れた理由（10/24に測った）

  これまで試した血統の指標は、人気か位置をそろえると全部消えた。
  AEI/CPI の上位40位に入る父かどうかだけは、どちらをそろえても残った。

      1〜40位に有  149頭 14.1%勝 32.2%複 平均人気5.62
      表の外       563頭  7.8%勝 25.6%複 平均人気6.36

      人気をそろえて   4〜6番人気   有12.5%  外 3.6%
      4角をそろえて    3〜4番手     有28.6%  外11.1%

  AEI/CPI は血の配合ではなく「その種牡馬個体の質」を、相手の母の質で割って
  測っている。良血をあてがわれただけの種牡馬は 1.0 に戻る。
  ロブチェンで確かめた「血統表ではなく、どの体が出た個体を種牡馬にしたか」と
  測っているものが同じ。詳細は notes/live/ketto_robuchen.md

  ただし 1開催・149頭で21勝。点は控えめ（+2）。

── ★ 当日にやること（ルール3・ルール4）

  馬体重・増減・オッズ・人気は前日の出馬表では空。**発走30分前に
  syutuba.py を回し直してから印を打ち直す。**
  前日のカードは下見。
"""
import sys, os, json, importlib.util, statistics as st

_kt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kettou.py")
_sp = importlib.util.spec_from_file_location("kettou", _kt)
kettou = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(kettou)

MK = ["◎", "○", "▲", "△", "△"]
FORCE, DROP, FORCE_ANA = {}, {}, {}     # {R: {順位: 馬番}} / {R: [馬番]} / {R: 馬番}

# NAR版 AEI/CPI比の上位40位（2026-10-25 にユーザーから受け取った表）。
# ★ 2018年以降の産駒が0頭の種牡馬は、今の出馬表には出てこない。
#   実際、前開催の大井712頭に ノーザンテースト・デヒア・アフリート・
#   キングカメハメハ・サウスヴィグラス・ディープインパクト・クロフネ・
#   フォーティナイナー は1頭もいなかった。残していても害はないので全部入れてある。
AEI40 = {
    "ノーザンテースト", "デヒア", "ホッコータルマエ", "アフリート", "バンブーエール",
    "キングカメハメハ", "サウスヴィグラス", "ゴールドドリーム", "タバスコキャット",
    "シニスターミニスター", "アジュディケーティング", "ブライアンズタイム", "ドレフォン",
    "リアルスティール", "ジェイドロバリー", "エスポワールシチー", "ダノンレジェンド",
    "パイロ", "キンシャサノキセキ", "ディープインパクト", "カレンブラックヒル",
    "アグネスデジタル", "ヘニーヒューズ", "サンデーサイレンス", "フォーティナイナー",
    "ロージズインメイ", "ヨハネスブルグ", "クロフネ", "モーニン", "スワーヴリチャード",
    "ニシケンモノノフ", "マイネルラヴ", "カコイーシーズ", "ハーツクライ",
    "ダンシングブレーヴ", "キングヘイロー", "ウォーニング", "ミスターメロディ",
    "ホワイトマズル", "トニービン",
}


# ────────────────────────── 過去走

def band(runs, d):
    """ルール2。上がりは同じ距離帯のぶんしか使わない"""
    if d <= 1000:
        return [r for r in runs if r["dist"] <= 1000]
    return [r for r in runs if abs(r["dist"] - d) <= 200]


def medians(D):
    pool = {}
    for v in D.values():
        for h in v["horses"]:
            for r in h["past"]:
                pool.setdefault((r["venue"], r["dist"]), []).append(r["agari"])
    return {k: st.median(v) for k, v in pool.items() if len(v) >= 4}


def prof(h, d, MED):
    runs = h["past"]
    if not runs:
        return None
    b = band(runs, d)
    use = b or runs
    z = {"xband": not b, "n": len(runs)}
    e = [r["agari"] - MED[(r["venue"], r["dist"])]
         for r in b if (r["venue"], r["dist"]) in MED]
    z["edge"] = round(sum(e) / len(e), 2) if e else None
    # 4角の相対位置。0 が先頭、1 が最後方
    pr = [(r["c4"] - 1) / max(1, r["n"] - 1) for r in use if r["c4"]]
    z["prel"] = round(sum(pr) / len(pr), 3) if pr else None
    z["pbest"] = round(min(pr), 3) if pr else None
    # ★ gain は加点しない。「下げる型かどうか」だけ見る
    g = [r["c1"] - r["c4"] for r in use if r["c1"] and r["c4"]]
    z["drop"] = round(sum(1 for x in g if x <= -2) / len(g), 2) if g else None
    z["inrate"] = round(sum(1 for r in use if r["chaku"] <= 3) / len(use), 2)
    z["frontwin"] = sum(1 for r in use if r["c4"] and r["c4"] <= 3 and r["chaku"] <= 3)
    p = runs[0]
    z["pchaku"], z["psa"], z["pdist"], z["pven"] = (
        p["chaku"], p["sa"], p["dist"], p["venue"])
    z["lastw"] = p.get("w")
    return z


# ────────────────────────── 点をつける

def pos_pt(z, d):
    """① 位置 ── これが大井でいちばん効く。

    前開催64鞍。1400m以上は4角後方158頭が0勝、中団も7.1%しかない。
    1200m以下は中団2.9%・後方1.1%。**前にいない馬は買えない。**
    """
    p = z["prel"]
    if p is None:
        return 0, ""
    short = d <= 1200
    if p < 0.18:
        return (6 if short else 5), "4角で先頭〜2番手"
    if p < 0.35:
        return 5, "4角3〜4番手"
    if p < 0.52:
        return (1 if short else 2), "4角で中団前め"
    if p < 0.68:
        return (-3 if short else -2), "4角で中団"
    return (-6 if short else -7), "4角で後方"


def drop_pt(z):
    """② 下げない ── 道中で順位を下げる馬は、前開催で1.1〜4.5%しか勝っていない"""
    dr = z["drop"]
    if dr is None:
        return 0, ""
    if dr >= 0.6:
        return -4, "道中で下げる型"
    if dr >= 0.35:
        return -2, "ときどき下げる"
    return 0, ""


def waku_pt(wk, d):
    """③ 枠 ── 距離で逆転する。

    1000〜1200m  1-2枠10.4% / 3-5枠15.0% / 6-8枠 3.4%
    1400m        1-2枠17.6% / 3-5枠 6.6% / 6-8枠 8.9%
    1600m以上    8.0 / 9.3 / 8.9 ── 不問
    """
    if not wk:
        return 0, ""
    if d <= 1200:
        if 3 <= wk <= 5:
            return 2, "3〜5枠"
        if wk >= 6:
            return -3, "外枠（1200mは6-8枠が3.4%）"
        return 0, ""
    if d <= 1400:
        return (2, "内枠") if wk <= 2 else (0, "")
    return 0, ""


def weight_pt(h, mean_w, d):
    """④ 馬体重 ── そのレースの平均との差（ルール4）。

    1400m以下  +20kg以上 9.5% / ±8 14.3% / −20kg以下 **1.9%**
    1600m以上  +20kg以上 **14.9%** / ±8 6.0% / −20kg以下 **3.0%**

    ★ 当日の体重が入っていれば当日のを、前日は直近の過去走の体重を使う。
      前日のは下見。発走30分前に取り直すこと。
    """
    w = h.get("w") or h.get("_lastw")
    if not w or mean_w is None:
        return 0, ""
    dd = w - mean_w
    today = " " if h.get("w") else "（前走の体重・要取り直し）"
    if dd <= -20:
        return -5, "平均より%.0fkg軽い%s" % (dd, today)
    if dd <= -8:
        return -2, "平均より%.0fkg軽い%s" % (dd, today)
    if dd >= 20:
        return (3 if d >= 1600 else 0), "平均より+%.0fkg%s" % (dd, today)
    if dd >= 8:
        return 2, "平均より+%.0fkg%s" % (dd, today)
    return 0, ""


def agari_pt(z):
    """⑤ 上がり ── 補助。大井は上がり幅が1400mで3.2秒・1600mで3.4秒しかなく、
    ルール7の4.0秒に届かない。順位は立つが幅がないので、点は小さくする。
    """
    e = z["edge"]
    if e is None:
        return 0, ""
    if z["xband"]:
        return 0, ""              # 距離帯が違うなら使わない（ルール2）
    if e <= -0.8:
        return 3, "上がり %+.1f秒" % e
    if e <= -0.4:
        return 2, "上がり %+.1f秒" % e
    if e <= 0.0:
        return 1, ""
    if e >= 1.0:
        return -2, "上がり %+.1f秒" % e
    return 0, ""


def sire_pt(ped):
    """⑥ 父が AEI/CPI の上位40位か。人気と位置をそろえても残った唯一の血統指標"""
    if not ped:
        return 0, ""
    f = ped[0]
    for n in AEI40:
        if n in f or f in n:
            return 2, "父%s（AEI上位）" % f
    return 0, ""


def base_pt(z):
    """履歴の厚み。★ルール6 ── 履歴が引けない馬は切らない（呼び元で中央値を入れる）"""
    s, w = 0, []
    ir = z["inrate"]
    if ir >= 0.5:
        s += 3
    elif ir >= 0.33:
        s += 2
    elif ir == 0:
        s -= 2
    if z["frontwin"] >= 2:
        s += 2; w.append("前で粘って3着内が%d回" % z["frontwin"])
    pc = z["pchaku"]
    if pc and 2 <= pc <= 6:
        s += 1
    return s, "・".join(w)


# ────────────────────────── 本体

def run(D, PED, only=None, why=None):
    MED = medians(D)
    for k in sorted(D, key=int):
        R = int(k)
        if only and R not in only:
            continue
        v = D[k]
        d = v["dist"] or 1200
        ped = PED.get(k, {})
        # レース平均の馬体重。当日が入っていればそれ、無ければ前走の体重
        ws = []
        for h in v["horses"]:
            z0 = h["past"][0] if h["past"] else None
            h["_lastw"] = z0.get("w") if z0 else None
            w = h.get("w") or h["_lastw"]
            if w:
                ws.append(w)
        mean_w = round(st.mean(ws)) if len(ws) >= 5 else None

        rows, nohist = [], []
        for h in v["horses"]:
            if R in DROP and h["ub"] in DROP[R]:
                continue
            z = prof(h, d, MED)
            pd = (ped.get(str(h["ub"])) or {}).get("ped")
            if z is None:
                nohist.append((h, pd))
                continue
            s, wy = 0, []
            for f, a in ((pos_pt, (z, d)), (drop_pt, (z,)), (agari_pt, (z,)),
                         (base_pt, (z,))):
                p, t = f(*a); s += p
                if t: wy.append("%s(%+d)" % (t, p))
            p, t = waku_pt(h.get("waku"), d); s += p
            if t: wy.append("%s(%+d)" % (t, p))
            p, t = weight_pt(h, mean_w, d); s += p
            if t: wy.append("%s(%+d)" % (t, p))
            p, t = sire_pt(pd); s += p
            if t: wy.append("%s(%+d)" % (t, p))
            rows.append([h, s, z, wy])

        # ★ ルール6 … 履歴が引けない馬は、その鞍の中央値を与える（切らない）
        mid = round(st.median([r[1] for r in rows])) if rows else 0
        for h, pd in nohist:
            wy = ["履歴なし＝この鞍の中央値(%d)" % mid]
            s = mid
            p, t = sire_pt(pd); s += p
            if t: wy.append("%s(%+d)" % (t, p))
            rows.append([h, s, None, wy])

        rows.sort(key=lambda r: -r[1])
        # FORCE で指名された馬を上へ
        if R in FORCE:
            for rank, ub in sorted(FORCE[R].items()):
                i = next((j for j, r in enumerate(rows) if r[0]["ub"] == ub), None)
                if i is not None:
                    rows.insert(rank - 1, rows.pop(i))

        print("\n%2dR %4dm %s %s %2d頭" % (
            R, d, v.get("start", ""), (v.get("cls") or "")[:18], len(v["horses"])))
        for i, (h, s, z, wy) in enumerate(rows[:5]):
            print("  %s %2d %-14s %3d点  %s" % (
                MK[i], h["ub"], h["name"][:14], s,
                "・".join(x for x in wy if x)[:92] if (why == R or why == 0) else
                (wy[0] if wy else "")))
        ana = pick_ana(rows, R, d)
        if ana:
            h, s, z, wy = ana
            print("  穴 %2d %-14s %3d点  %s" % (h["ub"], h["name"][:14], s, "・".join(x for x in wy if x)[:80]))
        if why == R:
            print("  ── 6位以下")
            for h, s, z, wy in rows[5:]:
                print("     %2d %-14s %3d点  %s" % (h["ub"], h["name"][:14], s,
                      "・".join(x for x in wy if x)[:92]))


def pick_ana(rows, R, d):
    """穴 ── 印を打った5頭より下から。

    CLAUDE.md「穴の欄」の①②のうち、大井で生き残るのは②だけ。
    ①（後ろから押し上げて差す形）は前開催で0勝〜4.4%しかなかった。
    該当なしの鞍は空ける。無理にひねり出さない。
    """
    if R in FORCE_ANA:
        return next((r for r in rows if r[0]["ub"] == FORCE_ANA[R]), None)
    for h, s, z, wy in rows[5:]:
        if z is None:
            continue
        # 前で粘れる型で、前走を負けていて人気が落ちる形
        if z["prel"] is not None and z["prel"] < 0.35 and (z["drop"] or 0) < 0.35 \
           and z["pchaku"] and z["pchaku"] >= 4:
            return [h, s, z, wy + ["前め型・前走%d着で人気が落ちる" % z["pchaku"]]]
    return None


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    D = json.load(open(a[0]))
    PED = json.load(open(a[1])) if len(a) > 1 and a[1].endswith(".json") else {}
    why = None
    if "--why" in a:
        why = int(a[a.index("--why") + 1])
        a = a[:a.index("--why")] + a[a.index("--why") + 2:]
    only = [int(x) for x in a[1:] if x.isdigit()]
    run(D, PED, only or None, why)


if __name__ == "__main__":
    main()
