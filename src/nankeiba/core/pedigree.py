"""血統ビーム 大系統カラーリング（亀谷敬正）を南関データで再現。

全種牡馬を11大系統に分類・色分け(ネイティヴダンサー系とミスプロ系は同色＝実質10色)。
馬券で使うだけなら **5大系統**(ノーザンダンサー/サンデー/ミスプロ/ターントゥ/ナスルーラ)
を見れば足りる。

使い方(誌面の思想):
  - 馬場読み: **父or母父サンデー系が走っているか**が鍵。走っている=主流馬場、
    そうでなければ非主流馬場の可能性。
  - ダート: サンデー系(特に芝寄り)がまとめて来る=“特殊(軽い)ダート”。通常のダートは
    パワー系(ミスプロ/ターントゥ・ロベルト/ナスルーラ)が主流。南関の主流はパワー系。
  - バイアスと逆の系統の人気馬なら、バイアス側の人気薄が高配当の妙味。

種牡馬→大系統の対応は誌面リスト＋一般的血統知識から作成(主要種牡馬中心・拡張可)。
未知の種牡馬は None(不明)。依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass

# 11大系統。key, 和名, 表示色(ネイティヴ=ミスプロは同色), 5大系統フラグ
SYSTEMS: dict[str, tuple[str, str, bool]] = {
    "northern":     ("ノーザンダンサー系", "#1a63c4", True),
    "sunday":       ("サンデー系",         "#7ac043", True),
    "mrprospector": ("ミスプロ系",         "#f0a24a", True),
    "native":       ("ネイティヴダンサー系", "#f0a24a", False),   # ミスプロと同色
    "turnto":       ("ターントゥ系",       "#3aa03a", True),
    "nasrullah":    ("ナスルーラ系",       "#e5007f", True),
    "hampton":      ("ハンプトン系",       "#9b6bd1", False),
    "stsimon":      ("セントサイモン系",   "#7a2fa0", False),
    "minor":        ("マイナー系",         "#9e9e9e", False),
    "herod":        ("ヘロド系",           "#7a5230", False),
    "matchem":      ("マッチェム系",       "#f08a24", False),
}
KEY5 = [k for k, v in SYSTEMS.items() if v[2]]


# 種牡馬名 → 大系統key（主要種牡馬・南関/JRA混在）
_SIRES: dict[str, list[str]] = {
    "sunday": [
        # ディープ系
        "ディープインパクト", "コントレイル", "キズナ", "サトノダイヤモンド", "サトノアラジン",
        "リアルスティール", "リアルインパクト", "ミッキーアイル", "ミッキーグローリー",
        "フィエールマン", "エイシンヒカリ", "アルアイン", "ヴァンセンヌ", "グレーターロンドン",
        "シルバーステート", "スピルバーグ", "ダノンキングリー", "ダノンバラード", "ダノンプレミアム",
        "ディープブリランテ", "トーセンホマレボシ", "トーセンラー", "ロジャーバローズ", "アイアンバローズ",
        # Pサンデー
        "ダイワメジャー", "フジキセキ", "キンシャサノキセキ", "ジャスタウェイ", "イスラボニータ",
        "インディチャンプ", "アドマイヤマーズ", "アドマイヤマックス", "カレンブラックヒル",
        "ダノンシャンティ", "デュランダル", "マツリダゴッホ", "アグネスタキオン", "オルフェーヴル",
        # Tサンデー
        "ステイゴールド", "ハーツクライ", "キタサンブラック", "ゴールドシップ", "スワーヴリチャード",
        "スペシャルウィーク", "ヴィクトワールピサ", "ゼンノロブロイ", "ダンスインザダーク",
        "マンハッタンカフェ", "シュヴァルグラン", "アドマイヤベガ",
        # Dサンデー(ダート・南関核)
        "ゴールドアリュール", "ゴールドドリーム", "コパノリッキー", "エスポワールシチー",
        "スマートファルコン", "クリソベリル", "ゴールドヘイロー", "スズカマンボ", "ネオユニヴァース",
        "エピカリス", "スパイキュール", "サウンドトゥルー",
        # Lサンデー
        "ブラックタイド", "ブルドッグボス", "ディープスカイ", "フェノーメノ", "ドリームジャーニー",
        "サムライハート", "ジョーカプチーノ", "スマートオーディン", "トーホウジャッカル",
        "リーチザクラウン", "レインボーライン", "ワンアンドオンリー", "メジロベイリー",
        "マーベラスサンデー", "サクラプレジデント", "ウインブライト", "エポカドーロ", "ガルボ",
    ],
    "mrprospector": [
        # フォーティナイナー系(短ダの宝庫)
        "サウスヴィグラス", "アドマイヤムーン", "エンドスウィープ", "スウェプトオーヴァーボード",
        "ハクサンムーン", "パドトロワ", "ファインニードル", "アイルハヴアナザー", "コロナドズクエスト",
        # キングマンボ系
        "キングカメハメハ", "ロードカナロア", "ルーラーシップ", "ドゥラメンテ", "ホッコータルマエ",
        "サートゥルナーリア", "リオンディーズ", "レイデオロ", "ヤマカツエース", "ラブリーデイ",
        "トゥザワールド", "トゥザグローリー", "ミッキーロケット", "ダノンスマッシュ", "ベルシャザール",
        # その他ミスプロ
        "マテラスカイ", "アグネスデジタル", "エンパイアメーカー", "ストリートセンス", "タワーオブロンドン",
        "キセキ", "エイシンフラッシュ", "アフリート", "シニスターミニスター",  # 誌面ではAPインディだが実務上ミスプロ寄せ回避→下でnasrullahに置く
    ],
    "nasrullah": [
        # エーピーインディ系(南関ダート主力)
        "シニスターミニスター", "パイロ", "カリフォルニアクローム", "カジノドライヴ",
        "マジェスティックウォリアー", "ラニ", "ベストウォーリア", "サンダースノー",
        # レッドゴッド/その他
        "バゴ", "アニマルキングダム",
        # プリンスリーギフト/グレイソヴリン
        "サクラバクシンオー", "ショウナンカンプ", "ビッグアーサー", "アドマイヤコジーン",
        "ジャングルポケット", "トーセンジョーダン", "チチカステナンゴ",
    ],
    "turnto": [
        # ロベルト系(パワー・南関)
        "フリオーソ", "ルヴァンスレーヴ", "シンボリクリスエス", "エピファネイア", "グラスワンダー",
        "スクリーンヒーロー", "モーリス", "ブライアンズタイム", "マヤノトップガン", "ゴールドアクター",
        "ストロングリターン", "タニノギムレット", "ナダル",
        # ヘイロー系
        "メイショウボーラー", "タイキシャトル", "ロージズインメイ",
    ],
    "northern": [
        # ストームキャット/ヴァイスリージェント(ダート・パワー)
        "クロフネ", "ヘニーヒューズ", "ドレフォン", "フレンチデピュティ", "モーニン",
        "アジアエクスプレス", "アイルハヴアナザー",  # (念のため)
        "ハービンジャー", "ディーマジェスティ", "エイシンヒカリ",  # 一部は別系だが主要のみ
        "キングヘイロー", "ダノンレジェンド",  # ※ダノンレジェンドはminorに置くため下で上書きしない
    ],
    "minor": [
        "トランセンド", "ダノンレジェンド", "ワイルドラッシュ", "キャプテンスティーヴ", "ノヴェリスト",
        "インカンテーション",
    ],
    "herod": ["トウカイテイオー", "メジロマックイーン", "シンボリルドルフ", "ギンザグリングラス"],
    "matchem": ["カルストンライトオ"],
    "hampton": ["サッカーボーイ", "ナリタトップロード"],
    "stsimon": ["タップダンスシチー"],
    "native": ["カコイーシーズ"],
}

# 逆引き（後勝ち＝最後に定義した系統を優先。曖昧なものは意図した系統を最後に置く）
SIRE_TO_SYSTEM: dict[str, str] = {}
for _sys, _names in _SIRES.items():
    for _n in _names:
        SIRE_TO_SYSTEM[_n] = _sys
# 追加の主要種牡馬（南関頻出・基礎父系）
SIRE_TO_SYSTEM.update({
    # サンデー系(基礎)
    "サンデーサイレンス": "sunday", "アグネスデジタル": "mrprospector",
    "ヴァーミリアン": "mrprospector", "トランセンド": "minor",
    # ノーザンダンサー系(ダート・パワー)
    "アメリカンペイトリオット": "northern", "マインドユアビスケッツ": "northern",
    "ワンダーアキュート": "northern", "カリズマティック": "northern",
    "スウィフトカレント": "sunday", "パイロ": "nasrullah", "キンググローリアス": "mrprospector",
    "サブノジュニア": "northern", "ダノンレジェンド": "minor",
    # ミスプロ系(基礎)
    "ミスタープロスペクター": "mrprospector", "フォーティナイナー": "mrprospector",
    "GoneWest": "mrprospector", "SmartStrike": "mrprospector", "Curlin": "mrprospector",
    "タイムパラドックス": "mrprospector", "アドマイヤムーン": "mrprospector",
    # マッチェム系
    "Tiznow": "matchem", "ティズナウ": "matchem", "カルストンライトオ": "matchem",
    # 誌面準拠の上書き
    "シニスターミニスター": "nasrullah",
})


def _normalize(name: str | None) -> str:
    s = (name or "")
    # 全角英数字→半角
    s = s.translate({c: c - 0xFEE0 for c in range(0xFF01, 0xFF5F)})
    return s.replace("　", "").replace(" ", "").replace("・", "").strip()


def classify(sire: str | None) -> str | None:
    """種牡馬名から大系統keyを返す。未知は None。"""
    n = _normalize(sire)
    if not n:
        return None
    if n in SIRE_TO_SYSTEM:
        return SIRE_TO_SYSTEM[n]
    # 部分一致（表記ゆれ対策）
    for name, sys in SIRE_TO_SYSTEM.items():
        if name in n or n in name:
            return sys
    return None


def system_name(key: str | None) -> str:
    return SYSTEMS[key][0] if key in SYSTEMS else "不明"


def system_color(key: str | None) -> str:
    return SYSTEMS[key][1] if key in SYSTEMS else "#bbbbbb"


def short_name(key: str | None) -> str:
    """短い記号（新聞用）。"""
    return {"northern": "NД", "sunday": "サ", "mrprospector": "ミ", "native": "ネ",
            "turnto": "タ", "nasrullah": "ナ", "hampton": "ハ", "stsimon": "St",
            "minor": "他", "herod": "ヘ", "matchem": "マ"}.get(key or "", "―")


@dataclass
class PedTag:
    umaban: int
    sire_sys: str | None       # 父の大系統
    bms_sys: str | None        # 母父の大系統

    @property
    def is_sunday_line(self) -> bool:
        """父or母父がサンデー系（馬場読みの鍵）。"""
        return self.sire_sys == "sunday" or self.bms_sys == "sunday"


def tag_entries(entries) -> dict[int, PedTag]:
    """entries: [(umaban, sire, bms), ...] → {umaban: PedTag}。"""
    out: dict[int, PedTag] = {}
    for um, sire, bms in entries:
        out[um] = PedTag(umaban=um, sire_sys=classify(sire), bms_sys=classify(bms))
    return out


@dataclass
class PedBias:
    counts: dict[str, int]         # 大系統key -> 頭数(父ベース)
    sunday_line: int               # 父or母父サンデー系の頭数
    total: int

    def top_systems(self, n: int = 3) -> list[tuple[str, int]]:
        return sorted(self.counts.items(), key=lambda t: -t[1])[:n]

    def track_read(self, surface: str = "ダ") -> str:
        """サンデー系の比率から馬場読みの一言。"""
        if not self.total:
            return "血統データ不足"
        s_rate = self.sunday_line / self.total
        if surface == "芝":
            return ("父母父サンデー系が多い→主流馬場想定" if s_rate >= 0.5
                    else "サンデー系少→非主流(パワー)馬場の可能性")
        # ダート: サンデー系がまとめて来る=特殊(軽い)ダート
        if s_rate >= 0.5:
            return "サンデー系多→“特殊(軽い)ダート”寄りに注意"
        return "パワー系(ミスプロ/ターントゥ/ナスルーラ)主流の通常ダート想定"


def bias_of(tags: dict[int, PedTag]) -> PedBias:
    counts: dict[str, int] = {}
    sunday_line = 0
    for t in tags.values():
        if t.sire_sys:
            counts[t.sire_sys] = counts.get(t.sire_sys, 0) + 1
        if t.is_sunday_line:
            sunday_line += 1
    return PedBias(counts=counts, sunday_line=sunday_line, total=len(tags))
