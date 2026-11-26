import re, os, sys
import monogatari as M
rid = sys.argv[1]
h = open(os.path.join(M.ARC, f"sei_{rid}.html"), encoding="utf-8", errors="replace").read()
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
avg = re.search(r"平均ハロン\s*([\d.]+)", t)
md = re.search(r"発走\s*[\d:]+\s*(.*?)\s*(\d{3,4})m", t)
print("■", (md.group(1).strip()+" "+md.group(2)+"m") if md else "?", "｜平均ハロン", avg.group(1) if avg else "?")
rows = []
for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
    row = m.group(1)
    if 'class="umaban"' not in row: continue
    tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
    if len(tds) < 14 or not re.match(r"^\d+$", tds[0]): continue
    chaku = int(tds[0]); ub = int(re.search(r'class="umaban">(\d+)', row).group(1))
    tuka = next((x for x in tds if re.match(r"^\d+( +\d+)+$", x)), None)
    c1 = int(tuka.split()[0]) if tuka else None
    ti = next((i for i, x in enumerate(tds) if re.match(r"^\d\.\d\d\.\d$", x)), None)  # タイム位置
    zen3 = None
    if ti is not None:
        after = [x for x in tds[ti+1:] if re.match(r"^\d{2}\.\d$", x)]
        if after: zen3 = after[0]  # タイム後の最初のXX.X = 前半3F
    rows.append((chaku, ub, c1, zen3))
# 勝ち馬タイム→秒
wt = re.search(r"(\d)\.(\d\d)\.(\d)\b", t)
wsec = None
mrun = re.search(r"class=\"umaban\">(\d+).*?(\d)\.(\d\d)\.(\d)", h, re.S)
for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
    if 'class="umaban"' not in m.group(1): continue
    tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
    if tds and tds[0] == "1":
        tm = next((x for x in tds if re.match(r"^\d\.\d\d\.\d$", x)), None)
        if tm:
            a, b, c = tm.split("."); wsec = int(a)*60 + int(b) + int(c)/10
        break
print("上位3着（1角位置 / 上がり3F）:")
for r in sorted(rows)[:3]:
    print(f"  {r[0]}着 {r[1]}番 1角{r[2]} 上がり3F{r[3]}")
z = [float(r[3]) for r in rows if r[3]]
win_ag = next((float(r[3]) for r in sorted(rows) if r[3]), None)
if wsec and win_ag:
    zen3 = wsec - win_ag
    keisha = win_ag - zen3
    kind = "前傾（前半速い→差し有利）" if keisha > 1.0 else "後傾（前半遅い→前有利）" if keisha < -1.0 else "平坦"
    print(f"勝ち馬タイム{wsec:.1f}s ｜ 前半3F≈{zen3:.1f} - 上がり3F{win_ag} → 前傾度{keisha:+.1f}秒 = 【{kind}】")
if z: print(f"上がり3F 最速{min(z)}（最も切れた） / 最遅{max(z)}")
