"""مسطرة المحرك: توقيت محركنا مقابل توقيت mp3quran (مضبوط يدوياً) لعشرة قرّاء و15 سورة فيها أخطاء معروفة.

التفريغ (الأبطأ، ~ساعة أول مرة على 4 أنوية) يُحفظ لكل ملف في data/benchmark/، فتغييرات المطابقة والحدود تُقاس في دقائق.
آية صحيحة = منتصف آيتنا داخل آيتهم ومنتصف آيتهم داخل آيتنا. «غلط» هنا قد يكون من mp3quran نفسه (أو قارئ كرر الآية).

الاستخدام: python scripts/benchmark.py [--retranscribe] [--only read:surah]  (read رقم المصحف في توقيت mp3quran)
النسخة 0.3.0: 5950 آية، ناقصة 1، غلط 7.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))
import timings  # noqa: E402

from othman_engine import alignment, config, ingest, pauses  # noqa: E402
from othman_engine.asr.base import Word  # noqa: E402
from othman_engine.match import match_words  # noqa: E402

ROOT = config.DATA_DIR / "benchmark"
READS = [54, 31, 123, 118, 112, 53, 133, 92, 30, 4]
SURAHS = [42, 50, 51, 52, 55, 69, 74, 75, 77, 78, 79, 101, 102, 103, 106]
LOW = 0.7


def cached(path: Path, make):
    if path.exists():
        return json.loads(path.read_text())
    value = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    return value


def audio_file(folder: str, read: int, surah: int) -> Path:
    path = ROOT / "audio" / str(read) / f"{surah:03d}.mp3"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f"{folder}{surah:03d}.mp3", path)
    return path


_engine = None


def transcribe(audio):
    global _engine
    if _engine is None:
        from othman_engine import Engine
        _engine = Engine()
    return [[w.text, w.start, w.end] for w in _engine.transcriber.transcribe(audio)]


def align(read: int, surah: int, folder: str, retranscribe=False):
    audio = ingest.load_audio(audio_file(folder, read, surah))
    words_path = ROOT / "words" / f"{read}_{surah:03d}.json"
    if retranscribe:
        words_path.unlink(missing_ok=True)
    words = [Word(*w) for w in cached(words_path, lambda: transcribe(audio))]
    result = alignment.build(words, match_words(words), len(audio) / config.SAMPLE_RATE)
    pauses.extend_opening_letters(audio, result)
    pauses.fill_missing(audio, result)
    pauses.refine_edges(audio, result)
    found = {}
    for s in result.quran_segments():
        if s.surah == surah and s.ayah not in found:
            found[s.ayah] = s
    return found, words, result


def judge(found, reference):
    rows = []
    for ayah, (ref_start, ref_end) in sorted(reference.items()):
        s = found.get(ayah)
        if s is None:
            rows.append((ayah, "missing", None))
            continue
        ours_mid, ref_mid = (s.start + s.end) / 2, (ref_start + ref_end) / 2
        ok = ref_start <= ours_mid <= ref_end and s.start <= ref_mid <= s.end
        status = "wrong" if not ok else ("low" if s.confidence < LOW else "ok")
        rows.append((ayah, status, s))
    return rows


def main():
    retranscribe = "--retranscribe" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    reads = {r["id"]: r for r in timings.mp3quran_reads()}
    totals = {"ok": 0, "low": 0, "wrong": 0, "missing": 0}
    problems = []
    for read in READS:
        for surah in SURAHS:
            if only and only != f"{read}:{surah}":
                continue
            reference = cached(ROOT / "ref" / f"{read}_{surah:03d}.json",
                               lambda: {str(k): v for k, v in timings.mp3quran_reference(read, surah).items()})
            reference = {int(k): tuple(v) for k, v in reference.items()}
            found, _, _ = align(read, surah, reads[read]["folder_url"], retranscribe)
            for ayah, status, s in judge(found, reference):
                totals[status] += 1
                if status != "ok":
                    ref = reference[ayah]
                    ours = f"{s.start:.2f}-{s.end:.2f} c={s.confidence:.2f}" if s else "-"
                    problems.append(f"{read}:{surah}:{ayah} {status:7} ours {ours}  ref {ref[0]:.2f}-{ref[1]:.2f}")
            print(f"{reads[read]['name']} {surah}", flush=True, file=sys.stderr)
    for line in problems:
        print(line)
    count = sum(totals.values())
    print(f"\nTOTAL {count} ayahs: " + ", ".join(f"{k} {v} ({100 * v / count:.1f}%)" for k, v in totals.items()))


if __name__ == "__main__":
    main()
