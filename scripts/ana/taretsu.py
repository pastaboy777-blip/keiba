"""相対テン速度で脚質序列化 ── 隊列とペースを精度よく予想。
各馬の近走の各コーナー通過を集計し、"先行力"(=前に行く強さ)を数値化。
絶対位置ではなく、そのレースの相対順位で隊列を組む(同型が揃えば1頭は控える)。
出力: 想定隊列(逃げ→後方) と 逃げ争い頭数 → ペース(超ハイ/ハイ/平均/スロー)。
先行力 = 近走の1角通過の平均(小さいほど前)。テン誘導。ハナ意欲は談話も加味。
標準ライブラリ + monogatari。
"""
import re, os, sys
import monogatari as M

def _uncircle(s):
    # 丸数字①..⑳ を通常数字へ (U+2460=① -> 1)
    out = []
    for ch in s:
        o = ord(ch)
        if 0x2460 <= o <= 0x2473: out.append(str(o - 0x2460 + 1))
        else: out.append(ch)
    return "".join(out)

NIGE_WORD = ["ハナ", "逃げ", "先手", "すんなり前", "前で運", "前につけ", "行き脚", "積極", "主張"]
SASHI_WORD = ["差し", "追い込", "終い", "末脚", "後方", "脚を溜め", "外から"]

def prof(cd):
    rids = M.horse_recent_rids(cd, 3)
    firsts = []; lasts = []
    for r in rids:
        f = M._get(f"{M.BASE}/chihou/seiseki/{r}", os.path.join(M.ARC, f"sei_{r}.html"))
        h = open(f, encoding="utf-8", errors="replace").read()
        idx = h.find(f'umacd="{cd}"')
        if idx < 0: continue
        start = h.rfind("<tr>", 0, idx); end = h.find("</tr>", idx)
        c = [_uncircle(re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", h[start:end], re.S)]
        tsu = next((x for x in c if re.match(r"^\d+(\s+\d+){1,3}$", x)), None)
        if not tsu: continue
        nums = [int(x) for x in tsu.split()]
        firsts.append(nums[0]); lasts.append(nums[-1])
    avg1 = sum(firsts) / len(firsts) if firsts else 9.9
    return avg1, firsts

def analyze(rid):
    danwa = M.race_danwa(rid)
    horses = []
    for cd, info in danwa.items():
        ub = info.get("umaban")
        if ub is None: continue
        avg1, firsts = prof(cd)
        cm = info.get("comment", "") or ""
        nige_intent = sum(1 for w in NIGE_WORD if w in cm)
        sashi_intent = sum(1 for w in SASHI_WORD if w in cm)
        # 先行力スコア: 通過が前(小)ほど高く、ハナ意欲で補正
        senkou = -(avg1) + 0.4 * nige_intent - 0.3 * sashi_intent
        horses.append({"ub": ub, "name": info.get("name"), "avg1": avg1,
                       "senkou": senkou, "nige_intent": nige_intent})
    horses.sort(key=lambda x: -x["senkou"])
    # 相対脚質ラベル
    n = len(horses)
    for i, hh in enumerate(horses):
        if i == 0: hh["role"] = "逃げ"
        elif i <= max(1, n // 4): hh["role"] = "先行"
        elif i <= n // 2: hh["role"] = "好位"
        elif i <= n * 3 // 4: hh["role"] = "中団"
        else: hh["role"] = "後方"
    # 逃げ争い頭数 = 近走で1角2番手以内が多い馬(絶対的な前々型)
    front = [h for h in horses if h["avg1"] <= 2.6]
    nf = len(front)
    pace = "超ハイ" if nf >= 4 else "ハイ" if nf >= 2 else "平均" if nf == 1 else "スロー(単騎不在)"
    return horses, front, pace

if __name__ == "__main__":
    rid = sys.argv[1]
    horses, front, pace = analyze(rid)
    print(f"=== 想定隊列/ペース {rid} ===  逃げ争い{len(front)}頭 → ペース【{pace}】")
    for hh in horses:
        fi = "★前々型" if hh["avg1"] <= 2.6 else ""
        print(f"  {hh['role']:>2} | {hh['ub']:2}番 {hh['name']} | 近走1角avg{hh['avg1']:.1f} 先行力{hh['senkou']:+.1f} {fi}")
