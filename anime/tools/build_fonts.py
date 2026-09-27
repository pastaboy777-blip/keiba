"""Download @fontsource packages via npm, merge unicode-range woff2 subsets into single TTFs, rename families."""
import glob, os, re, subprocess, tempfile
from fontTools.ttLib import TTFont
from fontTools.merge import Merger
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "fonts")
SPECS = [("@fontsource/noto-sans-jp", "noto-sans-jp", 700, "NotoSansJP-Bold.ttf", "AnimeSans"),
         ("@fontsource/noto-sans-jp", "noto-sans-jp", 500, "NotoSansJP-Medium.ttf", "AnimeSansM"),
         ("@fontsource/noto-serif-jp", "noto-serif-jp", 900, "NotoSerifJP-Black.ttf", "AnimeSerif"),
         ("@fontsource/dela-gothic-one", "dela-gothic-one", 400, "DelaGothicOne.ttf", "AnimeDela")]
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp()
for pkg, prefix, wt, out, fam in SPECS:
    if os.path.exists(os.path.join(OUT, out)): continue
    tgz = subprocess.check_output(["npm", "pack", pkg, "--silent"], cwd=tmp, text=True).strip().splitlines()[-1]
    d = os.path.join(tmp, prefix); os.makedirs(d, exist_ok=True)
    subprocess.check_call(["tar", "xzf", os.path.join(tmp, tgz), "-C", d])
    files = [f for f in glob.glob(f"{d}/package/files/{prefix}-*-{wt}-normal.woff2") if re.search(rf"-\d+-{wt}-", f)]
    parts = []
    for i, f in enumerate(files):
        t = TTFont(f); t.flavor = None; p = os.path.join(tmp, f"{prefix}_{wt}_{i}.ttf"); t.save(p); parts.append(p)
    font = Merger().merge(parts); n = font["name"]
    for r in list(n.names):
        if r.nameID in (1, 4, 6, 16, 21): n.setName(fam, r.nameID, r.platformID, r.platEncID, r.langID)
        if r.nameID in (2, 17, 22): n.setName("Regular", r.nameID, r.platformID, r.platEncID, r.langID)
    font["OS/2"].usWeightClass = 400
    font.save(os.path.join(OUT, out)); print(out)
