#!/usr/bin/env python3
"""
paddock_ledger.py — 気配台帳（同じ馬を時系列で記録し、平常値からの変化を捉える）

「走行フォームは単発では能力を予測しにくいが、個々の馬のフォームの“変化”を追えば
有用」(Morrice-West et al. 2021, 25,000頭超) という科学に基づく機能。
馬ごとに歩様指標＋馬体重＋性別＋日付を貯め、その馬の平常値(過去平均)からの
ズレを検出する。＝「いつもよりストライドが伸びている/縮んでいる」を可視化。

使い方:
    # 台帳に1頭追加（歩様CSVにメタ情報を添えて記録）
    python paddock_ledger.py add result/race_uma06_gait_metrics.csv \
        --horse ロードエクレール --date 2026-07-19 --race 高知11R \
        --sex 牡 --weight 482 --wdiff +3 --umaban 6

    # ある馬の履歴と「平常値からの変化」を表示
    python paddock_ledger.py history --horse ロードエクレール

    # 台帳の馬一覧
    python paddock_ledger.py list
    python paddock_ledger.py --selftest

台帳は既定で paddock_ledger.csv（--ledger で変更可）。馬名をキーに蓄積する
（馬番はレース毎に変わるため、時系列の追跡には馬名を使う）。
"""
import argparse, csv, os

# 時系列で追う歩様指標（生値・レースをまたいで比較可能）と、その好ましい向き
TRACK = [
    ("stride_len_norm", "ストライド長", +1),   # 伸び=後肢の踏み込み
    ("stride_freq_hz", "ピッチ(頻度)", 0),
    ("stride_regularity_s", "リズム安定", -1),
    ("head_bob_norm", "頭の上下動", 0),        # メカニカルの指紋。良し悪しは断定しない
    ("topline_stability", "背中の安定", -1),
]
META = ["date", "race", "horse", "sex", "weight", "wdiff", "umaban"]
FIELDS = META + [k for k, _, _ in TRACK] + ["cog_pass_pct", "source"]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_ledger(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_ledger(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def add(args):
    import pandas as pd
    df = pd.read_csv(args.gait_csv)
    if df.empty:
        raise SystemExit("歩様CSVが空です")
    m = df.iloc[0].to_dict()
    row = {
        "date": args.date or "", "race": args.race or "", "horse": args.horse,
        "sex": args.sex or "", "weight": args.weight or "", "wdiff": args.wdiff or "",
        "umaban": args.umaban or "", "cog_pass_pct": args.cog_pass or "",
        "source": str(m.get("source", os.path.basename(args.gait_csv))),
    }
    for k, _, _ in TRACK:
        row[k] = m.get(k, "")
    rows = load_ledger(args.ledger)
    rows.append(row)
    save_ledger(args.ledger, rows)
    print(f"台帳に記録: {args.horse}（{args.date} {args.race}）→ {args.ledger}（計{len(rows)}件）")


def history(args):
    rows = [r for r in load_ledger(args.ledger) if r.get("horse") == args.horse]
    if not rows:
        raise SystemExit(f"『{args.horse}』の記録がありません（台帳: {args.ledger}）")
    rows.sort(key=lambda r: (r.get("date", ""), r.get("race", "")))
    print(f"\n=== 気配台帳: {args.horse}（{len(rows)}走分） ===")
    for i, r in enumerate(rows):
        w = f"{r.get('weight','?')}kg" + (f"({r.get('wdiff')})" if r.get("wdiff") else "")
        head = f"[{i+1}] {r.get('date','?')} {r.get('race','')}  {r.get('sex','')} {w}"
        print("\n" + head)
        for k, name, direction in TRACK:
            v = _num(r.get(k))
            if v is None:
                print(f"    {name:12s}:   -"); continue
            # 過去（今回より前）の平均を平常値とする
            past = [_num(p.get(k)) for p in rows[:i]]
            past = [x for x in past if x is not None]
            mark = ""
            if past:
                base = sum(past) / len(past)
                d = v - base
                arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
                # 好ましい向きに動いたか（direction!=0のとき）
                good = ""
                if direction != 0:
                    good = " ◎" if (d * direction > 0 and abs(d) > 0.02) else (
                        " ▲" if (d * direction < 0 and abs(d) > 0.02) else "")
                mark = f"  平常{base:.3f} {arrow}{d:+.3f}{good}"
            print(f"    {name:12s}: {v:.3f}{mark}")
    print("\n◎=いつもより好ましい向き / ▲=好ましくない向き（|変化|>0.02）")
    print("※ 相対比較・参考です。単発でなく“変化”を見るのが科学的に有効（Morrice-West 2021）。")


def list_horses(args):
    rows = load_ledger(args.ledger)
    if not rows:
        print(f"台帳が空です: {args.ledger}"); return
    from collections import Counter
    c = Counter(r.get("horse", "?") for r in rows)
    print(f"=== 台帳の馬一覧（{args.ledger}・計{len(rows)}件） ===")
    for horse, n in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  {horse}: {n}走")


def selftest():
    import tempfile, pandas as pd
    d = tempfile.mkdtemp()
    ledger = os.path.join(d, "t.csv")
    for i, sl in enumerate([0.80, 0.90, 1.00]):  # ストライドが伸びていく
        csvp = os.path.join(d, f"g{i}.csv")
        pd.DataFrame([{"stride_len_norm": sl, "stride_freq_hz": 0.9,
                       "stride_regularity_s": 0.1, "head_bob_norm": 0.2,
                       "topline_stability": 0.05, "source": f"v{i}"}]).to_csv(csvp, index=False)
        a = argparse.Namespace(gait_csv=csvp, horse="テスト馬", date=f"2026-07-0{i+1}",
                               race="R", sex="牡", weight="480", wdiff="+2", umaban="1",
                               cog_pass="80", ledger=ledger)
        add(a)
    rows = [r for r in load_ledger(ledger) if r["horse"] == "テスト馬"]
    assert len(rows) == 3, rows
    # 3走目のストライドは過去平均(0.85)より伸びている
    last = _num(rows[-1]["stride_len_norm"]); base = (0.80 + 0.90) / 2
    assert last > base, (last, base)
    print("SELFTEST PASSED (3走を記録し、平常値からの変化を追跡できる)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="paddock_ledger.csv", help="台帳CSVのパス")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    pa = sub.add_parser("add", help="歩様CSV＋メタ情報を台帳に追加")
    pa.add_argument("gait_csv")
    pa.add_argument("--horse", required=True, help="馬名（時系列のキー）")
    pa.add_argument("--date"); pa.add_argument("--race")
    pa.add_argument("--sex"); pa.add_argument("--weight"); pa.add_argument("--wdiff")
    pa.add_argument("--umaban"); pa.add_argument("--cog-pass", dest="cog_pass")

    ph = sub.add_parser("history", help="ある馬の履歴と平常値からの変化を表示")
    ph.add_argument("--horse", required=True)

    sub.add_parser("list", help="台帳の馬一覧")

    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if args.cmd == "add":
        add(args)
    elif args.cmd == "history":
        history(args)
    elif args.cmd == "list":
        list_horses(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
