"""أدوات مشتركة لنوتبوكات توقيت المصاحف الكاملة: المدخلات، الحفظ أولاً بأول، التكملة، والمقارنة بمرجع mp3quran.

لا تعتمد على othman_engine لأن نوتبوك منجّم يستخدمها أيضاً.
"""
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

# عدد آيات كل سورة (العدّ الكوفي، رواية حفص)
AYAH_COUNTS = (
    7, 286, 200, 176, 120, 165, 206, 75, 129, 109, 123, 111, 43, 52, 99, 128, 111, 110, 98, 135,
    112, 78, 118, 64, 77, 227, 93, 88, 69, 60, 34, 30, 73, 54, 45, 83, 182, 88, 75, 85,
    54, 53, 89, 59, 37, 35, 38, 29, 18, 45, 60, 49, 62, 55, 78, 96, 29, 22, 24, 13,
    14, 11, 11, 18, 12, 12, 30, 52, 52, 44, 28, 28, 20, 56, 40, 31, 50, 40, 46, 42,
    29, 19, 36, 25, 22, 17, 19, 26, 30, 20, 15, 21, 11, 8, 8, 19, 5, 8, 8, 11,
    11, 8, 3, 9, 5, 4, 7, 3, 6, 3, 5, 4, 5, 6,
)

MP3QURAN_API = "https://mp3quran.net/api/v3"
USER_AGENT = "othman-timings/1.0"
FORMAT_VERSION = 1


def parse_surahs(spec: str) -> list[int]:
    """'1-114' أو '2,18,67' أو '78-80,2' ← قائمة مرتبة بلا تكرار."""
    numbers = set()
    for part in spec.replace("،", ",").split(","):
        part = part.strip()
        if not part:
            continue
        first, _, last = part.partition("-")
        first, last = int(first), int(last or first)
        if not 1 <= first <= last <= 114:
            raise ValueError(f"Bad surah range: {part}")
        numbers.update(range(first, last + 1))
    return sorted(numbers)


def surah_from_url(url: str) -> int:
    name = Path(urllib.parse.urlparse(url).path).stem
    digits = re.search(r"(\d{1,3})$", name)
    if not digits or not 1 <= int(digits.group(1)) <= 114:
        raise ValueError(f"Cannot tell the surah number from the file name: {url}")
    return int(digits.group(1))


def parse_sources(text: str, surahs: str = "1-114") -> list[tuple[int, str]]:
    """كل سطر رابط ملف (رقم السورة من اسمه) أو رابط مجلد ينتهي بـ / (تُكمَّل بـ 001.mp3 ... حسب surahs)."""
    sources = []
    for line in text.splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        if url.endswith("/"):
            sources += [(n, f"{url}{n:03d}.mp3") for n in parse_surahs(surahs)]
        else:
            sources.append((surah_from_url(url), url))
    return sources


def reciter_slug(url: str) -> str:
    """مجلد القارئ من الرابط: .../audio/abdulrahman-sudais/r1/002.mp3 ← abdulrahman-sudais_r1"""
    parts = [p for p in urllib.parse.urlparse(url).path.split("/")[:-1] if p]
    if parts and parts[0] == "audio":
        parts = parts[1:]
    slug = "_".join(parts) or urllib.parse.urlparse(url).netloc
    return re.sub(r"[^A-Za-z0-9._-]+", "-", slug)


def output_path(root: Path, engine: str, url: str) -> Path:
    return Path(root) / engine / reciter_slug(url) / f"{surah_from_url(url):03d}.json"


def _get(url: str, timeout: int = 60) -> bytes:
    last_error = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as error:  # الشبكة في Colab تنقطع أحياناً؛ نعيد المحاولة قبل الاستسلام
            last_error = error
            time.sleep(2 ** (attempt + 1))
    raise last_error


def get_json(url: str):
    return json.loads(_get(url))


def download(url: str, folder: Path) -> Path:
    target = Path(folder) / Path(urllib.parse.urlparse(url).path).name
    target.write_bytes(_get(url, timeout=600))
    return target


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    )
    return float(out.stdout.strip())


_reads_cache = None


def mp3quran_reads() -> list[dict]:
    global _reads_cache
    if _reads_cache is None:
        _reads_cache = get_json(f"{MP3QURAN_API}/ayat_timing/reads")
    return _reads_cache


