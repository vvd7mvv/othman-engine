"""توقيت من الصوت نفسه حيث لا يكفي توقيت التفريغ: وقفات النفَس داخل الآية، وبداية الحروف المقطعة الممدودة."""
import numpy as np

from othman_engine import config
from othman_engine import quran
from othman_engine.alignment import Alignment

FRAME_SECONDS = 0.05
# صدى المسجد يُبقي الوقفة مسموعة (~10dB تحت القراءة)، أما التوقف عند حرف مشدد أو قلقلة فأقصر من نصف ثانية
QUIET_DROP_DB = 8
MIN_PAUSE_SECONDS = 0.5
# الحروف المقطعة: "أَلِفۡ لَاااام مِيييم" تبدأ قبل أن يكتب الموديل "الم" بثوانٍ
OPENING_LETTERS_LOOKBACK_SECONDS = 10.0
SILENCE_BEFORE_SECONDS = 0.3


def add_pauses(audio: np.ndarray, alignment: Alignment) -> None:
    """الفراغ بين كلمتين في توقيت التفريغ وحده لا يكفي: الموديل يُنهي الكلمة قبل نهاية المد،
    وقد يترك فراغاً طويلاً داخل مد متصل، فنبحث عن الهدوء في الصوت نفسه بين بدايتي الكلمتين."""
    loudness = _loudness(audio)
    for segment in alignment.segments:
        starts = sorted(start for _, start, _ in segment.words)
        if len(starts) < 2:
            continue
        frames = loudness[_frame(segment.start) : _frame(segment.end)]
        if not len(frames):
            continue
        quiet = loudness < np.median(frames) - QUIET_DROP_DB
        segment.pauses = [
            pause for a, b in zip(starts, starts[1:]) if (pause := _longest_quiet_run(quiet, a, b))
        ]


def _loudness(audio: np.ndarray) -> np.ndarray:
    hop = int(config.SAMPLE_RATE * FRAME_SECONDS)
    frames = len(audio) // hop
    power = np.square(audio[: frames * hop], dtype=np.float64).reshape(frames, hop).mean(axis=1)
    return 10 * np.log10(power + 1e-12)


def _frame(t: float) -> int:
    return max(0, round(t / FRAME_SECONDS))


def _longest_quiet_run(quiet: np.ndarray, start: float, end: float) -> list[float] | None:
    best, run_start = None, None
    first, last = _frame(start), min(_frame(end), len(quiet))
    for i in range(first, last + 1):
        if i < last and quiet[i]:
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            if best is None or i - run_start > best[1] - best[0]:
                best = (run_start, i)
            run_start = None
    if best is None or (best[1] - best[0]) * FRAME_SECONDS < MIN_PAUSE_SECONDS:
        return None
    return [round(best[0] * FRAME_SECONDS, 2), round(best[1] * FRAME_SECONDS, 2)]


def extend_opening_letters(audio: np.ndarray, alignment: Alignment) -> None:
    """بداية آية الحروف المقطعة = بداية الصوت المتصل قبل أول حرف كتبه الموديل (لا قبل الآية السابقة)."""
    loudness = _loudness(audio)
    if not len(loudness):
        return
    quiet = loudness < np.median(loudness) - QUIET_DROP_DB
    previous_end = 0.0
    for segment in alignment.segments:
        if quran.is_muqattaat_ayah(segment.surah, segment.ayah):
            earliest = _frame(max(previous_end, segment.start - OPENING_LETTERS_LOOKBACK_SECONDS))
            i, silent = min(_frame(segment.start), len(quiet)), 0
            while i > earliest and silent * FRAME_SECONDS < SILENCE_BEFORE_SECONDS:
                i -= 1
                silent = silent + 1 if quiet[i] else 0
            start = (i + silent) * FRAME_SECONDS
            segment.start = round(min(segment.start, max(start, previous_end)), 2)
        previous_end = segment.end
