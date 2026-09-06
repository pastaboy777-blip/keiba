"""画面録画用のデモ(SNS向け)。

`scripts/demo.py` と同じパイプラインを、**動画で見て分かる**ように演出して流す。
収集 → 特徴量 → スコア → 確率 → 期待値判定 → バックテストROI を
1本の流れとして順に描画する。

実行:
    python3 scripts/show.py                # 標準速度(録画用・約90秒)
    python3 scripts/show.py --speed 2      # 倍速
    python3 scripts/show.py --instant      # 演出なし(動作確認用)
    python3 scripts/show.py --no-color     # 色なし

録画のコツ:
    ターミナルを縦長(幅64桁前後)にすると、スマホ縦動画でも文字が読める。
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import synth, betting as bt, probability as pb
from nankeiba.core import interval as iv
from nankeiba.core.backtest import run_backtest
from nankeiba.core.features import RaceContext, ScoreWeights, horse_features, horse_score

WIDTH = 62

# ---------------------------------------------------------------- 表示ユーティリティ

class Style:
    """ANSI エスケープ。--no-color 指定時は全て空文字になる。"""

    def __init__(self, enabled: bool = True) -> None:
        def c(code: str) -> str:
            return code if enabled else ""
        self.reset = c("\033[0m")
        self.bold = c("\033[1m")
        self.dim = c("\033[2m")
        self.red = c("\033[38;5;203m")
        self.green = c("\033[38;5;114m")
        self.yellow = c("\033[38;5;221m")
        self.blue = c("\033[38;5;75m")
        self.magenta = c("\033[38;5;176m")
        self.cyan = c("\033[38;5;80m")
        self.gray = c("\033[38;5;244m")
        self.white = c("\033[38;5;255m")


S = Style()
SPEED = 1.0


def pause(seconds: float) -> None:
    if SPEED <= 0:
        return
    time.sleep(seconds / SPEED)


def dwidth(s: str) -> int:
    """全角を2桁として数えた表示幅(ANSI エスケープは除外)。"""
    out = 0
    i = 0
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
            i += 1
            continue
        out += 2 if unicodedata.east_asian_width(s[i]) in ("W", "F") else 1
        i += 1
    return out


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - dwidth(s))


def type_out(text: str, delay: float = 0.012, end: str = "\n") -> None:
    """1文字ずつ流す(タイプライタ演出)。"""
    if SPEED <= 0:
        print(text, end=end, flush=True)
        return
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay / SPEED)
    sys.stdout.write(end)
    sys.stdout.flush()


def rule(char: str = "─") -> None:
    print(f"{S.gray}{char * WIDTH}{S.reset}")


def header(title: str, subtitle: str = "") -> None:
    print()
    print(f"{S.cyan}┌{'─' * (WIDTH - 2)}┐{S.reset}")
    line = f"{S.cyan}│{S.reset} {S.bold}{S.white}{title}{S.reset}"
    print(pad(line, WIDTH - 1) + f"{S.cyan}│{S.reset}")
    if subtitle:
        line = f"{S.cyan}│{S.reset} {S.gray}{subtitle}{S.reset}"
        print(pad(line, WIDTH - 1) + f"{S.cyan}│{S.reset}")
    print(f"{S.cyan}└{'─' * (WIDTH - 2)}┘{S.reset}")
    pause(0.35)


def progress(label: str, total: int, *, color: str = "", duration: float = 1.2) -> None:
    """ラベル付きプログレスバーを1本描く(同じ行を上書き)。"""
    color = color or S.green
    bar_w = 28
    if SPEED <= 0:
        print(f"  {pad(label, 18)} {color}{'█' * bar_w}{S.reset} {total:>6,}  {S.green}✓{S.reset}")
        return
    steps = 24
    for i in range(steps + 1):
        frac = i / steps
        filled = int(bar_w * frac)
        bar = "█" * filled + "░" * (bar_w - filled)
        n = int(total * frac)
        sys.stdout.write(
            f"\r  {pad(label, 18)} {color}{bar}{S.reset} {n:>6,}"
        )
        sys.stdout.flush()
        pause(duration / steps)
    print(f"  {S.green}✓{S.reset}")


def score_bar(value: float, lo: float, hi: float, width: int = 20) -> str:
    """スコアを相対バーに変換。"""
    span = hi - lo or 1.0
    frac = max(0.0, min(1.0, (value - lo) / span))
    filled = int(round(width * frac))
    return "▇" * filled + f"{S.gray}·{S.reset}" * (width - filled)


# ---------------------------------------------------------------- 各シーン

PLACE_ROMAJI = {"大井": "ooi", "川崎": "kawasaki", "船橋": "funabashi", "浦和": "urawa"}


def scene_title(place: str) -> None:
    print()
    for line in [
        f"{S.bold}{S.cyan}  南関競馬 予測エンジン{S.reset}",
        f"{S.gray}  大井 / 川崎 / 船橋 / 浦和 — 回収率特化{S.reset}",
    ]:
        print(line)
        pause(0.3)
    print()
    romaji = PLACE_ROMAJI.get(place, place)
    type_out(f"{S.dim}  $ python3 -m nankeiba.run --place {romaji}{S.reset}", delay=0.03)
    pause(0.6)


def scene_collect(n_races: int):
    header("① データ収集", "netkeiba 地方 — 結果 / オッズ")
    races, jockeys, trainers = synth.generate_season(n_races=n_races, seed=7)
    progress("レース結果", len(races), color=S.blue)
    progress("出走馬レコード", sum(len(r.entries) for r in races), color=S.blue)
    progress("三連単オッズ", sum(len(r.trifecta_odds) for r in races), color=S.blue)
    return races, jockeys, trainers


def scene_features(runs, ctx) -> None:
    header("② 特徴量抽出", "「ズブい馬をいかに走らせるか」を数値化")
    feats = horse_features(runs, ctx)
    labels = {
        "ability": "能力ベースライン",
        "interval_fit": "出走間隔フィット",
        "toughness": "タフネス(ズブさ)",
        "tatakii": "叩き何走目",
        "senkou": "先行力",
        "agari": "末脚",
        "baba_fit": "馬場適性",
        "place_fit": "競馬場替わり",
        "distance_fit": "距離変更",
        "fatigue": "使い込み疲労",
    }
    for key, label in labels.items():
        v = feats.get(key, 0.0)
        color = S.green if v >= 0 else S.red
        num = f"{'+' if v >= 0 else '-'}{abs(v):.3f}"
        bar_w = min(16, int(abs(v) * 22))
        bar = ("▇" * bar_w) or "·"
        print(f"  {pad(label, 20)} {color}{num:>7}{S.reset}  {color}{bar}{S.reset}")
        pause(0.13)
    pause(0.5)


def scene_rank(scores: dict, names: dict, pops: dict) -> list[int]:
    header("③ 強さスコア", "過去走のみ使用(リーク無し)")
    lo, hi = min(scores.values()), max(scores.values())
    order = sorted(scores, key=lambda u: scores[u], reverse=True)
    print(f"  {S.gray}順 馬番 {pad('馬名', 14)}人気   スコア{S.reset}")
    for rank, um in enumerate(order, 1):
        mark = f"{S.yellow}◎{S.reset}" if rank == 1 else (
            f"{S.magenta}○{S.reset}" if rank == 2 else (
                f"{S.blue}▲{S.reset}" if rank == 3 else " "))
        pop = pops[um]
        # 人気とスコア順の乖離=市場の歪み。乖離が大きい馬を強調。
        gap = pop - rank
        pop_s = f"{S.red}{pop:>2d}人気{S.reset}" if gap >= 4 else f"{S.gray}{pop:>2d}人気{S.reset}"
        bar = score_bar(scores[um], lo, hi)
        print(f"  {mark}{rank:>2d} {um:>3d} {pad(names[um], 14)}{pop_s} {S.cyan}{bar}{S.reset}")
        pause(0.10)
    print()
    hidden = [u for i, u in enumerate(order[:3], 1) if pops[u] - i >= 4]
    if hidden:
        for u in hidden:
            type_out(
                f"  {S.yellow}▶ ズブ穴検出{S.reset} {names[u]}"
                f"（{pops[u]}人気 → モデル{order.index(u) + 1}位）",
                delay=0.02,
            )
            pause(0.4)
    pause(0.5)
    return order


def scene_probability(strengths: dict) -> dict:
    header("④ 確率変換", "Plackett-Luce モデル → 三連複の的中確率")
    probs = pb.trio_probabilities(strengths)
    top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:6]
    peak = top[0][1] if top else 1.0
    for combo, p in top:
        label = "-".join(str(c) for c in combo)
        # 上位同士の差が小さいので、最大値を基準に相対表示する
        bar = "▇" * max(1, round(24 * p / peak))
        print(f"  {pad(label, 12)} {S.magenta}{p * 100:>5.2f}%{S.reset}  {S.magenta}{bar}{S.reset}")
        pause(0.14)
    pause(0.5)
    return probs


def scene_ev(probs: dict, odds: dict, threshold: float) -> list:
    header("⑤ 期待値判定", f"確率 × オッズ > {threshold} の買い目だけ買う")
    cands = sorted(
        ((c, p, odds[c], p * odds[c]) for c, p in probs.items() if c in odds),
        key=lambda t: t[3],
        reverse=True,
    )[:9]
    bought = 0
    for combo, p, o, ev in cands:
        label = "-".join(str(c) for c in combo)
        if ev > threshold:
            bought += 1
            verdict = f"{S.green}● 買い{S.reset}"
            evs = f"{S.green}{S.bold}EV {ev:>5.2f}{S.reset}"
        else:
            verdict = f"{S.gray}○ 見送り{S.reset}"
            evs = f"{S.gray}EV {ev:>5.2f}{S.reset}"
        print(
            f"  {pad(label, 11)}{S.gray}{p * 100:>5.2f}% ×{S.reset}"
            f"{o:>7.1f}倍  {evs}  {verdict}"
        )
        pause(0.18)
    print()
    type_out(
        f"  {S.bold}控除率27.5%を超える買い目のみ {bought} 点を購入{S.reset}", delay=0.02
    )
    pause(0.7)
    return bt.select_ev_bets(probs, odds, ev_threshold=threshold, max_bets=6)


def sparkline(
    series: list[float], width: int = WIDTH - 6, height: int = 8
) -> tuple[list[str], int, float, float]:
    """収支推移をブロック文字のチャートに変換。

    Returns:
        (行のリスト, 損益ゼロの行番号, 最小値, 最大値)
    """
    if not series:
        return [], 0, 0.0, 0.0
    step = max(1, len(series) // width)
    pts = series[::step][:width]
    lo, hi = min(pts + [0.0]), max(pts + [0.0])
    span = hi - lo or 1.0
    rows = [[" "] * len(pts) for _ in range(height)]
    zero_row = height - 1 - int((0.0 - lo) / span * (height - 1))
    for x, v in enumerate(pts):
        y = height - 1 - int((v - lo) / span * (height - 1))
        rows[y][x] = "●"
        for yy in range(min(y, zero_row) + 1, max(y, zero_row)):
            rows[yy][x] = "│"
    return ["".join(r) for r in rows], zero_row, lo, hi


def scene_backtest(races, jockeys, trainers) -> float:
    header("⑥ バックテスト", "時系列・リーク無しで回収率を検証")
    res = run_backtest(
        races, jockeys=jockeys, trainers=trainers, weights=ScoreWeights(),
        bet_type="trio", ev_threshold=1.3, max_bets=6, min_history=4,
    )
    if not res.pnl_history:
        print(f"  {S.gray}買い目が発生しませんでした{S.reset}")
        return 0.0

    rows, zero_row, lo, hi = sparkline(res.pnl_history)
    print(f"  {S.gray}収支推移(円){S.reset}")
    for i, row in enumerate(rows):
        color = S.green if i < zero_row else S.red
        tag = f"{hi:>+8,.0f}" if i == 0 else (
            f"{lo:>+8,.0f}" if i == len(rows) - 1 else " " * 8)
        line = "".join(
            (f"{color}{ch}{S.reset}" if ch != " " else " ") for ch in row
        )
        print(f"  {S.gray}{tag}{S.reset} {line}")
        pause(0.16)
    print()

    stats = [
        ("購入レース数", f"{res.n_bet_races:,}"),
        ("購入点数", f"{res.n_bets:,}"),
        ("的中", f"{res.n_hits:,}"),
        ("的中率", f"{res.hit_rate:.1%}"),
        ("投資額", f"{res.spent:,.0f} 円"),
        ("払戻額", f"{res.returned:,.0f} 円"),
    ]
    for label, value in stats:
        print(f"  {pad(label, 16)}{S.white}{value:>16}{S.reset}")
        pause(0.14)

    print()
    roi = res.roi
    color = S.green if roi >= 1.0 else S.red
    box = f" 回収率  {roi:.1%} "
    inner = WIDTH - 2
    print(f"{color}┏{'━' * inner}┓{S.reset}")
    print(f"{color}┃{S.reset}" + pad(f"{color}{S.bold}{box}{S.reset}", inner) + f"{color}┃{S.reset}")
    print(f"{color}┗{'━' * inner}┛{S.reset}")
    pause(0.9)
    return roi


def naive_favorite_roi(races, *, top_k: int = 4, stake: float = 100.0) -> float:
    """比較用の素朴戦略: 三連複でオッズが低い(人気)上位 top_k 点を機械的に買う。"""
    spent = ret = 0.0
    for race in races:
        if not race.trio_odds:
            continue
        cheap = sorted(race.trio_odds.items(), key=lambda kv: kv[1])[:top_k]
        result = tuple(sorted(race.result_order[:3]))
        for combo, odds in cheap:
            spent += stake
            if combo == result:
                ret += stake * odds
    return ret / spent if spent else 0.0


def scene_compare(model_roi: float, naive_roi: float) -> None:
    header("⑦ 比較", "同じレースを「人気順に買う」とどうなるか")
    rows = [
        ("人気順に4点買い", naive_roi, S.red),
        ("期待値プラスのみ購入", model_roi, S.green),
    ]
    for label, roi, color in rows:
        bar = "▇" * min(30, max(1, int(roi * 24)))
        print(f"  {pad(label, 22)}{color}{roi:>7.1%}{S.reset}  {color}{bar}{S.reset}")
        pause(0.5)
    print()
    diff = (model_roi - naive_roi) * 100
    type_out(f"  {S.bold}差 {diff:+.1f} ポイント{S.reset}", delay=0.03)
    pause(0.8)


def scene_outro() -> None:
    print()
    rule()
    for line in [
        f"  {S.bold}的中率ではなく、回収率で勝つ。{S.reset}",
        f"  {S.gray}期待値プラスの買い目だけを買う設計{S.reset}",
    ]:
        type_out(line, delay=0.03)
        pause(0.25)
    rule()
    print(
        f"  {S.dim}※ 本デモは合成データによるロジック検証です。"
        f"実データでの検証が必須。{S.reset}"
    )
    print()


# ---------------------------------------------------------------- レース1本の題材作り

def pick_showcase_race(races, *, place: str | None = None, min_history: int = 4):
    """履歴が十分たまった時点のレースを1本選び、その時点の過去走だけを返す。

    run_backtest と同じ順序で履歴を積み上げるので、リークは無い。
    """
    history: dict[object, list[iv.RunRecord]] = {}
    races = sorted(races, key=lambda r: r.date)
    chosen = None
    for race in races:
        if (chosen is None and len(race.entries) >= 8
                and (place is None or race.place == place)):
            past = {e.num(): list(history.get(e.horse_id, [])) for e in race.entries}
            if all(len(v) >= min_history for v in past.values()):
                chosen = (race, past)
        pos_of = {um: i + 1 for i, um in enumerate(race.result_order)}
        for e in race.entries:
            history.setdefault(e.horse_id, []).insert(0, iv.RunRecord(
                date=race.date, place=race.place, distance=race.distance,
                field_size=race.field_size,
                finish_pos=pos_of.get(e.num(), race.field_size),
                jockey=e.jockey, trainer=e.trainer,
            ))
        if chosen is not None:
            break
    return chosen


def main() -> None:
    global SPEED, S, WIDTH

    ap = argparse.ArgumentParser(description="画面録画用デモ")
    ap.add_argument("--speed", type=float, default=1.0, help="演出速度(2で倍速)")
    ap.add_argument("--instant", action="store_true", help="演出なしで一気に出力")
    ap.add_argument("--no-color", action="store_true", help="色を使わない")
    ap.add_argument("--width", type=int, default=WIDTH, help="表示幅(桁)")
    ap.add_argument("--races", type=int, default=600, help="合成レース数")
    ap.add_argument("--seed", type=int, default=7, help="乱数シード")
    ap.add_argument("--place", default="川崎",
                    choices=["大井", "川崎", "船橋", "浦和"],
                    help="題材にする競馬場")
    args = ap.parse_args()

    SPEED = 0.0 if args.instant else max(0.1, args.speed)
    S = Style(enabled=not args.no_color)
    WIDTH = max(40, args.width)

    random.seed(args.seed)

    scene_title(args.place)
    races, jockeys, trainers = scene_collect(args.races)

    picked = pick_showcase_race(races, place=args.place)
    if picked is None:
        print(f"{args.place}で題材にできるレースが見つかりませんでした"
              "(--races を増やしてください)")
        return
    race, past = picked

    names = {e.num(): f"{race.place}{e.num():02d}号" for e in race.entries}
    ctx_of = {
        e.num(): RaceContext(
            date=race.date, place=race.place, distance=race.distance,
            field_size=race.field_size, jockey=e.jockey, trainer=e.trainer,
        )
        for e in race.entries
    }

    header("対象レース", f"{race.place} ダ{race.distance}m {race.field_size}頭  {race.date}")
    pause(0.4)

    # 一番人気薄の馬を1頭選んで特徴量を見せる(ズブ穴の説明になる)
    pops = {}
    for i, (um, o) in enumerate(
        sorted(((e.num(), 0.0) for e in race.entries), key=lambda kv: kv[0]), 1
    ):
        pops[um] = i
    scores = {
        e.num(): horse_score(past[e.num()], ctx_of[e.num()],
                             jockeys=jockeys, trainers=trainers,
                             weights=ScoreWeights())
        for e in race.entries
    }
    # 「人気」はモデルを使わない素朴指標(直近着順)で代用して市場役にする
    naive = {
        um: sum(r.finish_pos for r in past[um][:3]) / max(1, len(past[um][:3]))
        for um in scores
    }
    for rank, um in enumerate(sorted(naive, key=lambda u: naive[u]), 1):
        pops[um] = rank

    sample = min(scores, key=lambda u: -pops[u])
    scene_features(past[sample], ctx_of[sample])

    order = scene_rank(scores, names, pops)
    strengths = pb.strengths_from_scores(scores, temperature=1.0)
    probs = scene_probability(strengths)
    scene_ev(probs, race.trio_odds, threshold=1.3)
    model_roi = scene_backtest(races, jockeys, trainers)
    scene_compare(model_roi, naive_favorite_roi(races))
    scene_outro()


if __name__ == "__main__":
    main()
