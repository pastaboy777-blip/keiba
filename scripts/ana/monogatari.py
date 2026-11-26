"""近3走『物語』エンジン — keibabook厩舎談話を3走遡って組み立て、穴サインを炙り出す。
7/13浦和の検証で、単発キーワード2/12→3走アーク物語読み8/10へ改善した読み方を実装。

各馬について:
  - 今回+前2走の厩舎談話(印+コメント)を組み立て
  - 5つの"物語の文法"でスコア化:
      ①本紙印の格上げ(△→○→◎) ②敗因が明確(包まれ/後手/気性=能力否定でない)
      ③叩きローテ完成(休み明け→ひと叩き→3戦目上向き) ④条件好転の明記(距離/場が合う)
      ⑤気配の階段状の充実(馬体増/落ち着き/状態上向き)
  - 人気薄×物語スコア高 = 穴候補★
実際の◎確信は、組み立てたアークをパスタさん/Claudeが"物語"として読んで最終判断。
標準ライブラリ + curl(kb.conf cookie)のみ。
"""
import subprocess,re,os,json,sys

SP=os.path.dirname(os.path.abspath(__file__))
ARC=os.path.join(SP,"arc");os.makedirs(ARC,exist_ok=True)
BASE="https://p.keibabook.co.jp"
RANK={'◎':5,'○':4,'▲':3,'☆':2.5,'△':2,'注':3,'':1,'消':0,'Ｘ':0,'×':0}

# ── 発掘したA型4パターンの語彙(川崎・大井・船橋・浦和 各1開催の実データから) ──
# A1: 敗因が具体的
HAIIN=["躓","落鉄","包まれ","窮屈","出負け","出遅","発馬","後手","イレ込","接触","砂を被",
       "枠順","内枠","気難","気の悪","ゲート","不利","ふらつ","チグハグ","詰ま"]
# A1: 陣営が一変/巻き返しを明言(=最強)
ICHIPEN=["一変","変わり身","巻き返","敗因","見直","一気に"]
# A2: 前走の中身が良い(着順は凡でも)＋相手強化での善戦
NAKAMI=["いい競馬","内容は良","内容が良","内容はいい","内容は悪くな","差を詰め","よく差","納得",
        "よく伸","持ち堪","際ど","惜し","見せ場","強かった","詰めてきた","抵抗",
        "相手が上","相手が一枚","相手が強","一枚上","メンバーが強","勝ち馬が強","ジリジリ寄"]
# H型: 気配の一貫した良化(状態が段階的に上向き/馬体が絞れる/勢い)
HKEHAI=["状態は上向","状態が上向","状態も上向","仕上がってき","絞れて","勢いづい","上向いてき",
        "良化","デキは上向","カイ食い","操縦性も良","動きも良くな","気配は上向","メンタルが戻","板についた"]
# A3: 叩き階段(休み明け→動ける→上向き)
YASUMI=["休み明け","放牧明け","久々","リフレッシュ","間隔","休養","ひと息入れ","ひと開催"]
TATAKI=["ひと叩き","一叩き","1度叩","一度叩","２度叩","二度叩","叩いた","叩いて","叩き","使った","使って","使う毎"]
JOUSHOU=["上向","良化","上積み","固ま","変わって","良くな","動ける","上々","成長","上がって"]
# A4: 条件好転
KOUTEN=["自己条件","クラス","条件に戻","条件も","距離を延ば","距離延長","距離短縮","距離が","得意","歓迎","向く","適し","減量","キロ減","プラス材料","替わり","この条件","戻る"]
# B型: 展開依存・弱気(=談話で取れない穴)
BTENKAI=["スムーズ","揉まれず","展開次第","展開が向","展開さえ","展開嵌","嵌まれ","流れに乗れれ","流れ次第",
         "結果につながら","入着","どうか","難しいかも","展開待ち","粘り込","叩いてから"]
# ── 中央で発掘した追加パターン D/E/F/G(地方でも有効) ──
# D: 陣営が条件を"明示変更"(答え合わせ)
DKAWARI=["芝に戻","ダートに戻","ダートを試","芝を試","距離を延ば","距離を詰め","距離短縮","距離延長",
         "短縮","延長","コース替","替えて","替わり","ワンターン","ブリンカー","一戦","路線変更"]
