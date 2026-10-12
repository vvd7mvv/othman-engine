"""alignment.json: الناتج الأساسي للمعالجة الثقيلة، وكل المخرجات تتولد منه."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from othman_engine import quran
from othman_engine.asr.base import Word

VERSION = 1


@dataclass
class Segment:
    surah: int
    ayah: int  # 0 = البسملة
    start: float
    end: float
    confidence: float
    # الكلمات التي طابقها التفريغ: [ترتيبها في الآية (نص Tanzil)، بدايتها، نهايتها]؛ فارغة في التوقيتات القديمة
    words: list = field(default_factory=list)
    # وقفات القارئ للنفَس داخل الآية: [بدايتها، نهايتها]؛ عندها تنتهي صفحة الآية وتختفي حتى يعود
    pauses: list = field(default_factory=list)


@dataclass
class Alignment:
    duration: float
    matched_ratio: float
    segments: list[Segment] = field(default_factory=list)

    def quran_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.ayah != quran.BASMALA_AYAH]

    def clip(self, start: float, end: float | None) -> "Alignment":
        """جزء من المقطع (قص بعد التفريغ)؛ التوقيتات تصبح نسبية لبداية الجزء."""
        end = self.duration if end is None else min(end, self.duration)
        segments = [
            Segment(s.surah, s.ayah, round(max(s.start, start) - start, 2), round(min(s.end, end) - start, 2),
                    s.confidence,
                    [[i, round(a - start, 2), round(b - start, 2)] for i, a, b in s.words if a >= start and b <= end],
                    [[round(a - start, 2), round(b - start, 2)] for a, b in s.pauses if a >= start and b <= end])
            for s in self.segments
            if s.end > start and s.start < end
        ]
        return Alignment(round(end - start, 2), self.matched_ratio, segments)

    def save(self, path: Path) -> None:
        data = {"version": VERSION, **asdict(self)}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Alignment":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["duration"], data["matched_ratio"], [Segment(**s) for s in data["segments"]])


# في الآيات القصيرة تتقارب أول الكلمات وآخرها، فلا يُعرف الرجوع لأولها من الوقف والابتداء
MIN_RESTART_WORDS = 4


def _restarts(index: int, previous_index: int, key: tuple[int, int]) -> bool:
    count = quran.ayah_word_count(*key)
    return count >= MIN_RESTART_WORDS and index <= 1 and previous_index >= count - 2


def build(words: list[Word], mapping: dict[int, int], duration: float) -> Alignment:
    """يجمع الكلمات المتتالية من نفس الآية في مقطع واحد.

    الرجوع لآية سابقة يبدأ مقطعاً جديداً، أما الرجوع داخل نفس الآية (وقف وابتداء) فيبقى في نفس المقطع،
    إلا إعادة الآية كاملة (من أولها بعد بلوغ آخرها): مقطع جديد، وإلا عُرضت صفحتها الأولى طوال القراءة الأولى.
    """
    stream = quran.word_stream()
    groups = []  # [(surah, ayah), [أرقام كلمات التفريغ]]
    for i in sorted(mapping):
        word = stream[mapping[i]]
        key = word.surah, word.ayah
        if groups and groups[-1][0] == key and not _restarts(word.index, stream[mapping[groups[-1][1][-1]]].index, key):
            groups[-1][1].append(i)
        else:
            groups.append((key, [i]))

    segments = []
    for (surah, ayah), indices in groups:
        covered = {stream[mapping[i]].index for i in indices}
        segments.append(Segment(
            surah=surah,
            ayah=ayah,
            start=round(words[indices[0]].start, 2),
            end=round(words[indices[-1]].end, 2),
            confidence=round(len(covered) / quran.ayah_word_count(surah, ayah), 2),
            words=[[stream[mapping[i]].index, round(words[i].start, 2), round(words[i].end, 2)] for i in indices],
        ))
    matched_ratio = len(mapping) / len(words) if words else 0.0
    return Alignment(round(duration, 2), round(matched_ratio, 2), segments)
