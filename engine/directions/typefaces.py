"""The Google Fonts families directions may pair, with what the engine needs to load and judge them.

`AXES` is merged into `engine/compile/themes.py` FONT_AXES, so a picked direction's fonts load with the right css2
axis spec (every spec here was checked against fonts.googleapis.com; the engine's fallback `wght@400;700` is a 400 for
families that have one weight). `CLASS` says what kind of face it is: the diversity check compares directions by it,
and the board writes it under the specimen.
"""
from __future__ import annotations

# family -> (class, css2 axes, has an italic, one weight only)
_F = {
    # serifs: old style / transitional / modern / slab / display
    "Cormorant Garamond": ("serif-old", "ital,wght@0,300..700;1,300..700", True, False),
    "Cormorant": ("serif-old", "ital,wght@0,300..700;1,300..700", True, False),
    "EB Garamond": ("serif-old", "ital,wght@0,400..800;1,400..800", True, False),
    "Libre Baskerville": ("serif-old", "ital,wght@0,400..700;1,400", True, False),
    "Lora": ("serif-text", "ital,wght@0,400..700;1,400..700", True, False),
    "Crimson Pro": ("serif-old", "ital,wght@0,200..900;1,200..900", True, False),
    "Source Serif 4": ("serif-text", "ital,opsz,wght@0,8..60,200..900;1,8..60,200..900", True, False),
    "Literata": ("serif-text", "ital,opsz,wght@0,7..72,200..900;1,7..72,200..900", True, False),
    "Newsreader": ("serif-text", "ital,opsz,wght@0,6..72,200..800;1,6..72,200..800", True, False),
    "Fraunces": ("serif-soft", "ital,opsz,wght@0,9..144,100..900;1,9..144,100..900", True, False),
    "Instrument Serif": ("serif-modern", "ital@0;1", True, True),
    "Playfair Display": ("serif-modern", "ital,wght@0,400..900;1,400..900", True, False),
    "DM Serif Display": ("serif-modern", "ital@0;1", True, True),
    "Bodoni Moda": ("serif-modern", "ital,opsz,wght@0,6..96,400..900;1,6..96,400..900", True, False),
    "Noto Serif Display": ("serif-modern", "ital,wght@0,100..900;1,100..900", True, False),
    "Young Serif": ("serif-soft", "", False, True),
    "Gloock": ("serif-modern", "", False, True),
    "Abril Fatface": ("serif-fat", "", False, True),
    "Rozha One": ("serif-fat", "", False, True),
    "Chonburi": ("serif-fat", "", False, True),
    "Italiana": ("serif-deco", "", False, True),
    "Marcellus": ("serif-deco", "", False, True),
    "Cinzel": ("serif-deco", "wght@400..900", False, False),
    "Shippori Mincho": ("serif-old", "wght@400;500;600;700", False, False),
    "Roboto Slab": ("slab", "wght@100..900", False, False),
    "Zilla Slab": ("slab", "ital,wght@0,300;0,400;0,500;0,600;0,700;1,400", True, False),
    "Bitter": ("slab", "ital,wght@0,100..900;1,100..900", True, False),
    # sans: neo-grotesque / grotesque / geometric / humanist / rounded
    "Inter": ("sans-neo", "ital,opsz,wght@0,14..32,100..900;1,14..32,100..900", True, False),
    "Inter Tight": ("sans-neo", "ital,wght@0,100..900;1,100..900", True, False),
    "Archivo": ("sans-grotesk", "ital,wght@0,100..900;1,100..900", True, False),
    "Familjen Grotesk": ("sans-grotesk", "ital,wght@0,400..700;1,400..700", True, False),
    "Hanken Grotesk": ("sans-neo", "ital,wght@0,100..900;1,100..900", True, False),
    "Schibsted Grotesk": ("sans-grotesk", "ital,wght@0,400..900;1,400..900", True, False),
    "Libre Franklin": ("sans-grotesk", "ital,wght@0,100..900;1,100..900", True, False),
    "Space Grotesk": ("sans-grotesk", "wght@300..700", False, False),
    "Bricolage Grotesque": ("sans-grotesk", "opsz,wght@12..96,200..800", False, False),
    "Instrument Sans": ("sans-neo", "ital,wdth,wght@0,75..100,400..700;1,75..100,400..700", True, False),
    "Public Sans": ("sans-neo", "ital,wght@0,100..900;1,100..900", True, False),
    "Work Sans": ("sans-grotesk", "ital,wght@0,100..900;1,100..900", True, False),
    "Karla": ("sans-grotesk", "ital,wght@0,200..800;1,200..800", True, False),
    "Albert Sans": ("sans-geo", "ital,wght@0,100..900;1,100..900", True, False),
    "DM Sans": ("sans-geo", "ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000", True, False),
    "Manrope": ("sans-geo", "wght@200..800", False, False),
    "Sora": ("sans-geo", "wght@100..800", False, False),
    "Outfit": ("sans-geo", "wght@100..900", False, False),
    "Lexend": ("sans-geo", "wght@100..900", False, False),
    "Figtree": ("sans-geo", "ital,wght@0,300..900;1,300..900", True, False),
    "Onest": ("sans-geo", "wght@100..900", False, False),
    "Epilogue": ("sans-grotesk", "ital,wght@0,100..900;1,100..900", True, False),
    "Red Hat Display": ("sans-geo", "ital,wght@0,300..900;1,300..900", True, False),
    "Montserrat": ("sans-geo", "ital,wght@0,100..900;1,100..900", True, False),
    "Rubik": ("sans-round", "ital,wght@0,300..900;1,300..900", True, False),
    "Nunito": ("sans-round", "ital,wght@0,200..1000;1,200..1000", True, False),
    "Quicksand": ("sans-round", "wght@300..700", False, False),
    "Fredoka": ("sans-round", "wght@300..700", False, False),
    "Barlow": ("sans-neo", "ital,wght@0,300;0,400;0,500;0,600;0,700;1,400", True, False),
    "Barlow Condensed": ("sans-condensed", "ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400", True, False),
    "IBM Plex Sans": ("sans-neo", "ital,wght@0,100..700;1,100..700", True, False),
    "Josefin Sans": ("sans-deco", "ital,wght@0,100..700;1,100..700", True, False),
    "Geologica": ("sans-geo", "wght@100..900", False, False),
    "Gabarito": ("sans-geo", "wght@400..900", False, False),
    "Mona Sans": ("sans-grotesk", "", False, False),
    # display / expressive
    "Syne": ("display-wide", "wght@400..800", False, False),
    "Unbounded": ("display-wide", "wght@200..900", False, False),
    "Anybody": ("display-wide", "wdth,wght@50..150,100..900", False, False),
    "Archivo Black": ("display-heavy", "", False, True),
    "Anton": ("display-heavy", "", False, True),
    "Oswald": ("sans-condensed", "wght@200..700", False, False),
    "Bebas Neue": ("display-heavy", "", False, True),
    "League Gothic": ("display-heavy", "", False, True),
    "Big Shoulders Display": ("sans-condensed", "wght@300..900", False, False),
    "Dela Gothic One": ("display-heavy", "", False, True),
    "Rubik Mono One": ("display-heavy", "", False, True),
    "Shrikhand": ("display-fun", "", False, True),
    "Bungee": ("display-fun", "", False, True),
    "Righteous": ("display-fun", "", False, True),
    "Monoton": ("display-fun", "", False, True),
    "Limelight": ("serif-deco", "", False, True),
    "Poiret One": ("sans-deco", "", False, True),
    "Press Start 2P": ("pixel", "", False, True),
    "Pixelify Sans": ("pixel", "wght@400..700", False, False),
    "Silkscreen": ("pixel", "wght@400;700", False, False),
    "VT323": ("pixel", "", False, True),
    "UnifrakturMaguntia": ("blackletter", "", False, True),
    "Caveat": ("hand", "wght@400..700", False, False),
    "Permanent Marker": ("hand", "", False, True),
    "Special Elite": ("typewriter", "", False, True),
    # monospaces
    "IBM Plex Mono": ("mono", "ital,wght@0,400;0,500;1,400", True, False),
    "JetBrains Mono": ("mono", "wght@100..800", False, False),
    "Space Mono": ("mono", "ital,wght@0,400;0,700;1,400", True, False),
    "DM Mono": ("mono", "ital,wght@0,300;0,400;0,500;1,400", True, False),
    "Courier Prime": ("mono", "ital,wght@0,400;0,700;1,400;1,700", True, False),
    "Martian Mono": ("mono", "wght@100..800", False, False),
    "Azeret Mono": ("mono", "wght@100..900", False, False),
    "Cutive Mono": ("mono", "", False, True),
}

