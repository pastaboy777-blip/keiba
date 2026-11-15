"""種牡馬 → 父系の系統（手で分類した表）。

    from sire_line import line_of
    line_of("エピファネイア")  # → "ロベルト"

系統は6つ ＋ 不明:
    ロベルト / 欧州 / 米国 / サンデー / キンカメ / その他 / ?(表にない)

分け方の考え方（出典は一般に知られている父系図。netkeiba・JBIS の「父系」表記と同じ筋で、手で当てた）:
  1. 父系を Roberto・Sunday Silence・Kingmambo までさかのぼれる馬を、地域より先に抜き出す。
     - ロベルト  … Roberto の子孫。Kris S(シンボリクリスエス→エピファネイア→エフフォーリア、ルヴァンスレーヴ、
                   ストロングリターン、Arch→Blame)、Silver Hawk(グラスワンダー→スクリーンヒーロー→モーリス、
                   ゴールドアクター)、ブライアンズタイム(タニノギムレット、マヤノトップガン、タイムパラドックス)、
                   Red Ransom(Intikhab)、Dynaformer。
     - サンデー  … Sunday Silence の子孫（ディープ、ハーツクライ、ステイゴールド、キズナ、キタサンブラック 等）。
     - キンカメ  … Kingmambo の子孫（キングカメハメハ、ロードカナロア、ルーラーシップ、ドゥラメンテ、
                   エルコンドルパサー、King's Best、Lemon Drop Kid 系も含める）。
  2. 残りは、その父系が主に発展した地域で分ける。
     - 欧州  … Sadler's Wells/Galileo/Frankel/Montjeu、Danehill/Dansili/Kingman、Nureyev、Lyphard
               (キングヘイロー)、Monsun(ノヴェリスト)、Marju(サトノクラウン)、Dubawi/Shamardal/Sea The Stars、
               Green Desert/Invincible Spirit、Grey Sovereign系(トニービン→ジャングルポケット、Caro系の欧州馬)、
               ハービンジャー、バゴ 等。Dubawi・Shamardal は Mr.Prospector・Storm Cat の血だが欧州で育った系統なので欧州。
     - 米国  … Mr.Prospector の米国系(Forty Niner、Gone West、Fappiano、Distorted Humor、Smart Strike)、
               Storm Cat(ヨハネスブルグ、Scat Daddy、Giant's Causeway の米国側)、A.P. Indy(Tapit 等)、
               Danzig の米国側(War Front、Hard Spun)、Deputy Minister(クロフネ)、Halo の非サンデー(タイキシャトル)、
               El Prado(Medaglia d'Oro、Kitten's Joy)、Unbridled's Song 等。
     - その他 … サクラバクシンオー(Princely Gift)、豪州の Sir Tristram 系 など、上のどれにも入れにくいもの。
  3. 迷ったものは、その種牡馬が主に供用された国で決めた（例: Caravaggio は Scat Daddy 系なので米国）。
  表にない種牡馬は "?"。件数は jra_blood_baba.py が数えて出す。
"""
from __future__ import annotations

R, E, A, S, K, O = "ロベルト", "欧州", "米国", "サンデー", "キンカメ", "その他"
LINES = [R, E, A, S, K, O]

_T: dict[str, str] = {}


def _add(line: str, names: str) -> None:
    for n in names.split("/"):
        n = n.strip()
        if n:
            _T[n] = line


_add(R, """エピファネイア/エフフォーリア/モーリス/スクリーンヒーロー/シンボリクリスエス/ブライアンズタイム/
グラスワンダー/タニノギムレット/マヤノトップガン/タイムパラドックス/ゴールドアクター/ルヴァンスレーヴ/
ストロングリターン/Blame/Dynaformer/Red Ransom/Intikhab/Symboli Kris S/Tanino Gimlet/Maurice/Kris S/
Arch/Silver Hawk/Brian's Time/Lear Fan/Roberto/Epiphaneia""")

