# 走っている馬の横向きシルエット（右向き・ギャロップ）。viewBox 0 0 118 78
HORSE = '''<svg class="hv" viewBox="0 0 118 78" width="60" height="40" aria-hidden="true">
 <g fill="{c}">
  <path d="M24 24 C15 15 6 14 1 19 C10 21 16 27 20 34 Z"/>
  <path d="M22 34 C22 25 34 20 50 20 C62 20 70 23 72 28 L70 40 C64 44 50 45 38 43 C28 41 22 39 22 34 Z"/>
  <path d="M64 28 L78 7 L88 13 L74 33 Z"/>
  <path d="M76 5 L92 8 L94 17 L82 18 L72 12 Z"/>
  <path d="M92 10 L106 15 L104 21 L90 19 Z"/>
  <path d="M78 0 L83 8 L73 6 Z"/>
  <path d="M66 39 L84 48 L88 60 L79 57 L60 45 Z"/>
  <path d="M58 41 L60 57 L68 70 L61 74 L51 59 L47 44 Z"/>
  <path d="M32 40 L16 50 L4 56 L8 63 L24 55 L39 45 Z"/>
  <path d="M26 41 L22 56 L13 69 L20 73 L31 59 L35 45 Z"/>
 </g></svg>'''

# 左向きの馬（HORSE を x=59 で鏡にしただけ。viewBox も幅も同じ）。
# 鏡の鞍（大井1600/1800/2000m・川崎2000m）で使う。矢印 CHEV_L と向きを揃えるため。
# ★ HORSE 自体は変えない。zu.py / taretsu_zu.py / kekka_zu.py の出力を動かさないため。
HORSE_L = '''<svg class="hv" viewBox="0 0 118 78" width="60" height="40" aria-hidden="true">
 <g fill="{c}">
  <path d="M94 24 C103 15 112 14 117 19 C108 21 102 27 98 34 Z"/>
  <path d="M96 34 C96 25 84 20 68 20 C56 20 48 23 46 28 L48 40 C54 44 68 45 80 43 C90 41 96 39 96 34 Z"/>
  <path d="M54 28 L40 7 L30 13 L44 33 Z"/>
  <path d="M42 5 L26 8 L24 17 L36 18 L46 12 Z"/>
  <path d="M26 10 L12 15 L14 21 L28 19 Z"/>
  <path d="M40 0 L35 8 L45 6 Z"/>
  <path d="M52 39 L34 48 L30 60 L39 57 L58 45 Z"/>
  <path d="M60 41 L58 57 L50 70 L57 74 L67 59 L71 44 Z"/>
  <path d="M86 40 L102 50 L114 56 L110 63 L94 55 L79 45 Z"/>
  <path d="M92 41 L96 56 L105 69 L98 73 L87 59 L83 45 Z"/>
 </g></svg>'''

CHEV = ('<svg class="cv" viewBox="0 0 22 14" width="15" height="10" aria-hidden="true">'
        '<g fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round">'
        '<path d="M2 3 L7 7 L2 11"/><path d="M10 3 L15 7 L10 11"/></g></svg>')

# 左向きの矢印（CHEV を x=11 で鏡にしただけ）。鏡の鞍（大井1600/1800/2000m・川崎2000m）で使う。
# ★ CHEV 自体は変えない。zu.py / taretsu_zu.py / kekka_zu.py の出力を動かさないため。
CHEV_L = ('<svg class="cv" viewBox="0 0 22 14" width="15" height="10" aria-hidden="true">'
          '<g fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round">'
          '<path d="M20 3 L15 7 L20 11"/><path d="M12 3 L7 7 L12 11"/></g></svg>')