CLASS = {fam: v[0] for fam, v in _F.items()}
AXES = {fam: v[1] for fam, v in _F.items()}
ITALIC = {fam for fam, v in _F.items() if v[2]}
SINGLE_WEIGHT = {fam for fam, v in _F.items() if v[3]}

# what a class reads as, for the specimen caption on the board
CLASS_LABEL = {
    "serif-old": "old-style serif", "serif-text": "text serif", "serif-soft": "soft serif", "serif-modern": "high-contrast serif",
    "serif-fat": "fat-face serif", "serif-deco": "deco capitals", "slab": "slab serif", "sans-neo": "neo-grotesque",
    "sans-grotesk": "grotesque", "sans-geo": "geometric sans", "sans-round": "rounded sans", "sans-condensed": "condensed sans",
    "sans-deco": "deco sans", "display-wide": "wide display", "display-heavy": "heavy display", "display-fun": "fun display",
    "pixel": "pixel face", "blackletter": "blackletter", "hand": "handwriting", "typewriter": "typewriter", "mono": "monospace",
}
# classes that sit close together, for the diversity check (serif-old ~ serif-text ...)
FAMILY = {
    "serif-old": "serif", "serif-text": "serif", "serif-soft": "serif", "serif-modern": "serif-display",
    "serif-fat": "serif-display", "serif-deco": "deco", "slab": "slab", "sans-neo": "sans", "sans-grotesk": "sans",
    "sans-geo": "sans-geo", "sans-round": "round", "sans-condensed": "condensed", "sans-deco": "deco",
    "display-wide": "wide", "display-heavy": "heavy", "display-fun": "fun", "pixel": "pixel", "blackletter": "black",
    "hand": "hand", "typewriter": "mono", "mono": "mono",
}


def family_of(font: str) -> str:
    return FAMILY.get(CLASS.get(font, "sans-neo"), "sans")
