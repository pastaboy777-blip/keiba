"""条件ごとの水準をつくり、**同じ対象が両方を経験した記録**で系統差を測って補正する。

競馬から取り出した汎用部分。拠点・機材・検査室・担当者など、
**測る場所によって数値の水準がずれるデータ**なら同じ形で使える。

  from level import Level
  L = Level(rows, subject="horse", group="venue", cond="distance", value="agari")
  L.fit()
  L.adjusted(value=38.4, group="浦和", cond=800)   # 基準の場に揃えた値

── なぜ2段階いるのか

  **1段階目（水準を引く）だけでは足りない。**

  各グループの中央値を引けば、グループ間の「平均的な差」は消える。
  ところが**対象の顔ぶれがグループごとに違う**と、中央値そのものが
  その顔ぶれに引きずられる。結果、水準を引いたあとにも系統差が残る。

  2段階目は、**同じ対象が複数のグループを経験した記録**だけを使う。
  同じ対象なので顔ぶれの違いが相殺され、グループ固有のズレだけが残る。

── 実例（2026-11-10、地方競馬の上がり3F）

  浦和800m の水準 35.5秒 ／ 川崎900m の水準 37.8秒。まず水準を引いた。
  それでも、同じ馬が両方を走った記録を見ると

    浦和 − 船橋 −0.60秒（360頭） ／ 川崎 − 浦和 +0.30秒（273頭）
    川崎 − 船橋 −0.25秒（213頭） ／ 大井 − 川崎 +0.05秒（49頭）

  **水準を引いたあとでも浦和が0.3〜0.6秒速く出る**（砂が軽い）。
  この残差を offset として足して初めて、別グループの対象を並べられる。

  補正前は、浦和で走った馬ばかりが上位を占めていた。
  補正後に3位へ上がった馬が、そのレースで11番人気2着だった。

── 使うときの注意

  1. **ペアの n が小さいグループの offset は信用しない。**
     上の例で大井は42〜56件しかなく、他のペアと整合が取れていなかった。
     `fit()` は各 offset の根拠件数を返すので、必ず見ること。
  2. 2つ以上のグループを経験した対象が少なすぎると、そもそも解けない。
  3. offset は**基準グループからの相対値**。基準を変えれば全部ずれる。
"""
import statistics as st
import collections
import itertools


class Level:
    def __init__(self, rows, subject, group, cond, value, min_per_cell=4, min_runs=2):
        """rows … dict のリスト。subject/group/cond/value はそのキー名。
        min_per_cell … 水準（中央値）を作るのに要る最低件数
        min_runs      … 1つの対象がそのグループで何件以上あれば「経験した」とみなすか
        """
        self.rows, self.S, self.G, self.C, self.V = rows, subject, group, cond, value
        self.min_per_cell, self.min_runs = min_per_cell, min_runs
        self.base = {}      # (group, cond) -> 中央値
        self.offset = {}    # group -> 残った系統差（基準グループ＝0）
        self.pair_n = {}    # (a, b) -> 根拠件数
        self.pair_d = {}    # (a, b) -> 実測した差の中央値
        self.ref = None

    # ── 1段階目 ────────────────────────────────
    def _baseline(self):
        cell = collections.defaultdict(list)
        for r in self.rows:
            if r.get(self.V) is None:
                continue
            cell[(r[self.G], r[self.C])].append(r[self.V])
        self.base = {k: st.median(v) for k, v in cell.items() if len(v) >= self.min_per_cell}

    def deviation(self, r):
        """水準との差。基準が無いセルは None"""
        b = self.base.get((r[self.G], r[self.C]))
        if b is None or r.get(self.V) is None:
            return None
        return r[self.V] - b

    # ── 2段階目 ────────────────────────────────
    def _offsets(self, ref=None):
        per = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in self.rows:
            d = self.deviation(r)
            if d is not None:
                per[r[self.S]][r[self.G]].append(d)
        pair = collections.defaultdict(list)
        for subj, gs in per.items():
            med = {g: st.median(v) for g, v in gs.items() if len(v) >= self.min_runs}
            for a, b in itertools.combinations(sorted(med), 2):
                pair[(a, b)].append(med[a] - med[b])
        diff = {k: st.median(v) for k, v in pair.items()}
        self.pair_d = diff
        self.pair_n = {k: len(v) for k, v in pair.items()}
        groups = sorted({g for k in diff for g in k})
        if not groups:
            self.offset = {}
            return
        self.ref = ref if ref in groups else max(
            groups, key=lambda g: sum(n for k, n in self.pair_n.items() if g in k))
        # 基準からの距離が近いものから順に埋める（幅優先）。
        # ★ 連立で解かずこの形にしたのは、ペアが欠けていても落ちないため。
        off = {self.ref: 0.0}
        changed = True
        while changed:
            changed = False
            for (a, b), d in sorted(diff.items(), key=lambda kv: -self.pair_n[kv[0]]):
                if a in off and b not in off:
                    off[b] = off[a] - d; changed = True
                elif b in off and a not in off:
                    off[a] = off[b] + d; changed = True
        # 基準に揃えるには「その差を足す」形にしたいので符号を反転
        self.offset = {g: -v for g, v in off.items()}

    def fit(self, ref=None):
        self._baseline()
        self._offsets(ref)
        return self

    # ── 使うとき ───────────────────────────────
    def adjusted(self, value, group, cond):
        """基準グループに揃えた値。小さいほど「速い／良い」側（元の指標の向き次第）。
        基準の無いセルや未知のグループは None。"""
        b = self.base.get((group, cond))
        if b is None:
            return None
        return value - b + self.offset.get(group, 0.0)

    def report(self):
        out = ["水準 … %d セル（%s × %s）" % (len(self.base), self.G, self.C),
               "基準グループ … %s" % self.ref, "",
               "%-16s %10s %10s" % ("グループ", "補正", "根拠件数")]
        for g, v in sorted(self.offset.items(), key=lambda kv: kv[1]):
            n = sum(n for k, n in self.pair_n.items() if g in k)
            out.append("%-16s %+10.2f %10d%s" % (g, v, n, "   ※件数が少ない" if n < 100 else ""))
        out.append("")
        out.append("ペアごとの実測差（基準にした値）")
        for k in sorted(self.pair_n, key=lambda k: -self.pair_n[k]):
            out.append("  %-8s − %-8s  %+6.2f  （%d件）" % (
                k[0], k[1], self.pair_d[k], self.pair_n[k]))
        return "\n".join(out)
