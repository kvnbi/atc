import numpy as np

RATE = 16000
LOW_HZ = 350.0
HIGH_HZ = 2800.0
ORDER = 4
NOISE_DB = -40.0
DRIVE = 2.0
PEAK = 0.7
QUIET = 0.05
LEAD_SECONDS = 0.05
TAIL_SECONDS = 0.12


def process(pcm, rng=None):
    rng = rng or np.random.default_rng()
    speech = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0
    if speech.size == 0:
        return pcm
    sigma = 10 ** (NOISE_DB / 20)
    noisy = speech + rng.normal(0.0, sigma, speech.size)
    freq = np.maximum(np.fft.rfftfreq(noisy.size, 1.0 / RATE), 1.0)
    gain = 1.0 / np.sqrt(1.0 + (LOW_HZ / freq) ** (2 * ORDER)) / np.sqrt(1.0 + (freq / HIGH_HZ) ** (2 * ORDER))
    band = np.fft.irfft(np.fft.rfft(noisy) * gain, noisy.size)
    band = np.tanh(band * DRIVE) / np.tanh(DRIVE)
    if np.abs(speech).max() > QUIET:
        band *= PEAK / max(np.abs(band).max(), 1e-9)
    lead = rng.normal(0.0, sigma, int(LEAD_SECONDS * RATE))
    tail_size = int(TAIL_SECONDS * RATE)
    tail = rng.normal(0.0, sigma * 3, tail_size) * np.linspace(1.0, 0.0, tail_size)
    out = np.clip(np.concatenate([lead, band, tail]), -1.0, 1.0)
    return (out * 32767).astype(np.int16).tobytes()
