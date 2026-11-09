"""競馬ブックの血統表から、指定した血が3代以内に入っている馬を探す（kb.conf のcookieが要る）。

  python3 kettou.py 2026101305 1023 アンブライドルズソング
  python3 kettou.py 2026101305 1023 ダンカーク ドレフォン      # 複数指定はOR
  python3 kettou.py 2026101305 1023 --list 5                  # 5Rの全頭の血統を出す

血統表ページ（/chihou/kettou/<rid>）は1頭につき **3代ぶん＝14頭**の名前が
この順で並ぶ。位置が分かるので「母父」なのか「母母父」なのかまで出せる。

  父 / 父父 / 父父父 / 父父母 / 父母 / 父母父 / 父母母
  母 / 母父 / 母父父 / 母父母 / 母母 / 母母父 / 母母母

2+4+8=14 なので3代。**4代目が ***** でマスクされている**。
したがって 3×4 の「奇跡の血量」(18.75%) はこのページからは見えない。
5代までほしいときは netkeiba の /horse/ped/<ID>/ が使える（EUC-JP）。

注意: 馬ごとの区切りは「馬番 馬名 (性齢)」で取る。騸馬は「(セン3)」と書かれる。
ここを落とすと、その馬の血統が前の馬にくっついて **別の馬の血を誤って拾う**。
10/23 浦和3Rの④キャッスルギフト（セン3）で実際にそうなった。
取れた名前が15個以上になったら区切りに失敗しているので捨てる。
"""
import re, sys, time, subprocess, os

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "kb.conf")
URL = "https://p.keibabook.co.jp/chihou/kettou/"      # 後方互換のため残す
BASE = "https://p.keibabook.co.jp/%s/kettou/"
POS = ["父", "父父", "父父父", "父父母", "父母", "父母父", "父母母",
       "母", "母父", "母父父", "母父母", "母母", "母母父", "母母母"]

# 父系の判定。父・父父・父父父 のどれかに出てきたら、その系統とする。
# 上から順に見て最初に当たったものを採る。
LINE = [
    ("ストームキャット系", ["ストームキャット", "ヘネシー", "ヘニーヒューズ", "ジャイアンツコーズウェイ",
                            "ヨハネスブルグ", "スキャットダディ", "ハーラン", "テイルオブザキャット",
                            "ジオポンティ", "ドレフォン", "カンタロス", "ライオンハート"]),
    ("エーピーインディ系", ["エーピーインディ", "オールドトリエステ", "シニスターミニスター", "パイロ",
                            "マジェスティックウォリアー", "タピット", "シアトルスルー", "プルピット",
                            "マインドユアビスケッツ", "ベルシャザール"]),
    ("ミスプロ系（ダート）", ["フォーティナイナー", "アフリート", "エンドスウィープ",
                              "スウェプトオーヴァーボード", "サウスヴィグラス", "ゴーンウエスト",
                              "クロフネ", "フレンチデピュティ", "カジノドライヴ", "スペイツタウン",
                              "ポセイドンズウォリアー", "イルーシヴクオリティ", "レイヴンズパス",
                              "ドバウィ", "ドバイミレニアム", "ウォーエンブレム", "シーキングザゴールド"]),
    ("キングマンボ系", ["キングマンボ", "キングカメハメハ", "レモンドロップキッド",
                        "エルコンドルパサー", "ルーラーシップ"]),
    ("ミスプロ系（その他）", ["ミスタープロスペクター", "マキアヴェリアン", "マキャヴェリアン", "ウッドマン"]),
    ("サンデー系", ["サンデーサイレンス", "ディープインパクト", "ハーツクライ", "ステイゴールド",
                    "ゴールドアリュール", "アグネスタキオン", "フジキセキ", "ネオユニヴァース",
                    "マンハッタンカフェ", "ダイワメジャー", "キンシャサノキセキ", "オルフェーヴル",
                    "ゴールドシップ", "ジャスタウェイ", "ドゥラメンテ", "ハーツ", "スペシャルウィーク",
                    "ヘイロー"]),
    ("ロベルト系", ["ロベルト", "ブライアンズタイム", "シンボリクリスエス", "エピファネイア",
                    "グラスワンダー", "スクリーンヒーロー", "モーリス"]),
    ("ノーザンダンサー系", ["ダンジグ", "サドラーズウェルズ", "ニジンスキー", "ヌレイエフ",
                            "グリーンデザート", "ケープクロス", "ノーザンテースト", "ダンシングブレーヴ",
                            "ホワイトマズル", "リファール", "ダンチヒ", "ウォーフロント", "デインヒル",
                            "エクシードアンドエクセル", "ガリレオ", "フランケル", "ラストタイクーン",
                            "マルジュ", "ヘルメット"]),
    ("その他の米ダート", ["ホーリーブル", "マッチョウノ", "アンブライドルド", "アンブライドルズソング",
                          "ファピアノ", "ダンカーク", "メダグリアドーロ", "エルプラド", "タリスマニック",
                          "ワイルドラッシュ", "ブロードブラッシュ"]),
    ("ブラッシンググルーム系", ["ブラッシンググルーム", "ナシュワン", "キャンディストライプス",
                                "ルロワドサニモー"]),
]


