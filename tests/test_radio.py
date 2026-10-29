import numpy as np

from atc.audio import radio


def tones(*hertz, seconds=1.0):
    t = np.arange(int(seconds * radio.RATE)) / radio.RATE
    wave = sum(np.sin(2 * np.pi * h * t) for h in hertz) / len(hertz)
    return (wave * 20000).astype(np.int16).tobytes()


def level(pcm, hertz):
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    spectrum = np.abs(np.fft.rfft(samples))
    freq = np.fft.rfftfreq(samples.size, 1 / radio.RATE)
    return spectrum[np.argmin(np.abs(freq - hertz))]


def test_keeps_the_voice_band_and_cuts_the_rest():
    out = radio.process(tones(100, 1000, 6000), np.random.default_rng(1))
    kept = level(out, 1000)
    assert kept > 10 * level(out, 100)
    assert kept > 10 * level(out, 6000)


def test_adds_lead_noise_and_squelch_tail():
    pcm = tones(1000)
    out = radio.process(pcm, np.random.default_rng(1))
    extra = int(radio.LEAD_SECONDS * radio.RATE) + int(radio.TAIL_SECONDS * radio.RATE)
    assert len(out) == len(pcm) + extra * 2


def test_level_is_bounded_and_deterministic_with_a_seed():
    pcm = tones(500, 1500)
    a = radio.process(pcm, np.random.default_rng(7))
    b = radio.process(pcm, np.random.default_rng(7))
    assert a == b
    assert np.abs(np.frombuffer(a, dtype=np.int16)).max() <= 32767 * 0.8


def test_silence_and_empty_input():
    assert radio.process(b"") == b""
    out = np.frombuffer(radio.process(bytes(32000), np.random.default_rng(1)), dtype=np.int16)
    assert np.isfinite(out).all() and np.abs(out).max() < 3000