_add(S, """ディープインパクト/コントレイル/キズナ/シルバーステート/ハーツクライ/ダイワメジャー/キタサンブラック/
ゴールドシップ/オルフェーヴル/ステイゴールド/ダノンバラード/リアルスティール/ウインブライト/マンハッタンカフェ/
サトノダイヤモンド/アドマイヤマーズ/イスラボニータ/ミッキーアイル/フィエールマン/アルアイン/スワーヴリチャード/
ダノンプレミアム/ヴィクトワールピサ/インディチャンプ/ゼンノロブロイ/ブラックタイド/キンシャサノキセキ/ジャスタウェイ/
アグネスタキオン/ネオユニヴァース/ダノンキングリー/スペシャルウィーク/グレーターロンドン/ダンスインザダーク/
ディープブリランテ/ロジャーバローズ/フジキセキ/マツリダゴッホ/ゴールドアリュール/ディーマジェスティ/シュヴァルグラン/
サリオス/サトノアラジン/ワールドプレミア/カレンブラックヒル/ダノンシャンティ/ヘンリーバローズ/トーセンホマレボシ/
ジョーカプチーノ/リアルインパクト/トーセンラー/リーチザクラウン/エポカドーロ/サトノジェネシス/アドマイヤマックス/
スズカマンボ/ドリームジャーニー/サングレーザー/アレスバローズ/ゴールドドリーム/ミッキーグローリー/エイシンヒカリ/
リンカーン/レッドベルジュール/ヴァンセンヌ/サクラプレジデント/ディープスカイ/ロジユニヴァース/スピルバーグ/
クリソベリル/マーベラスサンデー/ガルボ/トーセンレーヴ/スマートファルコン/サンデーサイレンス/Saxon Warrior/
デュランダル/Victoire Pisa/フェノーメノ/オレハマッテルゼ/アドミラブル/ナカヤマフェスタ/アルバート/ゴールドヘイロー/
ワールドエース/グローリーヴェイズ/エスポワールシチー/Deep Impact/Daiwa Major/マカヒキ/Heart's Cry/アドマイヤジャパン/
スマートオーディン/サトノインプレッサ/コパノリッキー/アドマイヤベガ/ヤマニンセラフィム/ウインバリアシオン/
マルカシェンク/アンライバルド/ショウナンバッハ/カネヒキリ/スウィフトカレント/Study of Man/サムライハート/
ミッキースワロー/カデナ/Sunday Silence/エピカリス/Silver State/Zenno Rob Roy/Mikki Isle/ステイフーリッシュ/
ジェンティルドンナ/ダノンザキッド/シャフリヤール/ドゥレッツァ/ジオグリフ/ポタジェ/プログノーシス/エタリオウ/
ワンアンドオンリー/トーセンファントム/リキアイサイレンス/ザサンデーフサイチ/バブルガムフェロー/タヤスツヨシ/
エイシンサンディ/トウカイテイオー/ハッピースプリント/アッミラーレ""")

_add(K, """キングカメハメハ/ロードカナロア/サートゥルナーリア/レイデオロ/ルーラーシップ/リオンディーズ/ダノンスマッシュ/
エイシンフラッシュ/キセキ/ワークフォース/ビーチパトロール/ドゥラメンテ/ラブリーデイ/キングズベスト/リオンリオン/
ステルヴィオ/ミッキーロケット/トゥザワールド/ヤマカツエース/Kingmambo/ルールオブロー/ソングオブウインド/
Henrythenavigator/チュウワウィザード/Thewayyouare/ヴァーミリアン/トゥザグローリー/ベルシャザール/ホッコータルマエ/
Lemon Drop Kid/エルコンドルパサー/Lord Kanaloa/King's Best/タイセイレジェンド/ロードアルティマ/アポロキングダム/
キングオブコージ/ホウオウイクセル/タイトルホルダー/ドウデュース/アルカセット""")

