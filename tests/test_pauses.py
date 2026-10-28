import numpy as np

from othman_engine import config
from othman_engine import quran
from othman_engine.alignment import Alignment, Segment
from othman_engine.pauses import add_pauses

SR = config.SAMPLE_RATE
# المائدة 116: يتنفس القارئ بعد "من دون الله ۖ" (كلمة Tanzil رقم 15)
SURAH, AYAH, BREATH_AFTER = 5, 116, 15


def _recitation(loud_spans, duration, echo=0.05):
    """ضوضاء بمستوى ثابت في فترات القراءة، وصدى خافت في غيرها (مثل المسجد)."""
    rng = np.random.default_rng(0)
    audio = rng.normal(0, echo, int(duration * SR)).astype(np.float32)
    for a, b in loud_spans:
        audio[int(a * SR) : int(b * SR)] = rng.normal(0, 0.5, int(b * SR) - int(a * SR))
    return audio


def _ayah_words(breath_at=None, breath=1.3):
    count = quran.ayah_word_count(SURAH, AYAH)
    words, t = [], 1.0
    for i in range(count):
        if breath_at is not None and i == breath_at + 1:
            t += breath
        words.append([i, round(t, 2), round(t + 0.3, 2)])
        t += 0.5
    return words


def test_breath_is_found_from_quiet_audio_but_long_madd_is_not():
    words = _ayah_words(BREATH_AFTER)
    breath_start = words[BREATH_AFTER][1] + 0.5
    breath_end = words[BREATH_AFTER + 1][1]
    duration = words[-1][2] + 1
    # الكلمات متصلة بالصوت (المد يملأ ما بينها) إلا وقت النفَس
    audio = _recitation([(words[0][1], breath_start), (breath_end, words[-1][2])], duration)
    alignment = Alignment(duration, 1.0, [Segment(SURAH, AYAH, words[0][1], words[-1][2], 1.0, words)])
    add_pauses(audio, alignment)
    [(start, end)] = alignment.segments[0].pauses
    assert abs(start - breath_start) < 0.1 and abs(end - breath_end) < 0.1


def test_short_stop_inside_a_word_is_not_a_breath():
    words = _ayah_words()
    duration = words[-1][2] + 1
    gap_at = words[10][1] + 0.1
    audio = _recitation([(words[0][1], gap_at), (gap_at + 0.3, words[-1][2])], duration)
    alignment = Alignment(duration, 1.0, [Segment(SURAH, AYAH, words[0][1], words[-1][2], 1.0, words)])
    add_pauses(audio, alignment)
    assert alignment.segments[0].pauses == []


def test_clip_shifts_pauses():
    segment = Segment(SURAH, AYAH, 1.0, 30.0, 1.0, [[0, 1.0, 1.5], [1, 9.0, 9.5]], [[5.0, 6.0]])
    clipped = Alignment(40.0, 1.0, [segment]).clip(2.0, None)
    assert clipped.segments[0].pauses == [[3.0, 4.0]]


def test_opening_letters_start_with_the_sound_not_with_the_transcribed_letter():
    from othman_engine.pauses import extend_opening_letters
    # صمت ثم "أَلِفۡ لَاااام مِيييم" من 1.0 ثانية، والموديل كتب "الم" عند 5.8 فقط
    audio = _recitation([(1.0, 9.8), (10.6, 14.0)], 15.0, echo=0.005)
    alignment = Alignment(15.0, 1.0, [Segment(32, 1, 5.8, 6.9, 1.0, [[0, 5.8, 6.9]]),
                                      Segment(32, 2, 10.6, 14.0, 1.0, [[0, 10.6, 11.0]])])
    extend_opening_letters(audio, alignment)
    assert abs(alignment.segments[0].start - 1.0) < 0.1
    assert alignment.segments[1].start == 10.6  # الآيات العادية لا تتغير


