"""نقطة الدخول: ملف تلاوة ← السورة والآيات ووقت كل كلمة."""
from pathlib import Path

from othman_engine import alignment, config, ingest, pauses
from othman_engine.alignment import Alignment
from othman_engine.errors import ProcessingError
from othman_engine.match import match_words


class Engine:
    """يحمّل النموذج مرة واحدة (~1GB ذاكرة)، ثم يعالج أي عدد من الملفات."""

    def __init__(self, threads: int | None = None):
        from othman_engine.asr.fastconformer import FastConformer
        for path in (config.MODEL_FILE, config.TOKENIZER_FILE):
            if not path.exists():
                raise ProcessingError("no_model", f"Model file missing: {path}. Run: othman-engine download")
        self.transcriber = FastConformer(threads=threads)

    def align_audio(self, audio) -> Alignment:
        """audio: مصفوفة float32 أحادية بمعدل config.SAMPLE_RATE."""
        words = self.transcriber.transcribe(audio)
        result = alignment.build(words, match_words(words), len(audio) / config.SAMPLE_RATE)
        if result.matched_ratio < config.MIN_MATCHED_RATIO or not result.quran_segments():
            raise ProcessingError("not_quran", "No Quran recitation was recognised.")
        pauses.extend_opening_letters(audio, result)
        pauses.add_pauses(audio, result)
        return result

    def align_file(self, path: Path, start: float = 0.0, end: float | None = None) -> Alignment:
        """التوقيتات نسبية لـ start."""
        ingest.probe_duration(Path(path))
        return self.align_audio(ingest.load_audio(Path(path), start, end))