# E: 滞在・リフレッシュ(夏の北海道ローテ 等)
ETAIZAI=["滞在","リフレッシュ","放牧先から直","短期放牧","放牧を挟","放牧明け","洋芝","現地入り","現地へ","入厩して","移動して"]
# F: 減量騎手×積極策
FGENRYO=["減量","キロ減","積極的","すんなり前","ハナ","前で運べ","前につけ","先行して","逃げ"]
# G: 馬具変更(気性難の解決)
GBAGU=["ブリンカー","チークＰ","チークピーシズ","シャドーロール","メンコ","ホライゾネット","馬具","舌縛","ハミ替","パシュファイヤー"]

def _get(url,out):
    if not os.path.exists(out) or os.path.getsize(out)<500:
        subprocess.run(["curl","-s","-L","-K",os.path.join(SP,"kb.conf"),url,"-o",out],check=False)
    return out

def _clean(raw):
    t=re.sub(r'<[^>]+>',' ',raw);t=re.sub(r'\s+',' ',t).strip()
    # 半角「着 人気」列以降(＝表のゴミ/次馬リンク)を切る。本文の数字は全角なので安全
    t=re.split(r'\s\d+\s+\d+(?:\s|$)',t)[0]
    mm=re.search(r'[―—－\-]{2,}\s*(.+)$',t)
    cm=mm.group(1).strip() if mm else (t.split('】',1)[1].strip() if '】' in t else t)
    return cm.strip()

def race_danwa(rid):
    """レースの談話ページ -> {umacd:{umaban,name,mark,comment}}。"""
    f=_get(f"{BASE}/chihou/danwa/1/{rid}",os.path.join(ARC,f"danwa_{rid}.html"))
    h=open(f,encoding='utf-8',errors='replace').read()
    out={}
    for m in re.finditer(r'umacd="(\d+)"(.*?)(?=umacd="|</table>|\Z)',h,re.S):
        cd,body=m.group(1),m.group(2)
        um=re.search(r'umaban">\s*(\d+)',h[max(0,m.start()-260):m.start()])
        t=re.sub(r'<[^>]+>',' ',body);t=re.sub(r'\s+',' ',t).strip()
        nm=re.search(r'([゠-ヿ一-龯ー]{2,})\s+[牡牝セ]',t)
        mk=re.search(r'([◎○▲△☆注消Ｘ×])',t)
        out[cd]={"umaban":int(um.group(1)) if um else None,
                 "name":nm.group(1) if nm else None,
                 "mark":mk.group(1) if mk else "","comment":_clean(body)}
    return out

def horse_recent_rids(umacd,n=3):
    f=_get(f"{BASE}/db/uma/{umacd}/kanzen",os.path.join(ARC,f"uma_{umacd}.html"))
    h=open(f,encoding='utf-8',errors='replace').read()
    rids=re.findall(r'/chihou/seiseki/(2026\d{12})',h)
    return sorted(set(rids),key=lambda x:x[-4:],reverse=True)[:n]

def horse_comment(rid,umacd):
    d=race_danwa(rid)
    return d.get(umacd)

def _has(text,words): return any(w in text for w in words)