def sire_line(ped):
    """父系を返す。父・父父・父父父 だけを見る"""
    for name, keys in LINE:
        for a in ped[:3]:
            if any(k in a for k in keys):
                return name
    return "不明"


def haha_ss(ped):
    """母系（母父・母父父・母母父）のサンデーサイレンスの位置。無ければ None"""
    for i in (8, 9, 12):
        if len(ped) > i and "サンデーサイレンス" in ped[i]:
            return POS[i]
    return None
SEI = "牡|牝|セン|セ|騸"
KOKU = "USA|IRE|GB|FR|CAN|AUS|NZ|GER|ARG|BRZ|ITY|JPN|SAF|CHI|URU|TUR"


def get(rid):
    """rid の桁数で中央／地方を分ける。地方=16桁、中央=12桁（kb.area() と同じ考え）"""
    url = BASE % ("cyuou" if len(rid) == 12 else "chihou") + rid
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-K", CONF, url],
                       capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def parse(h):
    """{馬番: {'name':…, 'sei':…, 'ped':[14頭ぶんの祖先名]}}"""
    t = re.sub(r"<[^>]+>", " ", h).replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t)
    # ★見出しは地方が「血統表 全馬を表示」、中央は「全馬を表示」だけ。
    #   地方の文言で決め打ちしていたため、中央は静かに0件を返していた。
    i = t.find("全馬を表示")
    if i < 0:
        return {}
    t = t[i:]
    head = re.compile(r"([0-9０-９]{1,2})\s+([ァ-ヶー]{2,})\s*\((%s)(\d+)\)" % SEI)
    hs = [(m.start(), m.group(1), m.group(2), m.group(3) + m.group(4))
          for m in head.finditer(t)]
    # 同じ並びが2回出るページなので、最初のひとまわりだけ使う
    seen, uniq = set(), []
    for x in hs:
        if x[1] in seen:
            break
        seen.add(x[1]); uniq.append(x)
    anc = re.compile(r"([ァ-ヶー][ァ-ヶー・ ]{1,22}?)(?:%s)?\s+"
                     r"[A-Za-z][A-Za-z'\. ]{2,30}\s+"
                     r"(?:黒鹿毛|鹿毛|栗毛|芦毛|青鹿毛|青毛|白毛|黒毛|栃栗毛)" % KOKU)
    out = {}
    for k, (p, ub, nm, sei) in enumerate(uniq):
        seg = t[p:uniq[k + 1][0] if k + 1 < len(uniq) else len(t)]
        names = [re.sub(r"\s+", "", x) for x in anc.findall(seg)]
        if len(names) > 14:          # 区切りに失敗している。隣の馬が混ざった
            names = names[:14]
        ub = int(ub.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
        out[ub] = {"name": nm, "sei": sei, "ped": names}
    return out


def where(ped, tg):
    return [POS[i] if i < len(POS) else "?"
            for i, a in enumerate(ped) if tg in a]


def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    base, mmdd = sys.argv[1], sys.argv[2]
    rest = sys.argv[3:]
    if "--list" in rest:
        R = int(rest[rest.index("--list") + 1])
        for ub, z in sorted(parse(get("%s%02d%s" % (base, R, mmdd))).items()):
            print("%2d %-14s %s" % (ub, z["name"], z["sei"]))
            for i, a in enumerate(z["ped"]):
                print("     %-5s %s" % (POS[i] if i < len(POS) else "?", a))
        return
    tgs = [x for x in rest if not x.startswith("-")]
    if not tgs:
        print(__doc__); return
    tot, hit = 0, []
    for R in range(1, 13):
        d = parse(get("%s%02d%s" % (base, R, mmdd)))
        tot += len(d)
        for ub, z in sorted(d.items()):
            for tg in tgs:
                w = where(z["ped"], tg)
                if w:
                    hit.append((R, ub, z["name"], tg, w, z["ped"]))
                    break
        time.sleep(0.4)
    print("調べた頭数 %d" % tot)
    print("「%s」が3代以内にいる馬 … %d頭\n" % ("／".join(tgs), len(hit)))
    for R, ub, nm, tg, w, ped in hit:
        print("  %2dR %2d %-14s  %s（%s）" % (R, ub, nm, tg, "・".join(w)))
        print("       父 %s ／ 母 %s ／ 母父 %s" % (
            ped[0] if len(ped) > 0 else "?",
            ped[7] if len(ped) > 7 else "?",
            ped[8] if len(ped) > 8 else "?"))


if __name__ == "__main__":
    main()
