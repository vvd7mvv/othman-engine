"""تطبيع النص العربي للمطابقة فقط؛ لا يُستخدم ناتجه في العرض أبداً."""
import re

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")
_LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ؤ": "و", "ئ": "ي", "ى": "ي", "ة": "ه",
})
_NON_LETTERS = re.compile(r"[^ء-ي ]")


def normalize_word(word: str) -> str:
    word = _DIACRITICS.sub("", word).translate(_LETTER_MAP)
    return _NON_LETTERS.sub("", word)


def normalize_words(text: str) -> list[str]:
    words = (normalize_word(w) for w in text.split())
    return [w for w in words if w]