_add(E, """ハービンジャー/ベンバトル/サトノクラウン/Galileo/Frankel/ポエティックフレア/ジャングルポケット/バゴ/ノヴェリスト/
Dubawi/キングヘイロー/Kingman/ノーブルミッション/Invincible Spirit/サンダースノー/Shamardal/Dark Angel/タートルボウル/
マクフィ/Siyouni/ローエングリン/ホワイトマズル/チチカステナンゴ/Teofilo/ファルブラヴ/ロゴタイプ/St Mark's Basilica/
Lope de Vega/コンデュイット/Sea The Stars/Cape Cross/Danehill Dancer/タニノフランケル/Wootton Bassett/ストーミングホーム/
ハイランドリール/Singspiel/Le Havre/Australia/Iffraaj/オペラハウス/ベーカバド/メイショウサムソン/Rock of Gibraltar/
Kodiac/Too Darn Hot/ケープブランコ/Oasis Dream/High Chaparral/New Approach/Exceed And Excel/Royal Applause/Medicean/
Sottsass/ローレルゲレイロ/Orpen/スニッツェル/ファスリエフ/Holy Roman Emperor/Acclamation/Monsun/Blue Point/
Mastercraftsman/Azamour/Lord of England/Palace Pier/Montjeu/Makfi/Pivotal/Dansili/Kendargent/Lizard Island/Dawn Approach/
Sinndar/Zoffany/Sir Prancealot/Dream Ahead/Redoute's Choice/Fastnet Rock/Anabaa/Duke of Marmalade/Champs Elysees/
モンテロッソ/Footstepsinthesand/Myboycharlie/カンパニー/Nathaniel/Unusual Heat/Nayef/Manduro/トーセンジョーダン/
ナリタトップロード/ロックオブジブラルタル/Spirit One/Oratorio/Canford Cliffs/Sadler's Wells/Bated Breath/Camelot/
スーパーホーネット/Alhaarth/テレグノシス/Marju/Zoustar/Winker Watson/Catcher In The Rye/Dabirsim/Daylami/Soldier Hollow/
Aussie Rules/ブラックホーク/The Wow Signal/フサイチコンコルド/Earthlight/Hinchinbrook/Poet's Voice/マリエンバード/
オウケンブルースリ/Awtaad/Baaeed/Night of Thunder/Grand Lodge/Compton Place/Dutch Art/Dalakhani/Sligo Bay/Jeremy/
Exceedance/Trapeze Artist/Hallowed Crown/Starspangledbanner/Not A Single Doubt/ファンタスティックライト/Arcano/Generous/
Lucky Vega/サツカーボーイ/Magician/So You Think/Gleneagles/Harbinger/Motivator/Mount Nelson/Lomitas/Rainbow Quest/
Shirocco/Darshaan/Pour Moi/Ghaiyyath/Masar/Cracksman/Danehill/Noble Mission/Benbatl/Machiavellian/
Green Desert/Kyllachy/Dashing Blade/Acatenango/Langfuhr/Pride Of Dubai/Sholokhov/Equiano/Showcasing/Mehmas/Gutaifan/
Dandy Man/Ocean Park/Almanzor/Belardo/Roderic O'Connor/Dragon Pulse/Zamindar/Diktat/Sakhee/Rossini/Rip Van Winkle/
Treasure Beach/Highland Reel/Cape Blanco/Kodi Bear/Olympic Glory/War Command/Muhaarar/Mukhadram/Elzaam/Tamayuz/
Dylan Thomas/Barathea/Highest Honor/Anabaa Blue/Kingsalsa/Shamardal/Pinatubo/モズアスコット/Harry Angel/Minardi/Lawman/Platini/Noverre/Girolamo/
Charm Spirit/Collected/Tobougg/Dushyantor/Elusive City/Encosta De Lago/Rail Link/Ruler of The World/Born To Sea/
ストラヴィンスキー/アラムシャー/ロックオブジブラルタル/スズカコーズウェイ/デザートキング/コマンダーインチーフ/
Mark of Esteem/Swiss Spirit/Mendelssohn/Magna Grecia/The Gurkha/Beat Hollow/Vespone/Paynter/ウォーニング/
ロドリゴデトリアーノ""")

