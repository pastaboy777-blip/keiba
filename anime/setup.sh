#!/usr/bin/env bash
# Installs python deps + builds Japanese fonts (Noto Sans/Serif JP, Dela Gothic One) from npm @fontsource packages.
set -e
cd "$(dirname "$0")"
pip install -q numpy scipy pillow pycairo imageio-ffmpeg fonttools brotli soundfile
python3 tools/build_fonts.py
mkdir -p ~/.fonts && cp fonts/*.ttf ~/.fonts/ && fc-cache -f