def grammar_score(marks,comments):
    """発掘したA型4パターン＋B型除外で判定。
    戻り値: (score, tags)。tagsは 'A1敗因一変'/'A2前走中身'/'A3叩き階段'/'A4好転/格上げ'/'B展開依存'。
    A型が1つでも立てば穴候補(score>=2.5)。B型のみは談話で取れない穴として負に。"""
    now=comments[0] if comments else ""
    prev=" ".join(comments[1:]) if len(comments)>1 else ""
    allt=" ".join(comments)
    sc=0.0;tags=[]
    # A1: 敗因明確（前走/2走前）＋ 一変/巻き返し明言 → 最強
    haiin=_has(prev,HAIIN) or _has(now,["前走"]) and _has(now,HAIIN)
    ichi=_has(allt,ICHIPEN)
    if haiin and ichi: sc+=3.0;tags.append("A1敗因→一変★")
    elif haiin: sc+=1.5;tags.append("A1敗因明確")
    # A2: 前走の中身が良い（着順は凡でも）
    if _has(prev,NAKAMI) or _has(now,["前走の内容","前走はいい","前走はよく","前走は強"]):
        sc+=2.0;tags.append("A2前走中身良")
    # A3: 叩き階段（休み明けの下地 × 直近で叩き上昇）
    if _has(allt,YASUMI) and _has(now,TATAKI) and _has(now,JOUSHOU):
        sc+=2.5;tags.append("A3叩き階段")
    elif _has(now,TATAKI) and _has(now,JOUSHOU):
        sc+=1.5;tags.append("A3叩き上昇")
    # A4: 本紙印の格上げ（前走の実印があるときだけ）or 条件好転の明記
    if len(marks)>1 and marks[1]:  # 前走に実際の印がある
        m0=RANK.get(marks[0],1);m1=RANK.get(marks[1],1)
        if m0>m1: sc+=1.5;tags.append("A4印上昇")
    if _has(now,KOUTEN): sc+=1.0;tags.append("A4条件好転")
    # D: 陣営が条件を明示変更(答え合わせ)。"戻す/試す"は特に強い意思表示
    if _has(now,["戻し","戻す","試そ","試す","試して","路線変更"]) and _has(now,DKAWARI):
        sc+=1.5;tags.append("D条件替わり★")
    elif _has(now,DKAWARI): sc+=1.0;tags.append("D条件替わり")
    # E: 滞在・リフレッシュ
    if _has(now,ETAIZAI): sc+=1.0;tags.append("E滞在/リフレッシュ")
    # F: 減量騎手×積極策
    if _has(now,["減量","キロ減"]) and _has(now,["積極","前","ハナ","先行","逃げ","すんなり"]):
        sc+=1.0;tags.append("F減量×積極")
    # G: 馬具変更(気性難の解決サイン)
    if _has(now,GBAGU):
        sc+=1.0;tags.append("G馬具変更")
    # H: 気配の一貫した良化(3走で段階的に上向き=最も見逃しが多かった型)
    allt=" ".join(comments)
    if _has(now,HKEHAI) and _has(prev,HKEHAI): sc+=1.5;tags.append("H気配良化(一貫)")
    elif _has(now,HKEHAI): sc+=0.8;tags.append("H気配良化")
    # B型: A/D/E/F/G型が一切立たず、展開依存/弱気のみ → 談話で取れない穴
    if not tags and _has(now,BTENKAI):
        tags.append("B展開依存(談話×)")
    return round(sc,1),tags

def verdict(score,tags,ninki=None):
    """穴候補ラベル(3段階)。人気薄(5人気以下)は★を強調。
    物語型=A(敗因/中身/叩き/条件)・D(条件替わり)・E(滞在)・F(減量×積極)・G(馬具)。"""
    story=tuple("ADEFGH")
    is_S=any(t[0] in story for t in tags)
    is_B=any(t.startswith("B") for t in tags)
    ana="" if (ninki is None or ninki>=5) else "(人気)"
    if is_S and score>=2.5: return f"★★本命級・物語濃厚{ana}"
    if is_S: return f"★穴候補{ana}"
    if is_B: return "B型=談話×→実力v2/馬場/脚質で判断"
    return "-"

def build(rno,ymd_head="2026071301",tail="0713"):
    rid=f"{ymd_head}{rno:02d}{tail}"
    today=race_danwa(rid)
    rows=[]
    for cd,info in today.items():
        rids=horse_recent_rids(cd)
        marks=[info["mark"]];comments=[info["comment"]];arc=[(rid[-4:],info["mark"],info["comment"])]
        for prid in rids[1:3]:
            pc=horse_comment(prid,cd)
            if pc: marks.append(pc["mark"]);comments.append(pc["comment"]);arc.append((prid[-4:],pc["mark"],pc["comment"]))
            else: arc.append((prid[-4:],"","(取得不可)"))
        sc,tags=grammar_score(marks,comments)
        rows.append({"umaban":info["umaban"],"name":info["name"],"umacd":cd,
                     "score":sc,"tags":tags,"arc":arc})
    rows.sort(key=lambda r:(r["umaban"] or 99))
    return rows

if __name__=="__main__":
    rno=int(sys.argv[1]) if len(sys.argv)>1 else 8
    head=sys.argv[2] if len(sys.argv)>2 else "2026071301"
    tail=sys.argv[3] if len(sys.argv)>3 else "0713"
    rows=build(rno,ymd_head=head,tail=tail)
    print(f"=== 浦和 {rno}R 近3走『物語』診断 (A型4パターン検出) ===")
    for r in sorted(rows,key=lambda x:-x["score"]):
        v=verdict(r["score"],r["tags"])
        if v=="-": continue
        print(f"\n{r['umaban']:>2} {r['name']}  {v}  物語{r['score']:+.1f} [{'/'.join(r['tags'])}]")
        for mmdd,mk,cm in r["arc"]:
            print(f"    {mmdd[:2]}/{mmdd[2:]} {mk or '－'} 「{cm[:64]}」")
