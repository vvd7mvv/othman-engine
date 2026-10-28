"""توقيت من الصوت نفسه حيث لا يكفي توقيت التفريغ: حدود الآية، ووقفات النفَس داخلها، وبداية الحروف المقطعة الممدودة،
والآية التي لم يكتبها الموديل بين جارتين."""
import numpy as np

from othman_engine import config
from othman_engine import quran
from othman_engine.alignment import Alignment, Segment

FRAME_SECONDS = 0.05
# صدى المسجد يُبقي الوقفة مسموعة (~10dB تحت القراءة)، أما التوقف عند حرف مشدد أو قلقلة فأقصر من نصف ثانية
QUIET_DROP_DB = 8
MIN_PAUSE_SECONDS = 0.5
# الحروف المقطعة: "أَلِفۡ لَاااام مِيييم" تبدأ قبل أن يكتب الموديل "الم" بثوانٍ
OPENING_LETTERS_LOOKBACK_SECONDS = 10.0
SILENCE_BEFORE_SECONDS = 0.3
# حدود الآية: الموديل يبدأ الكلمة الأولى متأخراً ويقطع آخر مد قبل نهايته، والصدى بعده جزء من الآية.
# الصوت "انتهى" إذا هدأ قريباً من أهدأ نقطة في السكتة، أو صار أخفض من القراءة بـ 30dB (تسجيل بلا ضوضاء)
EDGE_LOOKAROUND_SECONDS = 4.0
EDGE_ABOVE_FLOOR_DB = 6
EDGE_BELOW_READING_DB = 30
DIGITAL_SILENCE_DB = 60


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


def refine_edges(audio: np.ndarray, alignment: Alignment) -> None:
    """البداية ترجع لأول صوت قبل الكلمة الأولى، والنهاية تمتد لين يهدأ المد والصدى،
    دون تجاوز أهدأ نقطة في السكتة بينها وبين الآية المجاورة (منتصف السكتة يقع أحياناً داخل المد،
    لأن الموديل يبدأ الآية التالية متأخراً أيضاً)."""
    loudness = _loudness(audio)
    segments = alignment.segments
    if not len(loudness) or not segments:
        return
    original = [(s.start, s.end) for s in segments]
    splits = [_quietest(loudness, a[1], b[0]) for a, b in zip(original, original[1:])]
    for i, segment in enumerate(segments):
        start, end = original[i]
        reading = loudness[_frame(start) : _frame(end)]
        if not len(reading):
            continue
        level = float(np.median(reading))
        before = max(start - EDGE_LOOKAROUND_SECONDS, splits[i - 1] if i else 0.0)
        after = min(end + EDGE_LOOKAROUND_SECONDS, splits[i] if i < len(splits) else alignment.duration)
        segment.start = round(_sound_edge(loudness, level, start, before), 2)
        segment.end = round(_sound_edge(loudness, level, end, after), 2)


# آية لم يكتب الموديل منها شيئاً (أو كتبها مشوّهة)، وجارتاها موجودتان: تأخذ ما بينهما إن كان فيه قراءة.
# ثقتها صفر فتُعلَّم للمراجعة
MISSING_MIN_SOUND_SECONDS = 0.4
MISSING_BELOW_READING_DB = 12


def fill_missing(audio: np.ndarray, alignment: Alignment) -> None:
    loudness = _loudness(audio)
    segments = alignment.segments
    if not len(loudness) or not segments:
        return
    added = []
    first = segments[0]
    # أول الملف بلا بسملة ولا استعاذة («القارعة» في ملف يبدأ بها)
    if first.ayah == 2:
        added += _between(loudness, first.surah, 1, 0.0, first.start)
    for previous, following in zip(segments, segments[1:]):
        if previous.surah == following.surah and following.ayah - previous.ayah == 2:
            added += _between(loudness, previous.surah, previous.ayah + 1, previous.end, following.start)
    alignment.segments = sorted(segments + added, key=lambda s: s.start)


def _between(loudness: np.ndarray, surah: int, ayah: int, start: float, end: float) -> list[Segment]:
    span = loudness[_frame(start):_frame(end)]
    if not len(span):
        return []
    level = float(np.percentile(loudness, 90))
    loud = np.flatnonzero(span > level - MISSING_BELOW_READING_DB)
    if len(loud) * FRAME_SECONDS < MISSING_MIN_SOUND_SECONDS:
        return []
    first = _frame(start) + int(loud[0])
    last = _frame(start) + int(loud[-1]) + 1
    return [Segment(surah=surah, ayah=ayah, start=round(max(start, first * FRAME_SECONDS), 2),
                    end=round(min(end, last * FRAME_SECONDS), 2), confidence=0.0)]


def _quietest(loudness: np.ndarray, end: float, next_start: float) -> float:
    first, last = _frame(end), min(_frame(next_start), len(loudness))
    if last <= first:
        return min(end, next_start)
    return (first + int(np.argmin(loudness[first:last]))) * FRAME_SECONDS


def _sound_edge(loudness: np.ndarray, level: float, edge: float, limit: float) -> float:
    """يمشي من edge نحو limit ما دام الصوت مسموعاً، ويتوقف عند أول هدوء متصل لـ SILENCE_BEFORE_SECONDS.
    الهدوء نسبي لأهدأ نقطة في المدى (الصدى وضوضاء المسجد)، وفي مدى بلا سكتة يكفي أن يخفت عن القراءة."""
    low, high = sorted((_frame(edge), _frame(limit)))
    span = loudness[low : min(high, len(loudness))]
    if not len(span):
        return edge
    # الصمت الرقمي (آخر الملف أو صوت مقصوص) ليس مستوى ضوضاء المسجد، فلا يُقاس عليه
    audible = span[span > level - DIGITAL_SILENCE_DB]
    floor = np.percentile(audible, 10) + EDGE_ABOVE_FLOOR_DB if len(audible) else level
    threshold = max(min(floor, level - EDGE_ABOVE_FLOOR_DB), level - EDGE_BELOW_READING_DB)
    forward = limit > edge
    order = range(len(span)) if forward else range(len(span) - 1, -1, -1)
    need, silent, last_sound = round(SILENCE_BEFORE_SECONDS / FRAME_SECONDS), 0, None
    for i in order:
        if span[i] >= threshold:
            last_sound, silent = i, 0
        elif (silent := silent + 1) >= need:
            break
    if last_sound is None:
        return edge
    if forward:
        return min(max((low + last_sound + 1) * FRAME_SECONDS, edge), limit)
    return max(min((low + last_sound) * FRAME_SECONDS, edge), limit)
