# -*- coding: utf-8 -*-
"""
فك ترميز النص العربي المكتوب بخطوط SHX قديمة (SOSA.shx / xarb.shx) في لوحات الديوان.

These drawings store Arabic as LATIN keystrokes of the Arabic (101) keyboard
layout, rendered by legacy SHX fonts (SOSA.shx, xarb.shx).  e.g.
    'l:jF 5'            -> 'مكتب 5'
    'plhL'              -> 'حمام'
    "Hglsr' HBtrD"      -> 'المسقط الافقي'
Lower-case keys map to the standard keyboard letter; upper-case keys are the
same letter's final/isolated glyph in the font (with a few special keys).
Plain English text (e.g. 'IT room', 'E-mail : ...') must NOT be decoded —
use `looks_encoded()` / `decode_if_encoded()`; the reliable signal is the TEXT
STYLE font (SOSA.shx / xarb.shx) — see `is_arabic_style()`.
"""
import re

LOWER = {
    'q': 'ض', 'w': 'ص', 'e': 'ث', 'r': 'ق', 't': 'ف', 'y': 'غ', 'u': 'ع', 'i': 'ه',
    'o': 'خ', 'p': 'ح', '[': 'ج', ']': 'د', 'a': 'ش', 's': 'س', 'd': 'ي', 'f': 'ب',
    'g': 'ل', 'h': 'ا', 'j': 'ت', 'k': 'ن', 'l': 'م', ';': 'ك', "'": 'ط', 'z': 'ئ',
    'x': 'ء', 'c': 'ؤ', 'v': 'ر', 'b': 'لا', 'n': 'ى', 'm': 'ة', ',': 'و', '.': 'ز',
    '/': 'ظ', '`': 'ذ',
}
# upper-case / shifted keys = final or isolated glyph forms (verified on the
# Diwan title blocks & room names; '?' marks are best guesses, see README)
UPPER = {
    'Q': 'ض', 'W': 'ص', 'E': 'ث', 'R': 'ق', 'T': 'ف', 'Y': 'غ', 'U': 'ع', 'I': 'ة',
    'O': 'خ', 'P': 'ح', '{': 'ج', '}': 'د', 'A': 'ش', 'S': 'س', 'D': 'ي', 'F': 'ب',
    'G': 'ل', 'H': 'ا', 'J': 'ت', 'K': 'ن', 'L': 'م', ':': 'ك', '"': 'ط', 'Z': 'ئ',
    'X': 'ء', 'C': 'ؤ', 'V': 'ر', 'B': 'لا', 'N': 'ى', 'M': 'ة', '<': 'و', '>': 'ز',
    '?': 'ظ', '~': 'ذ',
}
TABLE = {**LOWER, **UPPER}

ARABIC_FONTS = ('sosa', 'xarb', 'arab', 'simpo')


def is_arabic_style(doc, style_name: str) -> bool:
    """True if the text style's SHX/TTF font is one of the keyboard-encoded Arabic fonts."""
    try:
        st = doc.styles.get(style_name)
        font = (st.dxf.font or '').lower()
    except Exception:
        return False
    return any(k in font for k in ('sosa', 'xarb'))


def decode(s: str) -> str:
    """Map every keyboard char to its Arabic letter; digits, spaces, + - . ( ) kept."""
    out = []
    n = len(s)
    for i, ch in enumerate(s):
        if ch in '0123456789 +-()%#*\t' or '\u0600' <= ch <= '\u06ff':
            out.append(ch)
        elif ch in '.,/' and 0 < i < n - 1 and s[i - 1].isdigit() and s[i + 1].isdigit():
            out.append(ch)          # decimal point inside a number (e.g. +12.10)
        else:
            out.append(TABLE.get(ch, ch))
    return ''.join(out)


_ENGLISH_WORDS = re.compile(r'\b(room|mail|tel|update|waiting|for|the|it|ftr|das|gsm|electric|lift|stair|wc|shaft)\b', re.I)


def looks_encoded(s: str) -> bool:
    """Heuristic when the style is unknown: real English words → not encoded."""
    if not re.search(r'[A-Za-z\[\];\',`]', s):
        return False
    if _ENGLISH_WORDS.search(s) or '@' in s:
        return False
    return True


def decode_if_encoded(s: str, doc=None, style=None) -> str:
    if doc is not None and style is not None:
        return decode(s) if is_arabic_style(doc, style) else s
    return decode(s) if looks_encoded(s) else s


if __name__ == '__main__':
    import sys
    for a in sys.argv[1:]:
        print(a, '->', decode(a))
