"""أدوات مشتركة لنوتبوكات توقيت المصاحف الكاملة: المدخلات، الحفظ أولاً بأول، التكملة، والمقارنة بمرجع mp3quran.

لا تعتمد على othman_engine لأن نوتبوك منجّم يستخدمها أيضاً.
"""
import http.server
import json
import os
import random
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
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

# أسماء Tanzil، وبعدها أسماء أخرى شائعة في أسماء الملفات
SURAH_NAMES = (
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة", "الأنعام", "الأعراف", "الأنفال", "التوبة", "يونس",
    "هود", "يوسف", "الرعد", "ابراهيم", "الحجر", "النحل", "الإسراء", "الكهف", "مريم", "طه",
    "الأنبياء", "الحج", "المؤمنون", "النور", "الفرقان", "الشعراء", "النمل", "القصص", "العنكبوت", "الروم",
    "لقمان", "السجدة", "الأحزاب", "سبإ", "فاطر", "يس", "الصافات", "ص", "الزمر", "غافر",
    "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية", "الأحقاف", "محمد", "الفتح", "الحجرات", "ق",
    "الذاريات", "الطور", "النجم", "القمر", "الرحمن", "الواقعة", "الحديد", "المجادلة", "الحشر", "الممتحنة",
    "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق", "التحريم", "الملك", "القلم", "الحاقة", "المعارج",
    "نوح", "الجن", "المزمل", "المدثر", "القيامة", "الانسان", "المرسلات", "النبإ", "النازعات", "عبس",
    "التكوير", "الإنفطار", "المطففين", "الإنشقاق", "البروج", "الطارق", "الأعلى", "الغاشية", "الفجر", "البلد",
    "الشمس", "الليل", "الضحى", "الشرح", "التين", "العلق", "القدر", "البينة", "الزلزلة", "العاديات",
    "القارعة", "التكاثر", "العصر", "الهمزة", "الفيل", "قريش", "الماعون", "الكوثر", "الكافرون", "النصر",
    "المسد", "الإخلاص", "الفلق", "الناس",
)
SURAH_ALIASES = {
    "براءة": 9, "بني إسرائيل": 17, "المؤمنين": 23, "المؤمن": 40, "حم السجدة": 41, "القتال": 47, "المنافقين": 63,
    "الدهر": 76, "عم": 78, "الانشراح": 94, "اقرأ": 96, "الزلزال": 99, "الكافرين": 109, "اللهب": 111, "تبت": 111,
    "التوحيد": 112,
}
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".opus", ".ogg", ".flac", ".aac")

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


def _name_key(name: str) -> str:
    # بعض أسماء الملفات تكتب الهمزة حرفاً مستقلاً بعد الألف (ا + ٔ)؛ NFKC يجمعهما في أ
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[\u064B-\u0655\u0670\u0640\s]", "", name)
    name = re.sub("[أإآٱء]", "ا", name).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return name[2:] if name.startswith("ال") and len(name) > 3 else name


_SURAH_KEYS = {_name_key(n): i for i, n in enumerate(SURAH_NAMES, 1)} | {_name_key(n): i for n, i in SURAH_ALIASES.items()}


def is_local(source: str) -> bool:
    return not re.match(r"https?://", source)


def file_name(source: str) -> str:
    return Path(source if is_local(source) else urllib.parse.urlparse(source).path).name


def surah_from_url(url: str) -> int:
    """من اسم الملف: اسم السورة بعد كلمة «سورة» (… | سورة عبس.mp3)، أو رقم في آخره (002.mp3) أو أوله (002 - …)."""
    name = Path(file_name(url)).stem
    named = re.search(r"سور[ةه]\s*(.+)$", name)
    if named and _name_key(named.group(1)) in _SURAH_KEYS:
        return _SURAH_KEYS[_name_key(named.group(1))]
    for digits in (re.search(r"(\d{1,3})$", name.strip()), re.match(r"\s*(\d{1,3})(?!\d)", name)):
        if digits and 1 <= int(digits.group(1)) <= 114:
            return int(digits.group(1))
    if _name_key(name) in _SURAH_KEYS:
        return _SURAH_KEYS[_name_key(name)]
    raise ValueError(f"Cannot tell the surah from the file name: {url}")


def _local_folder(folder: Path, surahs: str) -> list[tuple[int, str]]:
    wanted = set(parse_surahs(surahs))
    found, unknown = {}, []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            surah = surah_from_url(str(path))
        except ValueError:
            unknown.append(path.name)
            continue
        if surah in found:
            raise ValueError(f"Two files for surah {surah}: {Path(found[surah]).name} | {path.name}")
        found[surah] = str(path)
    if unknown:
        raise ValueError("Cannot tell the surah from these file names (rename them): " + ", ".join(unknown))
    return [(n, found[n]) for n in sorted(found) if n in wanted]