def test_ayah_edges_follow_the_sound_not_the_transcribed_words():
    from othman_engine.pauses import refine_edges
    # الآية الأولى صوتها 1.0–6.0 والموديل كتبها 1.4–5.2 (قطع آخر مد)؛ سكتة ثم الثانية 7.0–10.0 كتبها 7.3–9.5
    audio = _recitation([(1.0, 6.0), (7.0, 10.0)], 12.0, echo=0.02)
    alignment = Alignment(12.0, 1.0, [Segment(97, 1, 1.4, 5.2, 1.0), Segment(97, 2, 7.3, 9.5, 1.0)])
    refine_edges(audio, alignment)
    first, second = alignment.segments
    assert abs(first.start - 1.0) < 0.1 and abs(first.end - 6.0) < 0.1
    assert abs(second.start - 7.0) < 0.1 and abs(second.end - 10.0) < 0.1


def test_ayah_edges_stop_at_the_quietest_point_between_connected_ayahs():
    from othman_engine.pauses import refine_edges
    # قراءة موصولة: هبوط قصير (أقل من 0.3 ثانية) عند 5.0 فقط
    audio = _recitation([(1.0, 5.0), (5.15, 9.0)], 10.0, echo=0.02)
    alignment = Alignment(10.0, 1.0, [Segment(97, 1, 1.0, 4.2, 1.0), Segment(97, 2, 5.8, 9.0, 1.0)])
    refine_edges(audio, alignment)
    first, second = alignment.segments
    assert first.end <= second.start
    assert 4.9 <= first.end <= 5.2 and 4.9 <= second.start <= 5.2


def test_ayah_edges_never_shrink():
    from othman_engine.pauses import refine_edges
    audio = _recitation([(2.0, 4.0)], 6.0, echo=0.02)
    alignment = Alignment(6.0, 1.0, [Segment(97, 1, 1.5, 4.5, 1.0)])
    refine_edges(audio, alignment)
    assert (alignment.segments[0].start, alignment.segments[0].end) == (1.5, 4.5)


def test_digital_silence_at_the_end_of_the_file_is_not_the_room_noise_level():
    from othman_engine.pauses import refine_edges
    audio = _recitation([(1.0, 5.0)], 9.0, echo=0.02)
    audio[int(7.0 * SR):] = 0
    alignment = Alignment(9.0, 1.0, [Segment(97, 1, 1.0, 4.6, 1.0)])
    refine_edges(audio, alignment)
    assert abs(alignment.segments[0].end - 5.0) < 0.1


def test_an_ayah_the_model_did_not_write_takes_the_sound_between_its_neighbours():
    from othman_engine.pauses import fill_missing
    audio = _recitation([(1.0, 3.0), (3.5, 5.0), (5.5, 8.0)], 9.0, echo=0.02)
    alignment = Alignment(9.0, 1.0, [Segment(101, 1, 1.0, 3.0, 1.0), Segment(101, 3, 5.5, 8.0, 1.0)])
    fill_missing(audio, alignment)
    assert [(s.ayah, s.start, s.end, s.confidence) for s in alignment.segments] == [
        (1, 1.0, 3.0, 1.0), (2, 3.5, 5.0, 0.0), (3, 5.5, 8.0, 1.0)]


def test_a_silent_gap_is_not_an_ayah():
    from othman_engine.pauses import fill_missing
    audio = _recitation([(1.0, 3.0), (5.5, 8.0)], 9.0, echo=0.02)
    alignment = Alignment(9.0, 1.0, [Segment(101, 1, 1.0, 3.0, 1.0), Segment(101, 3, 5.5, 8.0, 1.0)])
    fill_missing(audio, alignment)
    assert [s.ayah for s in alignment.segments] == [1, 3]


def test_a_first_ayah_at_the_very_start_of_the_file():
    from othman_engine.pauses import fill_missing
    audio = _recitation([(0.1, 1.5), (1.8, 5.0)], 6.0, echo=0.02)
    alignment = Alignment(6.0, 1.0, [Segment(101, 2, 1.8, 5.0, 1.0)])
    fill_missing(audio, alignment)
    assert [(s.ayah, s.start) for s in alignment.segments] == [(1, 0.1), (2, 1.8)]
