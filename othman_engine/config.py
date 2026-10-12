"""المسارات والثوابت. البيانات (النموذج ونصوص Tanzil) في OTHMAN_ENGINE_HOME، وافتراضياً ~/.othman-engine."""
import os
from pathlib import Path

HOME = Path(os.environ.get("OTHMAN_ENGINE_HOME", Path.home() / ".othman-engine"))
DATA_DIR = HOME / "data"
TANZIL_DIR = DATA_DIR / "tanzil"
MODELS_DIR = HOME / "models"

MODEL_REPO = "Muno459/fastconformer-quran"
MODEL_DIR = MODELS_DIR / "fastconformer-quran"
# model.fp16.onnx لا يعمل على المعالج (خطأ أنواع داخل الملف)؛ q8 نصف الذاكرة لكنه أبطأ ~35%
MODEL_FILE = MODEL_DIR / "onnx" / "model.onnx"
TOKENIZER_FILE = MODEL_DIR / "tokenizer.model"

SAMPLE_RATE = 16000
AYAH_COUNT = 6236
# أقل نسبة من مدة المقطع يجب أن تطابق آيات، وإلا فليس تلاوة
MIN_MATCHED_RATIO = 0.5