def parse_sources(text: str, surahs: str = "1-114") -> list[tuple[int, str]]:
    """كل سطر رابط ملف (رقم السورة من اسمه) أو رابط مجلد ينتهي بـ / (تُكمَّل بـ 001.mp3 ... حسب surahs)،
    أو مسار مجلد/ملف محلي (مثل Google Drive) والسورة من اسم كل ملف."""
    sources = []
    for line in text.splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        if is_local(url):
            if not Path(url).exists():
                raise ValueError(f"Not found: {url}")
            sources += _local_folder(Path(url), surahs) if Path(url).is_dir() else [(surah_from_url(url), url)]
        elif url.endswith("/"):
            sources += [(n, f"{url}{n:03d}.mp3") for n in parse_surahs(surahs)]
        else:
            sources.append((surah_from_url(url), url))
    return sources


def reciter_slug(url: str) -> str:
    """مجلد القارئ من الرابط: .../audio/abdulrahman-sudais/r1/002.mp3 ← abdulrahman-sudais_r1،
    ومن الملف المحلي اسم مجلده."""
    if is_local(url):
        slug = Path(url).parent.name
    else:
        parts = [p for p in urllib.parse.urlparse(url).path.split("/")[:-1] if p]
        if parts and parts[0] == "audio":
            parts = parts[1:]
        slug = "_".join(parts) or urllib.parse.urlparse(url).netloc
    return re.sub(r"[^\w.-]+", "-", slug).strip("-") or "audio"


def output_path(root: Path, engine: str, url: str, surah: int | None = None) -> Path:
    return Path(root) / engine / reciter_slug(url) / f"{surah or surah_from_url(url):03d}.json"


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
        "audio": file_name(url),
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
    pending = [(s, u) for s, u in sources if not is_done(output_path(out_root, engine, u, s))]
    print(f"{len(sources) - len(pending)} done before, {len(pending)} to go")
    failures = []
    for index, (surah, url) in enumerate(pending, 1):
        target = output_path(out_root, engine, url, surah)
        with tempfile.TemporaryDirectory() as folder:
            try:
                path = Path(url) if is_local(url) else download(url, Path(folder))
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



LISTEN_ENGINES = ("othman-engine", "munajjam-whisperx")
REFERENCE = "mp3quran"


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pad_times(spans: dict[int, tuple[float, float]], duration: float | None, max_pad: float) -> dict:
    """يمد كل آية في السكتة قبلها وبعدها بنصفها، بحد أقصى max_pad ثانية، فلا تدخل في الآية المجاورة.
    spans تشمل البسملة (0) إن وُجدت لأنها تحد الآية الأولى، ولا تُرجَع."""
    ordered = sorted(spans.items(), key=lambda item: item[1][0])
    padded = {}
    for i, (ayah, (start, end)) in enumerate(ordered):
        before = ordered[i - 1][1][1] if i else 0.0
        after = ordered[i + 1][1][0] if i + 1 < len(ordered) else (duration or end)
        if ayah > 0:
            padded[ayah] = (start - min(max_pad, max(0.0, (start - before) / 2)),
                            end + min(max_pad, max(0.0, (after - end) / 2)))
    return padded


def _engine_spans(result: dict, pad: float) -> dict[int, tuple[float, float]]:
    spans = {row["ayah"]: (row["start"], row["end"]) for row in result["ayahs"] if row["start"] is not None}
    return pad_times(spans, result.get("meta", {}).get("audio_seconds"), pad)


def listen_queue(out_root, reciters: str = "", surahs: str = "", threshold: float = 0.5, random_share: float = 0.2,
                 pad: float = 0.5, seed: int = 0, reference=mp3quran_reference) -> list[dict]:
    """آيات الاستماع الأعمى من المحركين (بهامش pad) وتوقيت mp3quran إن وُجد للقارئ.
    كل الآيات المختلف عليها (أكبر فرق في البداية أو النهاية أكثر من threshold) مع عينة عشوائية ثابتة (seed)
    من الباقي، مخلوطة بترتيب عشوائي ثابت حتى لا يتتابع قارئ واحد أو سورة واحدة."""
    wanted_surahs = set(parse_surahs(surahs)) if surahs.strip() else None
    wanted_reciters = {r.strip() for r in reciters.replace("،", ",").split(",") if r.strip()}
    disputed, agreed = [], []
    for path in sorted(Path(out_root, LISTEN_ENGINES[0]).glob("*/*.json")):
        reciter = path.parent.name
        other = Path(out_root, LISTEN_ENGINES[1], reciter, path.name)
        if wanted_reciters and reciter not in wanted_reciters or not other.exists():
            continue
        ours = _read(path)
        if wanted_surahs and ours["surah"] not in wanted_surahs:
            continue
        times = {LISTEN_ENGINES[0]: _engine_spans(ours, pad), LISTEN_ENGINES[1]: _engine_spans(_read(other), pad)}
        if ours.get("mp3quran_read"):
            times[REFERENCE] = reference(ours["mp3quran_read"], ours["surah"])
        for ayah in sorted(set.intersection(*(set(t) for t in times.values()))):
            spans = {source: times[source][ayah] for source in times}
            spread = max(max(s[i] for s in spans.values()) - min(s[i] for s in spans.values()) for i in (0, 1))
            item = {"id": f"{reciter}/{ours['surah']}/{ayah}", "reciter": reciter, "surah": ours["surah"],
                    "ayah": ayah, "audio_url": ours["audio_url"], "spread": round(spread, 3),
                    "times": {source: [round(a, 3), round(b, 3)] for source, (a, b) in spans.items()}}
            (disputed if spread > threshold else agreed).append(item)
    rng = random.Random(seed)
    for item in disputed:
        item["bucket"] = "disputed"
    sample = rng.sample(agreed, round(len(agreed) * random_share))
    for item in sample:
        item["bucket"] = "random"
    queue = disputed + sample
    rng.shuffle(queue)
    return queue


