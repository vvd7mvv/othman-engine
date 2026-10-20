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



def test_surah_from_local_names():
    name = "/d/المصحف المرتل للقارئ عبدالعزيز التركي | سورة {}.mp3"
    for number, surah in enumerate(timings.SURAH_NAMES, 1):
        assert timings.surah_from_url(name.format(surah)) == number
    assert [timings.surah_from_url(name.format(n)) for n in ("سبأ", "الإنسان", "آل عمران", "الانفطار", "عم")] == [
        34, 76, 3, 82, 78]
    assert timings.surah_from_url("/d/002.wav") == 2
    with pytest.raises(ValueError):
        timings.surah_from_url("/d/تلاوة.mp3")


def test_parse_local_folder(tmp_path):
    folder = tmp_path / "عبدالعزيز التركي"
    folder.mkdir()
    for name in ("التلاوة | سورة عبس.mp3", "التلاوة | سورة الناس.wav", "cover.jpg"):
        (folder / name).write_bytes(b"x")
    sources = timings.parse_sources(str(folder), "1-114")
    assert [s for s, _ in sources] == [80, 114]
    assert timings.output_path(tmp_path, "e", sources[0][1], 80) == tmp_path / "e" / "عبدالعزيز-التركي" / "080.json"
    assert timings.parse_sources(str(folder), "80") == sources[:1]
    (folder / "بدون اسم.mp3").write_bytes(b"x")
    with pytest.raises(ValueError, match="بدون اسم"):
        timings.parse_sources(str(folder))


def test_pad_times():
    spans = {0: (0.5, 3.0), 1: (4.0, 6.0), 2: (6.0, 9.0), 3: (11.0, 12.0)}
    assert timings.pad_times(spans, 12.4, 0.5) == {1: (3.5, 6.0), 2: (6.0, 9.5), 3: (10.5, 12.2)}


def _write_result(root, engine, surah, ayahs):
    rows = [{"ayah": n, "start": s, "end": e, "confidence": 1} for n, (s, e) in ayahs.items()]
    path = root / engine / "abdulrahman-sudais_r1" / f"{surah:03d}.json"
    timings.save_json(path, {"surah": surah, "audio_url": SUDAIS + f"{surah:03d}.mp3", "mp3quran_read": 54,
                             "ayahs": rows, "meta": {"audio_seconds": 10}})


def test_listen_queue(tmp_path):
    _write_result(tmp_path, "othman-engine", 97, {0: (0, 1), 1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (7, 8), 5: (9, 10)})
    _write_result(tmp_path, "munajjam-whisperx", 97, {1: (1.1, 2), 2: (3, 5), 3: (5, 6), 4: (None, None), 5: (9, 10)})
    reference = lambda read, surah: {1: (1, 2.2), 2: (3, 4), 3: (5.6, 6), 4: (7, 8), 5: (9, 10)}
    queue = timings.listen_queue(tmp_path, reference=reference, random_share=0.5, pad=0)
    assert sorted((i["ayah"], i["bucket"], i["spread"]) for i in queue if i["bucket"] == "disputed") == [
        (2, "disputed", 1.0), (3, "disputed", 0.6)]
    assert len(queue) == 3 and {i["ayah"] for i in queue if i["bucket"] == "random"} <= {1, 5}
    two = next(i for i in queue if i["ayah"] == 2)
    assert two["times"] == {"othman-engine": [3, 4], "munajjam-whisperx": [3, 5], "mp3quran": [3, 4]}
    assert two["id"] == "abdulrahman-sudais_r1/97/2" and two["audio_url"].endswith("097.mp3")
    assert timings.listen_queue(tmp_path, reference=reference, random_share=0.5, pad=0) == queue
    padded = timings.listen_queue(tmp_path, reference=reference, random_share=0, pad=0.5)
    assert next(i for i in padded if i["ayah"] == 2)["times"]["othman-engine"] == [2.5, 4.5]
    assert timings.listen_queue(tmp_path, surahs="1-96", reference=reference) == []
    assert timings.listen_queue(tmp_path, reciters="other_r1", reference=reference) == []


def test_record_vote_and_points(tmp_path):
    path = tmp_path / "votes.json"
    item = {"id": "x/97/2", "reciter": "x", "surah": 97, "ayah": 2, "bucket": "disputed", "spread": 1.0,
            "times": {"mp3quran": [0, 1], "othman-engine": [0, 1], "munajjam-whisperx": [0, 1]}}
    order = ["mp3quran", "othman-engine", "munajjam-whisperx"]
    votes = timings.load_votes(path)
    timings.record_vote(path, votes, item, ["othman-engine", "mp3quran"], order)
    saved = timings.load_votes(path)["x/97/2"]
    assert saved["winners"] == ["mp3quran", "othman-engine"] and saved["order"] == order
    points = {row["source"]: row["points"] for row in timings.vote_points({"v": saved})}
    assert points == {"mp3quran": 0.5, "othman-engine": 0.5, "munajjam-whisperx": 0.0}
    for winners in ([], ["munajjam"]):
        with pytest.raises(ValueError):
            timings.record_vote(path, votes, item, winners, order)


def test_serve_local_audio(tmp_path):
    audio = tmp_path / "سورة عبس.mp3"
    audio.write_bytes(bytes(range(256)) * 4)
    items = [{"audio_url": str(audio)}, {"audio_url": SUDAIS + "097.mp3"}]
    paths = timings.serve_local_audio(items, port=8799)
    timings.use_served_audio(items, paths, "http://127.0.0.1:8799/")
    assert items[0]["audio_url"] == "http://127.0.0.1:8799/a0" and items[1]["audio_url"].startswith("https://")
    request = timings.urllib.request.Request(items[0]["audio_url"], headers={"Range": "bytes=10-19"})
    opener = timings.urllib.request.build_opener(timings.urllib.request.ProxyHandler({}))
    with opener.open(request) as response:
        assert response.status == 206 and response.read() == bytes(range(10, 20))
        assert response.headers["Content-Range"] == "bytes 10-19/1024"


def test_listen_page_escapes_script():
    page = timings.listen_page([{"id": "</script><b>"}])
    assert "__ITEMS__" not in page and "</script><b>" not in page
