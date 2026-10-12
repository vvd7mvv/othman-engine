"""مطابقة كلمات التفريغ مع كلمات المصحف.

الطريقة:
1. نبحث عن كل ثلاث كلمات متتالية من التفريغ في فهرس المصحف، وكل تطابق يعطي "قطراً"
   (الفرق بين موقع الكلمة في المصحف وموقعها في التفريغ).
2. التطابقات على نفس القطر وبكلمات متتالية تُدمج في "مقطع" متصل.
3. نختار أفضل سلسلة مقاطع غير متداخلة (برمجة ديناميكية) مع مكافأة الاستمرارية في المصحف،
   فتُحسم الآيات المتشابهة بما قبلها وبعدها، وتُقبل الإعادة والقفز بعقوبة أقل.
4. الكلمات الواقعة بين مقطعين (أخطاء تفريغ) تُطابق تقريبياً مع الكلمات المقابلة في المصحف.
"""
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache

from othman_engine import quran
from othman_engine.asr.base import Word
from othman_engine.normalize import normalize_word

NGRAM = 3
# الكلمات المتكررة جداً لا تفيد في تحديد الموقع، فنتجاهل الثلاثيات الشائعة
MAX_NGRAM_OCCURRENCES = 40
CONTINUITY_BONUS = 3.0
# إعادة القارئ لكلمات قريبة (رجوع للوقف والابتداء) أمر طبيعي
SHORT_BACKTRACK_WORDS = 40
JUMP_PENALTY = 4.0
LOCAL_GAP = 30
GAP_SIMILARITY = 0.6
MAX_GAP_CELLS = 4000


@dataclass(frozen=True)
class Run:
    rec_start: int
    rec_end: int  # غير شامل
    quran_start: int

    @property
    def length(self) -> int:
        return self.rec_end - self.rec_start

    @property
    def quran_end(self) -> int:
        return self.quran_start + self.length


@cache
def _ngram_index() -> dict[tuple[str, ...], list[int]]:
    words = [w.text for w in quran.word_stream()]
    index = defaultdict(list)
    for i in range(len(words) - NGRAM + 1):
        index[tuple(words[i : i + NGRAM])].append(i)
    return dict(index)


def find_runs(rec: list[str]) -> list[Run]:
    index = _ngram_index()
    hits = defaultdict(list)  # القطر -> مواقع بداية الثلاثيات في التفريغ
    for i in range(len(rec) - NGRAM + 1):
        positions = index.get(tuple(rec[i : i + NGRAM]), [])
        if len(positions) > MAX_NGRAM_OCCURRENCES:
            continue
        for pos in positions:
            hits[pos - i].append(i)

    runs = []
    for diagonal, starts in hits.items():
        run_start = previous = starts[0]
        for i in starts[1:] + [None]:
            # فجوة صغيرة على نفس القطر تعني ثلاثيات تجاهلناها لشيوعها (مثل "من دون الله")
            # أو كلمة واحدة أخطأ فيها التفريغ؛ القراءة متصلة فلا نقسم المقطع
            if i is not None and i <= previous + NGRAM + 1:
                previous = i
                continue
            runs.append(Run(run_start, previous + NGRAM, run_start + diagonal))
            if i is not None:
                run_start = previous = i
    return runs


def _transition_score(prev: Run, nxt: Run) -> float:
    step = nxt.quran_start - prev.quran_end
    rec_gap = nxt.rec_start - prev.rec_end
    # نفس القطر تقريباً: قراءة متصلة، حتى لو تداخل المقطعان بكلمات قليلة
    if abs(step - rec_gap) <= 2:
        return CONTINUITY_BONUS
    if -SHORT_BACKTRACK_WORDS <= step < 0:
        return CONTINUITY_BONUS / 2
    if 0 <= step <= rec_gap + 10:
        return 0.0
    return -JUMP_PENALTY


def choose_runs(runs: list[Run]) -> list[Run]:
    """أفضل سلسلة مقاطع غير متداخلة في التفريغ.

    الانتقال من مقطع قريب (فجوة ≤ LOCAL_GAP كلمة) يُقيَّم بالاستمرارية في المصحف،
    والانتقال من أي مقطع أبعد يُعامل كقفزة؛ هذا يبقي التعقيد قريباً من الخطي.
    """
    if not runs:
        return []
    runs = sorted(runs, key=lambda r: (r.rec_start, -r.length))
    by_end = sorted(range(len(runs)), key=lambda i: runs[i].rec_end)
    ends_at = defaultdict(list)
    best = [0.0] * len(runs)
    back = [-1] * len(runs)
    far_best, far_index, pointer = 0.0, -1, 0

    for j, run in enumerate(runs):
        # كل مقطع ينتهي قبل (بداية الحالي - LOCAL_GAP) يصلح كسابق بعيد
        while pointer < len(by_end) and runs[by_end[pointer]].rec_end <= run.rec_start - LOCAL_GAP:
            i = by_end[pointer]
            if best[i] > far_best:
                far_best, far_index = best[i], i
            pointer += 1

        best[j] = run.length
        if far_index != -1 and far_best + run.length - JUMP_PENALTY > best[j]:
            best[j], back[j] = far_best + run.length - JUMP_PENALTY, far_index
        # السابق قد يتداخل مع الحالي بكلمات قليلة (حدود الثلاثيات)؛ تُحسب الكلمات المشتركة مرة واحدة
        for end in range(max(0, run.rec_start - LOCAL_GAP + 1), run.rec_start + NGRAM):
            for i in ends_at[end]:
                if runs[i].rec_start >= run.rec_start:
                    continue
                gained = run.length - max(0, runs[i].rec_end - run.rec_start)
                score = best[i] + gained + _transition_score(runs[i], run)
                if score > best[j]:
                    best[j], back[j] = score, i
        ends_at[run.rec_end].append(j)

    j = max(range(len(runs)), key=best.__getitem__)
    chain = []
    while j != -1:
        chain.append(runs[j])
        j = back[j]
    return chain[::-1]