_add(A, """クロフネ/ブリックスアンドモルタル/タワーオブロンドン/シスキン/ドレフォン/アドマイヤムーン/タイキシャトル/
ミスターメロディ/フレンチデピュティ/エンパイアメーカー/デクラレーションオブウォー/ロージズインメイ/ファインニードル/
マインドユアビスケッツ/アグネスデジタル/アメリカンペイトリオット/スウェプトオーヴァーボード/パイロ/フィレンツェファイア/
フォーウィールドライブ/タリスマニック/ヨハネスブルグ/ヘニーヒューズ/Tapit/ミスチヴィアスアレックス/マテラスカイ/
War Front/カリフォルニアクローム/Medaglia d'Oro/ウォーエンブレム/Into Mischief/ヴァンゴッホ/Storm Cat/シャンハイボビー/
American Pharoah/アイルハヴアナザー/Kitten's Joy/ニューイヤーズデイ/ジャンダルム/Giant's Causeway/サウスヴィグラス/
セイウンコウセイ/アドマイヤコジーン/ケイムホーム/シニスターミニスター/Pioneerof the Nile/アジアエクスプレス/Malibu Moon/
Unbridled's Song/ホークビル/アニマルキングダム/ネロ/Ghostzapper/Scat Daddy/Candy Ride/マジェスティックウォリアー/
Distorted Humor/Speightstown/Bernardini/メイショウボーラー/ディスクリートキャット/Bernstein/Smart Strike/Congrats/
レッドファルクス/マイネルラヴ/ダンカーク/カラヴァッジオ/パドトロワ/Twirling Candy/Uncle Mo/トビーズコーナー/Tiznow/
バトルプラン/ワイルドラッシュ/Caravaggio/Street Cry/Bluegrass Cat/Mizzen Mast/アフリート/Harlan's Holiday/
ホットロッドチャーリー/Curlin/ナダル/More Than Ready/Street Boss/City Zip/Empire Maker/No Nay Never/English Channel/
Mr. Greeley/モーニン/Frosted/Pulpit/ストリートセンス/アルデバラン2/Discreet Cat/Hard Spun/スクワートルスクワート/
Charlatan/カジノドライヴ/Fortify/Elusive Quality/Quality Road/A.P. Indy/スタチューオブリバティ/ダノンレジェンド/
El Corredor/Gone West/Munnings/コマンズ/Bodemeister/Street Sense/Mineshaft/Gun Runner/Liam's Map/Wilburn/Shanghai Bobby/
エスケンデレヤ/Stormy Atlantic/パラダイスクリーク/ティンバーカントリー/Tale of Ekati/Raven's Pass/Animal Kingdom/
Tiz Wonderful/Violence/ベストウォーリア/スターリングローズ/Bellamy Road/ハードスパン/プリサイスエンド/High Yield/
Shackleford/Union Rags/Successful Appeal/Declaration of War/Include/レッドスパーダ/フォーティナイナー/First Samurai/
Complexity/ウィルテイクチャージ/ハクサンムーン/トランセンド/スターオブコジーン/Awesome Again/コロナドズクエスト/
ヘクタープロテクター/サマーバード/Flightline/Hawk Wing/Afleet Alex/オメガパフューム/フォーティナイナーズサン/Drosselmeyer/
Northern Afleet/Tale of the Cat/バンブーエール/Southern Image/Rahy/ノボジャック/ドリームバレンチノ/スキャン/
Oscar Performance/Van Nistelrooy/Aldebaran/Tizway/Karakontie/E Dubai/Sidney's Candy/Sky Mesa/Grand Slam/Get Stormy/
Birdstone/トワイニング/Fusaichi Pegasus/Freud/To Honor and Serve/Cozzene/Hansen/French Deputy/Midnight Lute/Macho Uno/
Vekoma/Coronado's Quest/Exchange Rate/Constitution/Pure Prize/Tapizar/Posse/Flower Alley/Majestic Warrior/Colonel John/
Cairo Prince/Congaree/Not This Time/Tiz the Law/Seeking the Gold/Super Saver/Smarty Jones/Kameko/McKinzie/Justify/
Bricks and Mortar/Admire Moon/Harlington/Burning Roma/Offlee Wild/Good Magic/Nyquist/Practical Joke/Gio Ponti/
Forest Wildcat/Not For Sale/Big Brown/Forestry/Mitole/Jack Christopher/Verrazano/Upstart/Jimmy Creed/Protectionist/
Eskendereya/Jackie's Warrior/Roman Ruler/Songandaprayer/Maximum Security/Authentic/Adios Charlie/Life Is Good/
Palace Malice/Bolt d'Oro/Air Force Blue/California Chrome/Johannesburg/Pyro/Into the Mystic/Knicks Go/City of Light/
Omaha Beach/Vino Rosso/Klimt/Game Winner/Runhappy/Audible/Improbable/Catholic Boy/Creative Cause/Broken Vow/Super Easy/
Indian Charlie/End Sweep/エンドスウィープ/Mucho Macho Man/Golden Pal/Mo Town/Cross Traffic/Volatile/Unified/
Flameaway/Custom for Carlos/Epicenter/Rock Hard Ten/Awesome Patriot/Speightster/Lookin At Lucky/Wicked Strong/
Graydar/Proud Citizen/Majesticperfection/Point of Entry/War Pass/Stay Inside/Drain the Clock/Sebi Halo/Zensational/
Smoke Glacken/Afternoon Deelites/Hussonet/Officer/Yonaguska/Trappe Shot/Preservationist/Pleasantly Perfect/
Rockport Harbor/Theatrical/Kantharos/Cherokee Run/Cyberknife/Magna Graduate/Uncaptured/Flatter/Tejano Run/
シルバーチャーム/ワンダーアキュート/コパノリチャード/ニシケンモノノフ/テーオーヘリオス/フリオーソ/アポロケンタッキー/
ケイティブレイブ/ブルドッグボス""")

_add(O, """サクラバクシンオー/ショウナンカンプ/Lonhro/Pierro/ビッグアーサー/Zabeel/Octagonal""")

# ビッグアーサーはサクラバクシンオー産駒(Princely Gift系)。


def line_of(sire: str | None) -> str:
    if not sire:
        return "?"
    s = str(sire).strip()
    return _T.get(s, "?")


if __name__ == "__main__":
    import collections
    c = collections.Counter(_T.values())
    print(len(_T), dict(c))