def load_votes(path) -> dict:
    try:
        return _read(path)
    except (OSError, ValueError):
        return {}


def record_vote(path, votes: dict, item: dict, winners: list[str], order: list[str]) -> None:
    """winners: مصدر أو أكثر من مصادر الآية (المتساوية في الأفضلية). order: المصادر بترتيب أ، ب، ج كما ظهرت."""
    sources = sorted(item["times"])
    if not winners or not set(winners) <= set(sources) or sorted(order) != sources:
        raise ValueError(f"Bad vote: {winners} {order}")
    votes[item["id"]] = {key: item[key] for key in ("reciter", "surah", "ayah", "bucket", "spread")}
    votes[item["id"]].update(winners=sorted(set(winners)), order=order, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    save_json(Path(path), votes)


def vote_points(votes: dict) -> list[dict]:
    """صف لكل (صوت، مصدر): نقطة الصوت تتقاسمها المصادر الفائزة فيه."""
    rows = []
    for vote in votes.values():
        for source in vote["order"]:
            share = 1 / len(vote["winners"]) if source in vote["winners"] else 0.0
            rows.append({"reciter": vote["reciter"], "surah": vote["surah"], "bucket": vote["bucket"],
                         "source": source, "points": share, "all_equal": len(vote["winners"]) == len(vote["order"])})
    return rows


class _AudioHandler(http.server.BaseHTTPRequestHandler):
    """يخدم الملفات المسجلة فقط، مع دعم Range: المتصفح لا يقفز داخل ملف صوت بدونه."""
    files: dict = {}

    def do_GET(self):
        path = self.files.get(self.path.split("?")[0].lstrip("/"))
        if not path:
            self.send_error(404)
            return
        size = os.path.getsize(path)
        first, last = 0, size - 1
        wanted = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if wanted and (wanted.group(1) or wanted.group(2)):
            if wanted.group(1):
                first = int(wanted.group(1))
                last = min(int(wanted.group(2)), size - 1) if wanted.group(2) else size - 1
            else:
                first = max(size - int(wanted.group(2)), 0)
            if first > last:
                self.send_error(416)
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        else:
            self.send_response(200)
        kind = {".wav": "audio/wav", ".m4a": "audio/mp4", ".opus": "audio/ogg", ".ogg": "audio/ogg", ".flac": "audio/flac",
                ".aac": "audio/aac"}
        self.send_header("Content-Type", kind.get(Path(path).suffix.lower(), "audio/mpeg"))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(last - first + 1))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(path, "rb") as audio:
            audio.seek(first)
            remaining = last - first + 1
            while remaining > 0:
                chunk = audio.read(min(remaining, 1 << 20))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):  # المتصفح يقطع الطلب عند القفز لمكان آخر
                    return
                remaining -= len(chunk)

    def log_message(self, *args):
        pass


_server = None


def serve_local_audio(items: list[dict], port: int = 8765) -> list[str]:
    """للملفات المحلية (Drive): خادم صغير في الخلفية. يرجع مسارات الملفات المسجلة بنفس ترتيب أرقامها؛
    رابط الملف i هو <عنوان الخادم>/a<i>، ويُستبدل في audio_url بعد معرفة العنوان العام."""
    global _server
    paths = sorted({item["audio_url"] for item in items if is_local(item["audio_url"])})
    _AudioHandler.files = {f"a{i}": path for i, path in enumerate(paths)}
    if paths and _server is None:
        _server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _AudioHandler)
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    return paths


def use_served_audio(items: list[dict], paths: list[str], base_url: str) -> None:
    index = {path: i for i, path in enumerate(paths)}
    for item in items:
        if item["audio_url"] in index:
            item["audio_url"] = f"{base_url.rstrip('/')}/a{index[item['audio_url']]}"


def listen_page(items: list[dict]) -> str:
    template = (Path(__file__).parent / "listen.html").read_text(encoding="utf-8")
    # "</" داخل JSON قد يغلق وسم السكربت مبكراً
    return template.replace("__ITEMS__", json.dumps(items, ensure_ascii=False).replace("</", "<\\/"))