def _folder_key(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.removeprefix("www.") + parsed.path.rsplit("/", 1)[0] + "/"


def mp3quran_read_id(url: str) -> int | None:
    """رقم المصحف في توقيت mp3quran إذا كان الصوت من مجلد عندهم، وإلا None."""
    if "mp3quran.net" not in urllib.parse.urlparse(url).netloc:
        return None
    key = _folder_key(url)
    for read in mp3quran_reads():
        if _folder_key(read["folder_url"] + "x") == key:
            return read["id"]
    return None


def build_result(surah: int, url: str, ayahs: dict, meta: dict) -> dict:
    """ayahs: {رقم الآية: (start, end, confidence)}. الآيات الناقصة تُكتب null مع confidence 0،
    والبسملة (0) تُكتب فقط إذا وُجدت."""
    rows = []
    for number in ([0] if 0 in ayahs else []) + list(range(1, AYAH_COUNTS[surah - 1] + 1)):
        start, end, confidence = ayahs.get(number, (None, None, 0.0))
        rows.append({
            "ayah": number,
            "start": None if start is None else round(float(start), 3),
            "end": None if end is None else round(float(end), 3),
            "confidence": round(min(max(float(confidence), 0.0), 1.0), 3),
        })
    return {
        "format_version": FORMAT_VERSION,
        "surah": surah,
        "audio": Path(urllib.parse.urlparse(url).path).name,
        "audio_url": url,
        "mp3quran_read": mp3quran_read_id(url),
        "ayahs": rows,
        "meta": meta,
    }


def save_json(path: Path, data: dict) -> None:
    """الكتابة لملف مؤقت ثم إعادة تسمية: انقطاع الجلسة أثناء الكتابة لا يترك ملفاً ناقصاً يُحسب منجزاً."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.part")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def is_done(path: Path) -> bool:
    try:
        return bool(json.loads(Path(path).read_text(encoding="utf-8")).get("ayahs"))
    except (OSError, ValueError):
        return False


def _minutes(seconds: float) -> str:
    return f"{seconds / 60:.1f} min" if seconds >= 60 else f"{seconds:.0f} s"


def run_batch(sources, out_root, engine: str, align, device: str, version: str = "",
              speed_guess: float = 0.1, long_audio: float = 1800):
    """align(path, surah) ← {ayah: (start, end, confidence)}.
    speed_guess: ثواني المعالجة لكل ثانية صوت قبل أن نقيسها فعلياً؛ تُستبدل بالمقاس بعد أول سورة."""
    total_audio = total_work = 0.0
    pending = [(s, u) for s, u in sources if not is_done(output_path(out_root, engine, u))]
    print(f"{len(sources) - len(pending)} done before, {len(pending)} to go")
    failures = []
    for index, (surah, url) in enumerate(pending, 1):
        target = output_path(out_root, engine, url)
        with tempfile.TemporaryDirectory() as folder:
            try:
                path = download(url, Path(folder))
                duration = audio_duration(path)
                speed = total_work / total_audio if total_audio else speed_guess
                note = f"  ⏳ long file: expect about {_minutes(duration * speed)}" if duration >= long_audio else ""
                print(f"[{index}/{len(pending)}] surah {surah} ({_minutes(duration)} audio){note}", flush=True)
                began = time.time()
                ayahs = align(path, surah)
                seconds = time.time() - began
            except Exception as error:
                print(f"  ✗ surah {surah}: {type(error).__name__}: {error}", flush=True)
                failures.append((surah, url, str(error)))
                continue
        total_audio += duration
        total_work += seconds
        meta = {"engine": engine, "version": version, "device": device,
                "seconds": round(seconds, 2), "audio_seconds": round(duration, 2)}
        result = build_result(surah, url, ayahs, meta)
        save_json(target, result)
        missing = sum(1 for row in result["ayahs"] if row["start"] is None)
        print(f"  ✓ {seconds:.1f} s, missing ayahs: {missing} → {target}", flush=True)
    if failures:
        print(f"\n{len(failures)} failed (run the cell again to retry them):")
        for surah, url, error in failures:
            print(f"  surah {surah}: {error}  {url}")
    return failures


def mp3quran_reference(read: int, surah: int) -> dict[int, tuple[float, float]]:
    """{آية: (start, end)} بالثواني. نهاية الآية عندهم = بداية التالية (تشمل الصمت)."""
    rows = get_json(f"{MP3QURAN_API}/ayat_timing?surah={surah}&read={read}")
    return {row["ayah"]: (row["start_time"] / 1000, row["end_time"] / 1000)
            for row in rows if row["ayah"] > 0}


def compare(result: dict, reference: dict[int, tuple[float, float]], threshold: float = 1.0) -> dict:
    """الفرق بالثواني عن المرجع. الآيات الناقصة في الناتج تُعد فرقاً أكبر من الحد ولا تدخل في المتوسط."""
    start_diffs, end_diffs, missing = [], [], 0
    rows = {row["ayah"]: row for row in result["ayahs"] if row["ayah"] > 0}
    for ayah, (ref_start, ref_end) in reference.items():
        row = rows.get(ayah)
        if not row or row["start"] is None:
            missing += 1
            continue
        start_diffs.append(abs(row["start"] - ref_start))
        end_diffs.append(abs(row["end"] - ref_end))
    count = len(reference)
    over = sum(d > threshold for d in start_diffs) + missing
    mean = lambda values: round(sum(values) / len(values), 3) if values else None
    return {
        "ayahs": count,
        "missing": missing,
        "mean_start_diff": mean(start_diffs),
        "over_1s_pct": round(100 * over / count, 1) if count else None,
        "mean_end_diff": mean(end_diffs),
    }
