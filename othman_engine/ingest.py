"""استخراج الصوت من أي ملف فيديو أو صوت عبر ffmpeg."""
import subprocess
from pathlib import Path

import numpy as np

from othman_engine import config
from othman_engine.errors import ProcessingError


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise ProcessingError("bad_file", "Cannot read the file; is it a valid audio or video file?") from None


def load_audio(path: Path, start: float = 0.0, end: float | None = None) -> np.ndarray:
    """صوت أحادي 16kHz. start/end بالثواني لقص جزء دون إنشاء ملف جديد."""
    # قبل -i: ffmpeg يقص بدقة لأنه يعيد الترميز
    trim = (["-ss", f"{start:.3f}"] if start else []) + (["-to", f"{end:.3f}"] if end is not None else [])
    result = subprocess.run(
        ["ffmpeg", "-v", "error", *trim, "-i", str(path), "-vn", "-ac", "1", "-ar", str(config.SAMPLE_RATE),
         "-f", "s16le", "-"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise ProcessingError("bad_file", "Cannot extract audio from the file.")
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
