"""نصوص المصحف وبيانات السور.

نص Tanzil الإملائي للمطابقة. الناتج برقم السورة والآية، فيمكن ربطه بأي نص للعرض (مثل نص مجمع الملك فهد).
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import cache

from othman_engine import config
from othman_engine.normalize import normalize_words

BASMALA = "بسم الله الرحمن الرحيم"
# الآية صفر تمثل البسملة في بداية السور (ما عدا الفاتحة لأنها آية فيها، والتوبة لأنها بلا بسملة)
BASMALA_AYAH = 0


@dataclass(frozen=True)
class Surah:
    number: int
    name_ar: str
    name_en: str
    ayah_count: int


@dataclass(frozen=True)
class QuranWord:
    surah: int
    ayah: int
    index: int  # ترتيب الكلمة داخل الآية
    text: str  # مطبّع


def has_basmala(surah: int) -> bool:
    return surah not in (1, 9)


@cache
def surahs() -> list[Surah]:
    root = ET.parse(config.TANZIL_DIR / "quran-data.xml").getroot()
    return [
        Surah(int(s.get("index")), s.get("name"), s.get("tname"), int(s.get("ayas")))
        for s in root.find("suras")
    ]


@cache
def simple_text() -> dict[tuple[int, int], str]:
    text = {}
    with (config.TANZIL_DIR / "quran-simple-clean.txt").open(encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            surah, ayah, ayah_text = line.rstrip("\n").split("|", 2)
            surah, ayah = int(surah), int(ayah)
            # Tanzil يلصق البسملة بأول آية في كل سورة؛ نفصلها لتصبح الآية صفر
            if ayah == 1 and has_basmala(surah):
                ayah_text = ayah_text.removeprefix(BASMALA).strip()
            text[surah, ayah] = ayah_text
    return text


@cache
def word_stream() -> list[QuranWord]:
    """كل كلمات المصحف بالترتيب، مع البسملة قبل أول آية من كل سورة."""
    words = []
    for surah in surahs():
        if has_basmala(surah.number):
            words += [QuranWord(surah.number, BASMALA_AYAH, i, w) for i, w in enumerate(normalize_words(BASMALA))]
        for ayah in range(1, surah.ayah_count + 1):
            words += [
                QuranWord(surah.number, ayah, i, w)
                for i, w in enumerate(normalize_words(simple_text()[surah.number, ayah]))
            ]
    return words


@cache
def _ayah_spans() -> dict[tuple[int, int], range]:
    spans = {}
    for position, word in enumerate(word_stream()):
        key = word.surah, word.ayah
        spans[key] = range(spans[key].start if key in spans else position, position + 1)
    return spans


def ayah_span(surah: int, ayah: int) -> range:
    """مواقع كلمات الآية في word_stream."""
    return _ayah_spans()[surah, ayah]


def ayah_word_count(surah: int, ayah: int) -> int:
    return len(ayah_span(surah, ayah))


# الحروف المقطعة: أول كلمة في هذه السور (وفي الشورى الآية الثانية "عسق" أيضاً)
MUQATTAAT_SURAHS = (2, 3, 7, 10, 11, 12, 13, 14, 15, 19, 20, 26, 27, 28, 29, 30, 31, 32, 36, 38,
                    40, 41, 42, 43, 44, 45, 46, 50, 68)
# حروفها الأربعة عشر (الحروف النورانية) بعد التطبيع
MUQATTAAT_LETTERS = frozenset("الرمصكهيعطسحقن")


@cache
def muqattaat_positions() -> frozenset[int]:
    """مواقع كلمات الحروف المقطعة في word_stream."""
    keys = [(surah, 1) for surah in MUQATTAAT_SURAHS] + [(42, 2)]
    return frozenset(ayah_span(*key).start for key in keys)


def is_muqattaat_ayah(surah: int, ayah: int) -> bool:
    """آية كاملة من الحروف المقطعة وحدها (مثل "الم" و"حم")، لا "الر تلك آيات..."."""
    span = ayah_span(surah, ayah) if (surah, ayah) in _ayah_spans() else range(0)
    return len(span) == 1 and span.start in muqattaat_positions()
