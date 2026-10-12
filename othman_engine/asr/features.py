"""Log-mel features for FastConformer-Quran.

Copied verbatim from tajweed/aligner.py (LogMelExtractor, _slaney_mel_filterbank)
in Muno459/fastconformer-quran, NPL-1.1. Kept as-is because the model was
trained and evaluated on exactly these features; do not "fix" it to match NeMo.
"""
import numpy as np


class LogMelExtractor:
    """80-dim log-mel matching the FastConformer preprocessor config:
        sample_rate=16000, window=0.025, hop=0.010, n_fft=512, n_mels=80,
        log=True, normalize='per_feature', dither=1e-5.

    NeMo uses the Slaney mel filterbank convention. We replicate it with numpy
    so we don't pull in torchaudio here.
    """
    def __init__(
        self,
        sample_rate: int = 16000,
        window_s: float = 0.025,
        hop_s: float = 0.010,
        n_fft: int = 512,
        n_mels: int = 80,
        dither: float = 1e-5,
    ):
        self.sr = sample_rate
        self.win_n = int(round(sample_rate * window_s))
        self.hop_n = int(round(sample_rate * hop_s))
        self.n_fft = n_fft
        self.n_mels = n_mels
        self.dither = dither
        self.window = np.hanning(self.win_n).astype(np.float32)
        # Slaney mel filterbank: linear up to 1 kHz, log above
        self.mel_fb = _slaney_mel_filterbank(
            sample_rate=sample_rate, n_fft=n_fft, n_mels=n_mels, fmin=0.0, fmax=sample_rate / 2
        )

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        """Returns (80, T_frames) float32, per-feature normalised."""
        x = audio.astype(np.float32, copy=True)
        if self.dither > 0:
            x = x + self.dither * np.random.RandomState(0).randn(len(x)).astype(np.float32)
        # Pre-emphasis is NOT applied in NeMo's preprocessor by default.
        # Pad to ensure last frame fits
        pad = self.win_n - 1
        x = np.pad(x, (0, max(0, pad)), mode="constant")
        n_frames = max(1, 1 + (len(x) - self.win_n) // self.hop_n)
        # STFT
        frames = np.lib.stride_tricks.as_strided(
            x,
            shape=(n_frames, self.win_n),
            strides=(x.strides[0] * self.hop_n, x.strides[0]),
        ).copy()
        frames = frames * self.window
        # FFT magnitude squared (power spectrogram)
        spec = np.fft.rfft(frames, n=self.n_fft, axis=1)
        power = np.real(spec * np.conj(spec)).astype(np.float32)  # (T, n_fft/2+1)
        # Mel projection
        mel = power @ self.mel_fb.T  # (T, n_mels)
        # log: NeMo uses log(x + epsilon) with eps=2^-24
        mel = np.log(mel + 2 ** -24)
        # Transpose to (n_mels, T)
        feats = mel.T
        # per_feature normalisation
        mean = feats.mean(axis=1, keepdims=True)
        std = feats.std(axis=1, keepdims=True) + 1e-5
        feats = (feats - mean) / std
        return feats.astype(np.float32)


def _slaney_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int, fmin: float, fmax: float) -> np.ndarray:
    """Reproduces librosa/slaney-style mel filterbank in numpy."""
    def hz_to_mel(f):
        f_min = 0.0
        f_sp = 200.0 / 3
        min_log_hz = 1000.0
        min_log_mel = (min_log_hz - f_min) / f_sp
        logstep = np.log(6.4) / 27.0
        f_safe = np.maximum(f, 1e-3)  # avoid log(0) at DC bin
        return np.where(
            f_safe < min_log_hz,
            (f_safe - f_min) / f_sp,
            min_log_mel + np.log(f_safe / min_log_hz) / logstep,
        )

    def mel_to_hz(m: float) -> float:
        f_min = 0.0
        f_sp = 200.0 / 3
        min_log_hz = 1000.0
        min_log_mel = (min_log_hz - f_min) / f_sp
        logstep = np.log(6.4) / 27.0
        return np.where(
            m < min_log_mel,
            f_min + f_sp * m,
            min_log_hz * np.exp(logstep * (m - min_log_mel)),
        )

    mel_min = hz_to_mel(fmin)
    mel_max = hz_to_mel(fmax)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = mel_to_hz(mel_points)
    bin_freqs = np.linspace(0, sample_rate / 2, n_fft // 2 + 1)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        lo, ctr, hi = hz_points[i], hz_points[i + 1], hz_points[i + 2]
        left = (bin_freqs - lo) / (ctr - lo + 1e-12)
        right = (hi - bin_freqs) / (hi - ctr + 1e-12)
        fb[i] = np.maximum(0, np.minimum(left, right))
        # Slaney normalisation: 2/(hi-lo)
        enorm = 2.0 / (hi - lo + 1e-12)
        fb[i] *= enorm
    return fb
