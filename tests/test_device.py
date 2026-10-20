import pytest

from othman_engine.asr import fastconformer


def test_providers(monkeypatch):
    assert fastconformer._providers("cpu") == ["CPUExecutionProvider"]
    monkeypatch.setattr(fastconformer.ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    assert fastconformer._providers("auto") == ["CPUExecutionProvider"]
    with pytest.raises(RuntimeError):
        fastconformer._providers("cuda")
    with pytest.raises(ValueError):
        fastconformer._providers("gpu")
    monkeypatch.setattr(fastconformer.ort, "get_available_providers",
                        lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setattr(fastconformer.ort, "preload_dlls", lambda: None, raising=False)
    assert fastconformer._providers("auto")[0][0] == "CUDAExecutionProvider"
