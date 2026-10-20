import numpy as np
import onnxruntime as ort
import sentencepiece as spm

from othman_engine import config
from othman_engine.asr.base import Word
from othman_engine.asr.features import LogMelExtractor

BLANK_ID = 1024
FRAME_SECONDS = 0.08  # الموديل يختزل 8 إطارات من 10ms في إطار واحد
WORD_BOUNDARY = "▁"

# الموديل تدرّب على آيات مفردة، وفي المقاطع الطويلة (أكثر من ~20 ثانية) يتجاهل أجزاء كاملة،
# لذلك نقطع الصوت عند أهدأ النقاط (غالباً الوقف بين الآيات) إلى مقاطع قصيرة
CHUNK_MAX_SECONDS = 12
CHUNK_MIN_SECONDS = 2
QUIET_WINDOW_SECONDS = 0.3
REFILL_GAP_SECONDS = 2.5

def _providers(device: str) -> list:
    """device: "auto" (كرت الشاشة إن وُجد onnxruntime-gpu و CUDA) أو "cpu" أو "cuda"."""
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device not in ("auto", "cuda"):
        raise ValueError(f"Unknown device: {device}")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        if device == "cuda":
            raise RuntimeError("CUDA is not available: install onnxruntime-gpu on a machine with an NVIDIA GPU")
        return ["CPUExecutionProvider"]
    if hasattr(ort, "preload_dlls"):
        # يحمّل مكتبات CUDA/cuDNN من حزم pip (nvidia-*) إن وُجدت، كما في Colab
        ort.preload_dlls()
    # طول كل مقطع مختلف؛ البحث الشامل عن خوارزمية الالتفاف (الافتراضي) يتكرر مع كل طول جديد ويبطئ كثيراً
    return [("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"}), "CPUExecutionProvider"]


class FastConformer:
    def __init__(self, model_file=config.MODEL_FILE, tokenizer_file=config.TOKENIZER_FILE, threads=None,
                 device="auto"):
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(model_file), options, providers=_providers(device))
        self.device = "cuda" if self.session.get_providers()[0] == "CUDAExecutionProvider" else "cpu"
        self.tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer_file))
        self.features = LogMelExtractor()

    def transcribe(self, audio: np.ndarray) -> list[Word]:
        words = self._transcribe_span(audio, 0, len(audio))
        return self._refill_gaps(audio, words)

    def _transcribe_span(self, audio: np.ndarray, begin: int, end: int) -> list[Word]:
        words = []
        for start, stop in split_points(audio[begin:end]):
            offset = (begin + start) / config.SAMPLE_RATE
            words += [
                Word(w.text, w.start + offset, w.end + offset)
                for w in self._transcribe_chunk(audio[begin + start : begin + stop])
            ]
        return words

    def _refill_gaps(self, audio: np.ndarray, words: list[Word]) -> list[Word]:
        """تمريرة ثانية على الفجوات الطويلة بين الكلمات.

        حين يحوي المقطع آيتين قصيرتين متشابهتين (مثل "ملك الناس" ثم "إله الناس") قد يكتب الموديل
        إحداهما فقط؛ نفس الجزء وحده يُفرَّغ صحيحاً. الفجوة الصامتة فعلاً لا تُرجع شيئاً.
        """
        sr = config.SAMPLE_RATE
        bounds = [0.0, *[t for w in words for t in (w.start, w.end)], len(audio) / sr]
        refilled = []
        for gap_start, gap_end in zip(bounds[::2], bounds[1::2]):
            if gap_end - gap_start >= REFILL_GAP_SECONDS:
                refilled += self._transcribe_span(audio, int(gap_start * sr), int(gap_end * sr))
        return sorted(words + refilled, key=lambda w: w.start)

    def _transcribe_chunk(self, audio: np.ndarray) -> list[Word]:
        if len(audio) < config.SAMPLE_RATE * 0.2:
            return []
        feats = self.features(audio)[None]
        logprobs, = self.session.run(
            ["logprobs"], {"audio_signal": feats, "length": np.array([feats.shape[2]], dtype=np.int64)}
        )
        return self._ctc_words(logprobs[0].argmax(axis=-1))

    def _ctc_words(self, token_ids: np.ndarray) -> list[Word]:
        # كل كلمة: [القطع, أول إطار, آخر إطار]
        spans = []
        previous = BLANK_ID
        for frame, token in enumerate(token_ids.tolist()):
            if token != BLANK_ID:
                if token != previous:
                    piece = self.tokenizer.id_to_piece(token)
                    if piece.startswith(WORD_BOUNDARY) or not spans:
                        spans.append([[token], frame, frame])
                    else:
                        spans[-1][0].append(token)
                spans[-1][2] = frame
            previous = token
        return [
            Word(self.tokenizer.decode(tokens), first * FRAME_SECONDS, (last + 1) * FRAME_SECONDS)
            for tokens, first, last in spans
        ]


def split_points(audio: np.ndarray) -> list[tuple[int, int]]:
    """يقسم الصوت تكرارياً عند أهدأ نقطة حتى لا يتجاوز أي مقطع CHUNK_MAX_SECONDS."""
    sr = config.SAMPLE_RATE
    hop = int(sr * QUIET_WINDOW_SECONDS) // 4
    frames = len(audio) // hop
    energy = np.square(audio[: frames * hop]).reshape(frames, hop).mean(axis=1)
    smoothed = np.convolve(energy, np.ones(4) / 4, mode="same")

    def split(start, end):
        if end - start <= CHUNK_MAX_SECONDS * sr:
            return [(start, end)]
        lo = (start + CHUNK_MIN_SECONDS * sr) // hop
        hi = (end - CHUNK_MIN_SECONDS * sr) // hop
        cut = (lo + int(smoothed[lo:hi].argmin())) * hop
        return split(start, cut) + split(cut, end)

    return split(0, len(audio))
