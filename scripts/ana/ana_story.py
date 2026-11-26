"""談話"物語"エンジンの常時運用ラッパー ── 人気薄×上昇物語の穴を自動ランク。
monogatari.build() が近3走アーク+grammar_scoreで物語型(A敗因→一変/H気配良化/
D条件替わり/F減量×積極/G馬具 等)を検出済み。ここに単勝人気を重ね、
"人気薄(既定6人気以下)×物語スコア高"を★穴として毎レース提示する。
"""
import sys
import monogatari as M
import cyokyo_ana as C

def analyze(rid, unpop_from=6):
    rno = int(rid[10:12]); head = rid[:10]; tail = rid[12:]
    rows = M.build(rno, ymd_head=head, tail=tail)
    od, rank = C.odds_rank(rid)
    out = []
    for r in rows:
        ub = r["umaban"]; pk = rank.get(ub, 99)
        v = M.verdict(r["score"], r["tags"], ninki=pk)
        ana = "★物語の穴" if (pk >= unpop_from and r["score"] >= 2.0 and
                             any(t[0] in "ADEFGH" for t in r["tags"])) else ""
        out.append((r["score"], ub, r["name"], pk, od.get(ub), r["tags"], v, ana))
    out.sort(key=lambda x: (-x[0], x[3]))
    return out

if __name__ == "__main__":
    rid = sys.argv[1]
    print(f"=== 物語エンジン(人気薄フィルタ) {rid} ===")
    for sc, ub, nm, pk, o, tags, v, ana in analyze(rid):
        if sc <= 0 and not ana: continue
        star = "  " + ana if ana else ""
        print(f"  物語{sc:+.1f} | {ub:2}番 {nm} | {pk}人{o} | {v} [{'/'.join(tags)}]{star}")
