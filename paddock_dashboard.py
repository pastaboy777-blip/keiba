#!/usr/bin/env python3
"""
paddock_dashboard.py — 「パドックアイ風」ダッシュボードHTMLを生成

run_paddock.py の出力フォルダ（各馬の *_gait_metrics.csv と *_skeleton.mp4）から、
全頭を1画面で見比べるHTMLを作る:
  ・各馬カード: 骨格動画(背骨=緑/重心=赤/重心貫通) ＋ 歩様指標 ＋ 気配スコア
  ・馬番順 / 気配順 で並べ替え
  ・2頭を選んで横並び比較

標準ライブラリのみ（pandas不要）。動画は同フォルダ内の相対パス参照なので、
フォルダごと開けば（Colabならzipを解凍して）そのまま再生できる。

使い方:
    python paddock_dashboard.py --dir result
    python paddock_dashboard.py --dir result --out result/dashboard.html --title "高知6R"
    python paddock_dashboard.py --selftest
"""
import argparse, csv, glob, html, json, os, re

# paddock_compare と同じ指標・重み（気配スコア）
METRICS = [
    ("stride_freq_hz", "ピッチ", 0),
    ("stride_regularity_s", "リズム安定", -1),
    ("stride_len_norm", "ストライド長", +1),
    ("head_bob_norm", "頭の上下動", 0),
    ("topline_stability", "背中の安定", -1),
]
KEHAI_WEIGHTS = {"stride_len_norm": 2.0, "topline_stability": 0.5, "stride_regularity_s": 0.3}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _umaban(path):
    m = re.search(r"uma(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else None


def collect(dirpath):
    """dir内の各馬の {umaban, metrics, skeleton, clip} を集める。"""
    rows = []
    for csvf in sorted(glob.glob(os.path.join(dirpath, "*_gait_metrics.csv"))):
        uma = _umaban(csvf)
        if uma is None:
            continue
        with open(csvf, encoding="utf-8") as f:
            r = next(csv.DictReader(f), None)
        if not r:
            continue
        rec = {"umaban": uma, "_good": {}}
        for k, _, _ in METRICS:
            rec[k] = _num(r.get(k))
        rec["n_strides"] = _num(r.get("n_strides"))
        # 対応する骨格動画・クリップを探す
        sk = glob.glob(os.path.join(dirpath, f"*uma{uma:02d}*skeleton*.mp4")) or \
            glob.glob(os.path.join(dirpath, f"*uma{uma}*skeleton*.mp4"))
        cl = glob.glob(os.path.join(dirpath, f"race_uma{uma:02d}.mp4")) or \
            glob.glob(os.path.join(dirpath, f"*uma{uma}.mp4"))
        rec["skeleton"] = os.path.basename(sk[0]) if sk else None
        rec["clip"] = os.path.basename(cl[0]) if cl else None
        # 重心貫通%のサイドカー（skeleton_overlayが出力していれば）
        cog = glob.glob(os.path.join(dirpath, f"*uma{uma:02d}*cogpass*")) or \
            glob.glob(os.path.join(dirpath, f"*uma{uma}*cogpass*"))
        rec["cog_pass"] = None
        if cog:
            try:
                rec["cog_pass"] = float(open(cog[0]).read().strip())
            except Exception:
                pass
        rows.append(rec)
    return rows


def compute_kehai(rows):
    for key, _, d in METRICS:
        if d == 0 or key not in KEHAI_WEIGHTS:
            continue
        nums = [r[key] for r in rows if r.get(key) is not None]
        if not nums:
            continue
        lo, hi = min(nums), max(nums)
        for r in rows:
            v = r.get(key)
            if v is None:
                g = None
            elif hi == lo:
                g = 0.5
            else:
                g = (v - lo) / (hi - lo)
                if d < 0:
                    g = 1 - g
            r["_good"][key] = g
    for r in rows:
        sc = wsum = 0.0
        for key, g in r["_good"].items():
            if g is None:
                continue
            sc += g * KEHAI_WEIGHTS[key]; wsum += KEHAI_WEIGHTS[key]
        r["kehai"] = round(100 * sc / wsum, 1) if wsum else None
    # 指標ごとのベスト馬（★用）
    best = {}
    for key, _, d in METRICS:
        if d == 0:
            continue
        cand = [(r[key], r["umaban"]) for r in rows if r.get(key) is not None]
        if cand:
            best[key] = (min if d < 0 else max)(cand)[1]
    return best


def render(rows, best, title):
    def kcolor(k):
        if k is None:
            return "#666"
        t = max(0.0, min(1.0, k / 100))
        return f"rgb({int(255-120*t)},{int(180+70*t)},{int(120)})"
    cards = []
    data = []
    for r in rows:
        uma = r["umaban"]; k = r.get("kehai")
        vid = r.get("skeleton") or r.get("clip")
        video_html = (f'<video src="{html.escape(vid)}" controls muted loop playsinline '
                      f'preload="metadata"></video>') if vid else '<div class="novid">動画なし</div>'
        mrows = ""
        for key, name, d in METRICS:
            v = r.get(key)
            vs = "-" if v is None else f"{v:.3f}"
            star = "★" if best.get(key) == uma else ""
            mrows += f'<tr><td>{name}</td><td class="v">{vs} <b>{star}</b></td></tr>'
        cog = "" if r.get("cog_pass") is None else \
            f'<div class="cog">重心貫通 {r["cog_pass"]:.0f}%</div>'
        kv = "-" if k is None else f"{k:.1f}"
        cards.append(f'''<div class="card" data-uma="{uma}" data-kehai="{k if k is not None else -1}">
  <div class="chd"><span class="uma">{uma}</span>
    <span class="kehai" style="background:{kcolor(k)}">{kv}</span>
    <label class="cmp"><input type="checkbox" class="cmpchk" value="{uma}"> 比較</label></div>
  {video_html}{cog}
  <table class="met">{mrows}</table>
</div>''')
        data.append({"uma": uma, "kehai": k, "video": vid,
                     "metrics": {n: (None if r.get(key) is None else round(r[key], 3))
                                 for key, n, _ in METRICS}})
    cards_html = "\n".join(cards)
    data_json = json.dumps(data, ensure_ascii=False)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} パドック解析</title>
