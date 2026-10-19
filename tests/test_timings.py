import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))
import timings  # noqa: E402

SUDAIS = "https://cdn.mp3quran.net/audio/abdulrahman-sudais/r1/"


def test_ayah_counts():
    assert len(timings.AYAH_COUNTS) == 114
    assert sum(timings.AYAH_COUNTS) == 6236


def test_parse_surahs():
    assert timings.parse_surahs("78-80, 2,2") == [2, 78, 79, 80]
    assert len(timings.parse_surahs("1-114")) == 114
    with pytest.raises(ValueError):
        timings.parse_surahs("0-3")


def test_parse_sources():
    text = f"""
    # comment
    {SUDAIS}
    https://example.com/qari/002.mp3
    """
    assert timings.parse_sources(text, "1,114") == [
        (1, SUDAIS + "001.mp3"), (114, SUDAIS + "114.mp3"), (2, "https://example.com/qari/002.mp3")]
    with pytest.raises(ValueError):
        timings.parse_sources("https://example.com/fatiha.mp3")


def test_output_path():
    path = timings.output_path(Path("/d"), "othman-engine", SUDAIS + "002.mp3")
    assert path == Path("/d/othman-engine/abdulrahman-sudais_r1/002.json")


def test_mp3quran_read_id(monkeypatch):
    monkeypatch.setattr(timings, "_reads_cache", [{"id": 54, "folder_url": SUDAIS}])
    assert timings.mp3quran_read_id(SUDAIS.replace("https:", "http:") + "002.mp3") == 54
    assert timings.mp3quran_read_id(SUDAIS + "002.mp3") == 54
    assert timings.mp3quran_read_id("https://example.com/audio/abdulrahman-sudais/r1/002.mp3") is None


def test_build_result_fills_missing(monkeypatch):
    monkeypatch.setattr(timings, "_reads_cache", [])
    result = timings.build_result(97, SUDAIS + "097.mp3", {0: (0, 2, 1), 1: (2.5, 7.123456, 1.2)}, {"seconds": 1})
    assert result["surah"] == 97 and result["audio"] == "097.mp3" and result["audio_url"].endswith("097.mp3")
    assert [row["ayah"] for row in result["ayahs"]] == [0, 1, 2, 3, 4, 5]
    assert result["ayahs"][1] == {"ayah": 1, "start": 2.5, "end": 7.123, "confidence": 1.0}
    assert result["ayahs"][2] == {"ayah": 2, "start": None, "end": None, "confidence": 0.0}


def test_save_and_is_done(tmp_path):
    target = tmp_path / "a" / "002.json"
    assert not timings.is_done(target)
    target.parent.mkdir()
    target.write_text('{"ayahs": [')
    assert not timings.is_done(target)
    timings.save_json(target, {"ayahs": [{"ayah": 1}]})
    assert timings.is_done(target) and json.loads(target.read_text())["ayahs"]
    assert not list(target.parent.glob("*.part"))


def test_compare():
    result = {"ayahs": [
        {"ayah": 0, "start": 0, "end": 1, "confidence": 1},
        {"ayah": 1, "start": 1.2, "end": 4.0, "confidence": 1},
        {"ayah": 2, "start": 6.0, "end": 8.0, "confidence": 1},
        {"ayah": 3, "start": None, "end": None, "confidence": 0},
    ]}
    reference = {1: (1.0, 4.5), 2: (4.5, 8.0), 3: (8.0, 9.0), 4: (9.0, 10.0)}
    metrics = timings.compare(result, reference)
    assert metrics == {"ayahs": 4, "missing": 2, "mean_start_diff": 0.85, "over_1s_pct": 75.0, "mean_end_diff": 0.25}


def _write_result(root, engine, surah, ayahs):
    rows = [{"ayah": n, "start": s, "end": e, "confidence": 1} for n, (s, e) in ayahs.items()]
    path = root / engine / "abdulrahman-sudais_r1" / f"{surah:03d}.json"
    timings.save_json(path, {"surah": surah, "audio_url": SUDAIS + f"{surah:03d}.mp3", "mp3quran_read": 54,
                             "ayahs": rows})


def test_listen_queue(tmp_path):
    _write_result(tmp_path, "othman-engine", 97, {0: (0, 1), 1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (7, 8), 5: (9, 10)})
    _write_result(tmp_path, "munajjam-whisperx", 97, {1: (1.1, 2), 2: (3, 5), 3: (5, 6), 4: (None, None), 5: (9, 10)})
    reference = lambda read, surah: {1: (1, 2.2), 2: (3, 4), 3: (5.6, 6), 4: (7, 8), 5: (9, 10)}
    queue = timings.listen_queue(tmp_path, reference=reference, random_share=0.5)
    assert [(i["ayah"], i["bucket"], i["spread"]) for i in queue[:2]] == [(2, "disputed", 1.0), (3, "disputed", 0.6)]
    assert len(queue) == 3 and queue[2]["bucket"] == "random" and queue[2]["ayah"] in (1, 5)
    assert queue[0]["times"] == {"othman-engine": [3, 4], "munajjam-whisperx": [3, 5], "mp3quran": [3, 4]}
    assert queue[0]["id"] == "abdulrahman-sudais_r1/97/2" and queue[0]["audio_url"].endswith("097.mp3")
    assert timings.listen_queue(tmp_path, reference=reference, random_share=0.5) == queue
    assert timings.listen_queue(tmp_path, surahs="1-96", reference=reference) == []
    assert timings.listen_queue(tmp_path, reciters="other_r1", reference=reference) == []


def test_record_vote(tmp_path):
    path = tmp_path / "votes.json"
    item = {"id": "x/97/2", "reciter": "x", "surah": 97, "ayah": 2, "bucket": "disputed", "spread": 1.0}
    votes = timings.load_votes(path)
    timings.record_vote(path, votes, item, "mp3quran", ["mp3quran", "othman-engine", "munajjam-whisperx"])
    saved = timings.load_votes(path)["x/97/2"]
    assert saved["choice"] == "mp3quran" and saved["bucket"] == "disputed" and saved["order"][0] == "mp3quran"
    with pytest.raises(ValueError):
        timings.record_vote(path, votes, item, "munajjam", ["mp3quran", "othman-engine", "munajjam-whisperx"])


def test_listen_page_escapes_script():
    page = timings.listen_page([{"id": "</script><b>"}])
    assert "__ITEMS__" not in page and "</script><b>" not in page
