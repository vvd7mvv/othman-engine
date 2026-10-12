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
