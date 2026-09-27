"""Global settings for 「最後の一完歩」 (The Last Stride)."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")
W, H = 1920, 1080
FPS = 24
DURATION = 60.0
AUDIO_SR = 48000

# Fonts (installed to ~/.fonts by setup.sh; family names are renamed copies of Noto / Dela Gothic)
FONT_SANS = "AnimeSans"      # Noto Sans JP Bold
FONT_SANS_M = "AnimeSansM"   # Noto Sans JP Medium
FONT_SERIF = "AnimeSerif"    # Noto Serif JP Black
FONT_IMPACT = "AnimeDela"    # Dela Gothic One (manga SFX / announcer impact text)

# Shared palette (0..1 RGB). Use these so all scenes feel like one film.
PAL = {
    "night_top":   (0.02, 0.03, 0.10),
    "night_mid":   (0.07, 0.08, 0.24),
    "night_low":   (0.28, 0.14, 0.34),   # city glow on horizon
    "track_dirt":  (0.36, 0.26, 0.20),   # 大井 dirt under floodlights
    "track_dirt_hi": (0.62, 0.48, 0.36),
    "rail_white":  (0.95, 0.95, 0.98),
    "lamp_warm":   (1.00, 0.78, 0.45),
    "light_cool":  (0.75, 0.88, 1.00),
    "neon_cyan":   (0.25, 0.95, 1.00),   # AI HUD colour
    "neon_pink":   (1.00, 0.30, 0.55),
    "harukaze":    (0.78, 0.38, 0.16),   # chestnut coat (栗毛)
    "harukaze_mane": (0.95, 0.72, 0.42), # flaxen mane / tail
    "silk_main":   (0.93, 0.93, 0.96),   # Mizuki's silks: white body
    "silk_accent": (0.90, 0.12, 0.22),   # red sash + red cap with white star
    "mizuki_hair": (0.12, 0.10, 0.16),
    "skin":        (1.00, 0.86, 0.76),
    "skin_shadow": (0.90, 0.66, 0.60),
    "ink":         (0.06, 0.05, 0.10),   # line art colour
}