def _trim_overlaps(chain: list[Run]) -> list[Run]:
    """المقاطع المتجاورة قد تتداخل في التفريغ بعد التوسيع؛ نقص بداية اللاحق."""
    trimmed = []
    for run in chain:
        if trimmed and run.rec_start < trimmed[-1].rec_end:
            cut = trimmed[-1].rec_end - run.rec_start
            if cut >= run.length:
                continue
            run = Run(run.rec_start + cut, run.rec_end, run.quran_start + cut)
        trimmed.append(run)
    return trimmed


def _align_gap(rec: list[str], rec_range: range, quran_range: range, mapping: dict[int, int]) -> None:
    """محاذاة مرتبة (Needleman-Wunsch) بين كلمات التفريغ والمصحف في الفجوة، بتشابه الحروف."""
    n, m = len(rec_range), len(quran_range)
    if not n or not m or n * m > MAX_GAP_CELLS:
        return
    stream = quran.word_stream()
    sim = [[SequenceMatcher(None, rec[r], stream[q].text).ratio() for q in quran_range] for r in rec_range]
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diagonal = score[i - 1][j - 1] + sim[i - 1][j - 1] if sim[i - 1][j - 1] >= GAP_SIMILARITY else -1
            score[i][j] = max(score[i - 1][j], score[i][j - 1], diagonal)
    i, j = n, m
    while i and j:
        if sim[i - 1][j - 1] >= GAP_SIMILARITY and score[i][j] == score[i - 1][j - 1] + sim[i - 1][j - 1]:
            mapping[rec_range[i - 1]] = quran_range[j - 1]
            i, j = i - 1, j - 1
        elif score[i][j] == score[i - 1][j]:
            i -= 1
        else:
            j -= 1


def match_words(words: list[Word]) -> dict[int, int]:
    """يرجع: رقم الكلمة في التفريغ -> موقعها في word_stream."""
    rec = [normalize_word(w.text) for w in words]
    chain = _trim_overlaps(choose_runs(find_runs(rec)))
    mapping = {}
    for run in chain:
        for k in range(run.length):
            mapping[run.rec_start + k] = run.quran_start + k

    stream = quran.word_stream()
    boundaries = [None] + chain + [None]
    for prev, nxt in zip(boundaries, boundaries[1:]):
        if prev is None and nxt is None:
            continue
        rec_lo = prev.rec_end if prev else 0
        rec_hi = nxt.rec_start if nxt else len(rec)
        if prev and nxt:
            q_lo, q_hi = prev.quran_end, nxt.quran_start
            if q_hi < q_lo:  # إعادة: الكلمات المفقودة قد تكون بداية الإعادة
                q_lo = max(0, q_hi - (rec_hi - rec_lo))
        # الأطراف (قبل أول مقطع وبعد آخر مقطع) غالباً كلام غير قرآني كالاستعاذة،
        # فلا نطابقها إلا مع بقية الآية نفسها
        elif prev:
            last = stream[prev.quran_end - 1]
            q_lo, q_hi = prev.quran_end, quran.ayah_span(last.surah, last.ayah).stop
        else:
            first = stream[nxt.quran_start]
            q_lo, q_hi = quran.ayah_span(first.surah, first.ayah).start, nxt.quran_start
            # الحروف المقطعة آية مستقلة قبلها (مثل "الم" ثم "تنزيل الكتاب")، وثلاثياتها لا تكفي لمقطع
            while q_lo > 0 and quran.is_muqattaat_ayah(stream[q_lo - 1].surah, stream[q_lo - 1].ayah):
                q_lo -= 1
        _align_gap(rec, range(rec_lo, rec_hi), range(q_lo, q_hi), mapping)
    _extend_muqattaat(rec, mapping)
    return mapping


def _extend_muqattaat(rec: list[str], mapping: dict[int, int]) -> None:
    """الموديل يقطّع الحروف المقطعة الممدودة ويكررها ("الم الم ص ص" لـ"المص")؛
    الكلمات المجاورة غير المطابقة المكونة من حروفها فقط تُضم إليها."""
    positions = quran.muqattaat_positions()
    for index, position in sorted(mapping.items()):
        if position not in positions:
            continue
        for step in (-1, 1):
            k = index + step
            while 0 <= k < len(rec) and k not in mapping and rec[k] and set(rec[k]) <= quran.MUQATTAAT_LETTERS:
                mapping[k] = position
                k += step
