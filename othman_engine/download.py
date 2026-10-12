"""تحميل النموذج (Hugging Face) ونصوص Tanzil إلى OTHMAN_ENGINE_HOME."""
import os
import sys
import urllib.request
from pathlib import Path

from othman_engine import config

TANZIL_TEXT = ("https://tanzil.net/pub/download/index.php?marks=true&sajdah=true&rub=true&tatweel=true"
               "&outType=txt-2&agree=true&quranType=simple-clean")
TANZIL_FILES = {
    "quran-simple-clean.txt": TANZIL_TEXT,
    "quran-data.xml": "https://tanzil.net/res/text/metadata/quran-data.xml",
}


def count_ayahs(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip() and not line.startswith("#"))


def download_tanzil() -> None:
    config.TANZIL_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in TANZIL_FILES.items():
        target = config.TANZIL_DIR / name
        print(f"Downloading {name}")
        urllib.request.urlretrieve(url, target)
        if target.suffix == ".txt" and count_ayahs(target) != config.AYAH_COUNT:
            sys.exit(f"{name} does not have {config.AYAH_COUNT} ayahs")


def download_model() -> None:
    """الموديل محمي بموافقة: اقبل الشروط من صفحته، ثم ضع الـ token في HF_TOKEN."""
    from huggingface_hub import snapshot_download
    if not os.environ.get("HF_TOKEN"):
        sys.exit(f"HF_TOKEN is not set. Accept the terms at https://huggingface.co/{config.MODEL_REPO} "
                 "and create a token at https://huggingface.co/settings/tokens")
    try:
        snapshot_download(repo_id=config.MODEL_REPO, local_dir=config.MODEL_DIR,
                          allow_patterns=["onnx/model.onnx", "tokenizer.model", "LICENSE", "README.md"])
    except Exception as error:  # noqa: BLE001 أخطاء huggingface_hub تختلف بين الإصدارات
        text = str(error)
        if any(word in text for word in ("401", "403", "gated", "Gated", "authorized", "Unauthorized")):
            sys.exit(f"Hugging Face refused the download. Accept the model's terms while logged in at "
                     f"https://huggingface.co/{config.MODEL_REPO} and check that HF_TOKEN is that account's token "
                     f"(fine-grained tokens need 'Read access to public gated repos').\n{text.splitlines()[0]}")
        sys.exit(f"Model download failed: {text.splitlines()[0] if text else type(error).__name__}")
    for path in (config.MODEL_FILE, config.TOKENIZER_FILE):
        if not path.exists():
            sys.exit(f"Missing after download: {path}")


def main() -> None:
    download_tanzil()
    download_model()
    print(f"Done: {config.HOME}")
