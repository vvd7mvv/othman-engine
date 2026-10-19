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
