"""قياس دقة التفريغ والمطابقة على تلاوات سور كاملة معروفة الآيات.

نستخدم تسجيلات سور كاملة متصلة من quranicaudio. لا نستخدم ملفات everyayah (آية لكل ملف)
لأن الموديل تدرّب عليها، فدمجها يعطي نتائج مضللة.
الملفات تُحفظ في data/eval/ حتى لا تُحمّل كل مرة.

الاستخدام: python scripts/evaluate.py [اسم الحالة ...]
"""
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from othman_engine import config
from othman_engine import alignment, ingest, quran
from othman_engine.asr.fastconformer import FastConformer
from othman_engine.match import match_words

EVAL_DIR = config.DATA_DIR / "eval"
SOURCE = "https://download.quranicaudio.com/quran/{reciter}/{surah:03d}.mp3"
DOWNLOAD_ATTEMPTS = 4

# اسم الحالة: (القارئ، السور المتتالية)
CASES = {
    "mulk_sudais": ("abdurrahmaan_as-sudays", [67]),
    "rahman_dussary": ("yasser_ad-dussary", [55]),
    "naba_qatami": ("nasser_bin_ali_alqatami", [78]),
    "fatiha_minshawi": ("muhammad_siddeeq_al-minshaawee", [1]),
    "falaq_nas_husary": ("mahmood_khaleel_al-husaree", [113, 114]),
    "tariq_maher": ("maher_almu3aiqly/year1440", [86]),
}


def download(reciter, surah) -> Path:
    target = EVAL_DIR / reciter.replace("/", "_") / f"{surah:03d}.mp3"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            urllib.request.urlretrieve(SOURCE.format(reciter=reciter, surah=surah), target)
            return target
        except OSError:
            if attempt == DOWNLOAD_ATTEMPTS - 1:
                raise
            time.sleep(2 ** attempt)


def expected_ayahs(surahs):
    expected = []
    for surah in surahs:
        if quran.has_basmala(surah):
            expected.append((surah, quran.BASMALA_AYAH))
        expected += [(surah, a) for a in range(1, quran.surahs()[surah - 1].ayah_count + 1)]
    return expected


def evaluate(name, transcriber):
    reciter, surahs = CASES[name]
    audio = np.concatenate([ingest.load_audio(download(reciter, s)) for s in surahs])
    duration = len(audio) / config.SAMPLE_RATE
    started = time.time()
    words = transcriber.transcribe(audio)
    result = alignment.build(words, match_words(words), duration)
    elapsed = time.time() - started

    got = [(s.surah, s.ayah) for s in result.segments]
    want = expected_ayahs(surahs)
    # بعض التسجيلات بلا بسملة، فغيابها لا يُعد خطأ
    missing = [a for a in want if a not in got and a[1] != quran.BASMALA_AYAH]
    extra = [a for a in got if a not in want]
    out_of_order = not extra and got != sorted(got, key=want.index)
    ok = not missing and not extra and not out_of_order
    low = [f"{s.surah}:{s.ayah}={s.confidence}" for s in result.segments if s.confidence < 0.8]
    print(f"\n{name}: {'✓' if ok else '✗'}  {duration:.0f}s audio in {elapsed:.1f}s, matched {result.matched_ratio}")
    if missing:
        print(f"  missing: {missing}")
    if extra:
        print(f"  extra:   {extra}")
    if out_of_order:
        print(f"  order:   {got}")
    if low:
        print(f"  low confidence: {low}")
    return ok


def main():
    names = sys.argv[1:] or list(CASES)
    transcriber = FastConformer()
    passed = sum(evaluate(name, transcriber) for name in names)
    print(f"\n{passed}/{len(names)} passed")


if __name__ == "__main__":
    main()
