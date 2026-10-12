"""اختبارات المطابقة بكلمات مصطنعة من نص المصحف، بدون موديل التفريغ."""
from othman_engine import alignment, quran
from othman_engine.asr.base import Word
from othman_engine.match import match_words
from othman_engine.normalize import normalize_word


def ayah_words(surah, ayah, first=0, last=None):
    # علامات الوقف (ۖ ۚ ...) مكتوبة في النص ككلمات مستقلة، ولا تُنطق
    words = [w for w in quran.simple_text()[surah, ayah].split() if normalize_word(w)] if ayah else quran.BASMALA.split()
    return words[first:last]


def recite(*parts):
    """كل جزء: (سورة، آية) أو (سورة، آية، من كلمة، إلى كلمة) أو نص حر غير قرآني."""
    texts = []
    for part in parts:
        texts += part.split() if isinstance(part, str) else ayah_words(*part)
    return [Word(text, i * 0.5, i * 0.5 + 0.4) for i, text in enumerate(texts)]


def segments(words):
    result = alignment.build(words, match_words(words), duration=len(words) * 0.5)
    return [(s.surah, s.ayah) for s in result.segments], result


def test_consecutive_ayahs():
    got, result = segments(recite(*[(67, a) for a in range(1, 6)]))
    assert got == [(67, a) for a in range(1, 6)]
    assert all(s.confidence == 1.0 for s in result.segments)


def test_istiadha_and_closing_speech_are_ignored():
    words = recite("أعوذ بالله من الشيطان الرجيم", (85, 12), (85, 13), "صدق الله العظيم")
    got, _ = segments(words)
    assert got == [(85, 12), (85, 13)]


def test_repeating_previous_ayah():
    got, _ = segments(recite((1, 2), (1, 3), (1, 4), (1, 3), (1, 4), (1, 5)))
    assert got == [(1, 2), (1, 3), (1, 4), (1, 3), (1, 4), (1, 5)]


def test_waqf_and_ibtida_stays_in_one_segment():
    # القارئ يقف في منتصف آية الكرسي ثم يعيد من كلمات سابقة
    got, _ = segments(recite((2, 255, 0, 12), (2, 255, 8, None), (2, 256)))
    assert got == [(2, 255), (2, 256)]


def test_similar_ayahs_resolved_by_context():
    # "فبأي آلاء ربكما تكذبان" تتكرر 31 مرة في سورة الرحمن
    got, _ = segments(recite(*[(55, a) for a in range(20, 27)]))
    assert got == [(55, a) for a in range(20, 27)]


def test_crossing_surahs_with_basmala():
    got, _ = segments(recite((18, 109), (18, 110), (19, 0), (19, 1), (19, 2)))
    assert got == [(18, 109), (18, 110), (19, 0), (19, 1), (19, 2)]


def test_transcription_errors_are_tolerated():
    words = recite((36, 1), (36, 2), (36, 3), (36, 4))
    words[5] = Word("المرسلن", words[5].start, words[5].end)
    got, _ = segments(words)
    assert got == [(36, 1), (36, 2), (36, 3), (36, 4)]


def test_non_quran_speech_has_low_matched_ratio():
    _, result = segments(recite("السلام عليكم ورحمة الله وبركاته كيف حالكم اليوم إن شاء الله بخير"))
    assert result.matched_ratio < 0.5


def test_common_phrase_at_ayah_boundary_does_not_break_the_chain():
    # "من دون الله" شائعة جداً فتُتجاهل ثلاثياتها؛ كانت تقسم غافر 69-77 فتقفز المطابقة لآية 35
    got, _ = segments(recite(*[(40, a) for a in range(69, 78)]))
    assert got == [(40, a) for a in range(69, 78)]


def test_single_misheard_word_keeps_one_run():
    words = recite((67, 1), (67, 2))
    words[4] = Word("قدر", words[4].start, words[4].end)
    got, _ = segments(words)
    assert got == [(67, 1), (67, 2)]


def test_opening_letters_as_their_own_ayah():
    # كما كتبها الموديل فعلاً: الحرف الممدود مقطّع ومكرر، و"حم" خطأ في الميم الممدودة
    got, result = segments(recite("أعوذ بالله من الشيطان الرجيم الم الم حم", (32, 2), (32, 3)))
    assert got == [(32, 1), (32, 2), (32, 3)]
    assert len(result.segments[0].words) == 3


def test_opening_letters_split_into_pieces():
    got, _ = segments(recite("الم الم ص ص", (7, 2), (7, 3)))
    assert got == [(7, 1), (7, 2), (7, 3)]


def test_two_opening_letter_ayahs():
    got, _ = segments(recite("حم عسق", (42, 3), (42, 4)))
    assert got == [(42, 1), (42, 2), (42, 3), (42, 4)]


def test_letters_inside_a_longer_ayah():
    got, _ = segments(recite("الر الر", (10, 1, 1, None), (10, 2)))
    assert got == [(10, 1), (10, 2)]


def test_istiadha_does_not_reach_a_normal_previous_ayah():
    got, _ = segments(recite("أعوذ بالله من الشيطان الرجيم", (67, 3), (67, 4)))
    assert got == [(67, 3), (67, 4)]


def test_repeating_the_whole_ayah_is_a_new_reading():
    got, _ = segments(recite((7, 5), (7, 5), (7, 6)))
    assert got == [(7, 5), (7, 5), (7, 6)]