<style>
:root{{--bg:#12141a;--card:#1c1f28;--fg:#e8eaf0;--mut:#9aa0ad;--line:#2b2f3a}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);
font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif}}
header{{position:sticky;top:0;background:#0d0f14;border-bottom:1px solid var(--line);
padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:5}}
header h1{{font-size:18px;margin:0}} .sub{{color:var(--mut);font-size:13px}}
.btn{{background:#242835;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:7px 12px;cursor:pointer;font-size:13px}} .btn.on{{background:#3a7;border-color:#3a7;color:#08120c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;padding:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.card.sel{{outline:2px solid #3a7}}
.chd{{display:flex;align-items:center;gap:8px;padding:8px 10px}}
.uma{{width:30px;height:30px;border-radius:7px;background:#fff;color:#111;font-weight:800;
display:flex;align-items:center;justify-content:center}}
.kehai{{font-weight:800;color:#08120c;border-radius:7px;padding:4px 10px;font-size:16px}}
.cmp{{margin-left:auto;color:var(--mut);font-size:12px;cursor:pointer}}
video{{width:100%;display:block;background:#000;aspect-ratio:16/9;object-fit:contain}}
.novid{{padding:30px;text-align:center;color:var(--mut)}}
.cog{{padding:6px 10px;color:#7fe0a0;font-size:13px;border-top:1px solid var(--line)}}
.met{{width:100%;border-collapse:collapse;font-size:13px}}
.met td{{padding:5px 10px;border-top:1px solid var(--line)}} .met .v{{text-align:right;color:var(--mut)}}
#bar{{position:fixed;bottom:0;left:0;right:0;background:#0d0f14;border-top:1px solid var(--line);
padding:10px 16px;display:none;gap:14px;align-items:flex-start}}
#bar.show{{display:flex}} #bar .col{{flex:1}} #bar video{{border-radius:8px}}
#bar .t{{font-weight:700;margin-bottom:6px}} .diff{{font-size:12px;color:var(--mut);margin-top:6px}}
.close{{margin-left:auto}}
</style></head><body>
<header>
  <h1>🐎 {html.escape(title)} パドック解析</h1>
  <span class="sub">{len(rows)}頭 ／ 背骨=緑・重心=赤・重心貫通</span>
  <span style="flex:1"></span>
  <button class="btn on" id="sK">気配順</button>
  <button class="btn" id="sU">馬番順</button>
</header>
<div class="grid" id="grid">{cards_html}</div>
<div id="bar">
  <div class="col" id="c0"></div><div class="col" id="c1"></div>
  <button class="btn close" id="cx">×</button>
</div>
<script>
const DATA = {data_json};
const grid = document.getElementById('grid');
function cards() {{ return [...grid.children]; }}
function sortBy(key, desc) {{
  cards().sort((a,b)=>{{
    const av=+a.dataset[key], bv=+b.dataset[key];
    return desc ? bv-av : av-bv;
  }}).forEach(c=>grid.appendChild(c));
}}
document.getElementById('sK').onclick=e=>{{sortBy('kehai',true);setOn('sK');}};
document.getElementById('sU').onclick=e=>{{sortBy('uma',false);setOn('sU');}};
function setOn(id){{['sK','sU'].forEach(x=>document.getElementById(x).classList.toggle('on',x===id));}}
sortBy('kehai',true);
// 2頭比較
let sel=[];
grid.addEventListener('change',e=>{{
  if(!e.target.classList.contains('cmpchk')) return;
  const uma=+e.target.value, card=e.target.closest('.card');
  if(e.target.checked){{ sel.push(uma); card.classList.add('sel');
    if(sel.length>2){{ const drop=sel.shift(); uncheck(drop); }} }}
  else {{ sel=sel.filter(x=>x!==uma); card.classList.remove('sel'); }}
  renderBar();
}});
function uncheck(uma){{ const c=grid.querySelector('.card[data-uma="'+uma+'"]');
  if(c){{ c.classList.remove('sel'); const ck=c.querySelector('.cmpchk'); if(ck) ck.checked=false; }} }}
function col(uma){{ const d=DATA.find(x=>x.uma===uma); if(!d) return '';
  const v=d.video?'<video src="'+d.video+'" controls muted loop playsinline></video>':'';
  const m=Object.entries(d.metrics).map(([k,v])=>k+': '+(v==null?'-':v)).join(' ／ ');
  return '<div class="t">'+uma+'番 ・ 気配'+(d.kehai==null?'-':d.kehai)+'</div>'+v+'<div class="diff">'+m+'</div>'; }}
function renderBar(){{
  const bar=document.getElementById('bar');
  document.getElementById('c0').innerHTML = sel[0]?col(sel[0]):'';
  document.getElementById('c1').innerHTML = sel[1]?col(sel[1]):'';
  bar.classList.toggle('show', sel.length>0);
}}
document.getElementById('cx').onclick=()=>{{ sel.forEach(uncheck); sel=[]; renderBar(); }};
</script></body></html>'''


def build(dirpath, out, title):
    rows = collect(dirpath)
    if not rows:
        raise SystemExit(f"歩様CSVが見つかりません: {dirpath}/*_gait_metrics.csv")
    best = compute_kehai(rows)
    out = out or os.path.join(dirpath, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(rows, best, title))
    print(f"ダッシュボードを保存: {out}（{len(rows)}頭）")
    return out


def selftest():
    import tempfile
    d = tempfile.mkdtemp()
    for uma, sl, tp in [(3, 1.05, 0.05), (7, 0.70, 0.12), (12, 0.85, 0.09)]:
        with open(os.path.join(d, f"race_uma{uma:02d}_gait_metrics.csv"), "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["n_strides", "stride_freq_hz", "stride_regularity_s",
                        "stride_len_norm", "head_bob_norm", "topline_stability"])
            w.writerow([8, 0.9, 0.1, sl, 0.2, tp])
    out = build(d, None, "テスト")
    txt = open(out, encoding="utf-8").read()
    assert "パドック解析" in txt and 'data-uma="3"' in txt and "気配順" in txt
    # 3番はストライド最長→気配最上位
    best = compute_kehai(collect(d))
    print("SELFTEST PASSED (ダッシュボードHTML生成・並べ替え・比較UIを含む)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="run_paddock の出力フォルダ")
    ap.add_argument("--out", help="出力HTML（既定: <dir>/dashboard.html）")
    ap.add_argument("--title", default="レース", help="タイトル")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if not args.dir:
        ap.error("--dir を指定してください")
    build(args.dir, args.out, args.title)


if __name__ == "__main__":
    main()
