"""Focused suppression quality tests for SemanticSuppressor.

Tests both the default Wiener-DD masking and the cIRM alternative.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai.ai_runtime.separation.codecsep_query import (
    CodecSepCandidateScore,
    CodecSepQueryPlan,
    CodecSepQueryResult,
)
from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.suppression.masking import CIRMMasking


class FakeDetector:
    def __init__(self, confidence: float = 0.8):
        self.detections = {"pets": confidence}

    def classify(self, audio, sample_rate):
        return {
            "raw": self.detections,
            "smoothed": self.detections,
            "stable": {k: v > 0.5 for k, v in self.detections.items()},
            "states": {k: "active" if v > 0.5 else "inactive" for k, v in self.detections.items()},
        }


class FakeSeparator:
    def __init__(self, capture_ratio: float = 0.6):
        self.capture_ratio = capture_ratio

    def separate(self, audio, sample_rate, targets=None):
        result = audio * self.capture_ratio
        if result.ndim == 1:
            result = result.reshape(-1, 1)
        return result


class FakeCodecSepSeparator:
    def __init__(self):
        self.calls = []

    def separate_stems(self, audio, sample_rate, stems=None, prompt_overrides=None):
        self.calls.append(
            {
                "sample_rate": sample_rate,
                "stems": list(stems or []),
                "prompt_overrides": dict(prompt_overrides or {}),
            },
        )
        audio_out = audio.astype(np.float32)
        if audio_out.ndim == 1:
            return {stem: audio_out.copy() for stem in stems or []}
        return {stem: audio_out.copy() for stem in stems or []}


class ComplementCodecSepSeparator:
    def __init__(self):
        self.calls = []

    def separate_stems(self, audio, sample_rate, stems=None, prompt_overrides=None):
        self.calls.append(
            {
                "sample_rate": sample_rate,
                "stems": list(stems or []),
                "prompt_overrides": dict(prompt_overrides or {}),
            },
        )
        audio = np.asarray(audio, dtype=np.float32)
        n = len(audio)
        speech = np.full(n, 0.3, dtype=np.float32)
        music = np.full(n, 0.2, dtype=np.float32)
        sfx = np.full(n, 0.5, dtype=np.float32)
        mapping = {"speech": speech, "music": music, "sfx": sfx}
        return {stem: mapping[stem].copy() for stem in stems or [] if stem in mapping}


class BundledCodecSepSeparator:
    STEMS = ("speech", "music", "sfx")

    def __init__(self):
        self.calls = []

    def separate_stem_bundle(self, audio, sample_rate, stems=None, prompt_overrides=None):
        self.calls.append(
            {
                "sample_rate": sample_rate,
                "stems": list(stems or []),
                "prompt_overrides": dict(prompt_overrides or {}),
            },
        )
        audio = np.asarray(audio, dtype=np.float32)
        n = len(audio)
        raw = {
            "speech": np.full(n, 0.25, dtype=np.float32),
            "music": np.full(n, 0.15, dtype=np.float32),
            "sfx": np.full(n, 0.20, dtype=np.float32),
        }
        normalized = {
            "speech": np.full(n, 0.30, dtype=np.float32),
            "music": np.full(n, 0.20, dtype=np.float32),
            "sfx": np.full(n, 0.50, dtype=np.float32),
        }
        requested = stems or []
        return {
            "raw": {stem: raw[stem].copy() for stem in requested if stem in raw},
            "normalized": {
                stem: normalized[stem].copy() for stem in requested if stem in normalized
            },
        }


class FakeQueryCodecSepSeparator:
    STEMS = ("speech", "music", "sfx")

    def __init__(self, *, auto_selected_slot: str | None = None):
        self.query_calls: list[dict] = []
        self.auto_selected_slot = auto_selected_slot

    def query(self, audio, sample_rate, plan, selected_slot_hint=None):
        self.query_calls.append(
            {
                "sample_rate": sample_rate,
                "plan": plan,
                "selected_slot_hint": selected_slot_hint,
            },
        )
        audio = np.asarray(audio, dtype=np.float32)
        n = len(audio)
        normalized_outputs = {
            "speech": np.full(n, 0.30, dtype=np.float32),
            "music": np.full(n, 0.20, dtype=np.float32),
            "sfx": np.full(n, 0.50, dtype=np.float32),
        }
        selected_slot = selected_slot_hint or self.auto_selected_slot or plan.preferred_slot
        target_audio = normalized_outputs[selected_slot].copy()
        complement = np.zeros_like(target_audio)
        for slot, track in normalized_outputs.items():
            if slot != selected_slot:
                complement += track
        if plan.reconstruction_policy == "keep_complement":
            clean_audio = complement
            chosen_policy = "keep_complement"
        elif plan.reconstruction_policy == "wiener_mask":
            # Simulate Wiener masking: complement weighted by power ratio
            clean_audio = complement
            chosen_policy = "wiener_mask"
        else:
            clean_audio = audio - max(1.0, float(plan.aggressiveness)) * target_audio
            chosen_policy = "subtract_target"
        score = CodecSepCandidateScore(
            slot=selected_slot,
            target_score=0.9 if selected_slot == "sfx" else 0.8,
            preserve_score=0.7 if plan.preserve_prompts else 0.0,
            mixture_score=0.95,
            total_score=0.98 if selected_slot == "sfx" else 0.85,
            strategy=plan.query_strategy,
        )
        return CodecSepQueryResult(
            plan=plan,
            selected_slot=selected_slot,
            target_audio=target_audio,
            clean_audio=clean_audio,
            raw_outputs={slot: track.copy() for slot, track in normalized_outputs.items()},
            normalized_outputs={slot: track.copy() for slot, track in normalized_outputs.items()},
            score=score,
            candidate_scores={selected_slot: score},
            chosen_policy=chosen_policy,
            used_multistep=bool(plan.use_multistep and plan.multistep_steps > 1),
        )


class FailingDetector:
    def classify(self, audio, sample_rate):
        raise AssertionError("Detector should not have been called")


class FakeUniversalSeparator:
    """Tracks calls to AudioSep and returns a scaled copy of input."""

    def __init__(self, capture_ratio: float = 0.5):
        self.calls: list[dict] = []
        self.capture_ratio = capture_ratio

    def separate(self, audio, sample_rate, prompts=None):
        self.calls.append({"sample_rate": sample_rate, "prompts": list(prompts or [])})
        return (audio * self.capture_ratio).astype(np.float32)


class FakeAudioSepHive15CatSeparator:
    def __init__(self, category_scales: dict[str, float] | None = None):
        self.calls: list[dict] = []
        self.category_scales = dict(category_scales or {})

    def separate(self, audio, sample_rate, categories):
        labels = [categories] if isinstance(categories, str) else list(categories)
        self.calls.append({"sample_rate": sample_rate, "categories": labels})
        output = np.zeros_like(np.asarray(audio, dtype=np.float32))
        for label in labels:
            output += np.asarray(audio, dtype=np.float32) * float(
                self.category_scales.get(label, 0.25)
            )
        return output.astype(np.float32)


class MultiCategoryDetector:
    def __init__(self, scores):
        self.scores = scores

    def classify(self, audio, sample_rate):
        return {
            "raw": self.scores,
            "smoothed": self.scores,
            "stable": {k: v > 0.5 for k, v in self.scores.items()},
            "states": {k: "active" if v > 0.5 else "inactive" for k, v in self.scores.items()},
        }


def make_impulse_audio(sr: int = 44100) -> np.ndarray:
    n_samples = sr
    audio = np.zeros(n_samples, dtype=np.float32)
    burst_len = int(0.005 * sr)
    center = n_samples // 2
    t = np.linspace(0, 2 * np.pi * 8, burst_len)
    audio[center : center + burst_len] = 0.9 * np.sin(t).astype(np.float32)
    return audio


def legacy_subtractive_cirm(
    mix: np.ndarray,
    unwanted: np.ndarray,
    *,
    aggressiveness: float,
    sample_rate: int,
    nperseg: int = 2048,
) -> np.ndarray:
    from scipy import signal as scipy_signal

    noverlap = nperseg // 2
    eps = 1e-10

    mix_2d = mix.reshape(-1, 1) if mix.ndim == 1 else mix
    unwanted_2d = unwanted.reshape(-1, 1) if unwanted.ndim == 1 else unwanted
    min_len = min(mix_2d.shape[0], unwanted_2d.shape[0])
    num_channels = mix_2d.shape[1]
    unw_channels = min(num_channels, unwanted_2d.shape[1])

    clean_channels: list[np.ndarray] = []
    for ch in range(num_channels):
        mix_ch = mix_2d[:min_len, ch].astype(np.float64)
        unw_ch = np.asarray(
            unwanted_2d[:min_len, ch % unw_channels], dtype=np.float64,
        ).ravel()[:min_len]

        _, _, z_mix = scipy_signal.stft(
            mix_ch, nperseg=nperseg, noverlap=noverlap,
        )
        _, _, z_unw = scipy_signal.stft(
            unw_ch, nperseg=nperseg, noverlap=noverlap,
        )

        mean_unw = np.mean(np.abs(z_unw))
        mean_mix = np.mean(np.abs(z_mix)) + eps
        confidence = min(1.0, mean_unw / mean_mix)
        effective_agg = aggressiveness * confidence

        z_clean = z_mix - effective_agg * z_unw
        mag_clean = np.abs(z_clean)
        mag_mix = np.abs(z_mix) + eps
        floor = np.linspace(0.01, 0.05, mag_clean.shape[0], dtype=np.float64)[:, np.newaxis]
        mag_clean = np.maximum(mag_clean, floor * mag_mix)
        z_clean = mag_clean * np.exp(1j * np.angle(z_clean))

        _, clean_ch = scipy_signal.istft(
            z_clean, nperseg=nperseg, noverlap=noverlap,
        )
        clean_ch = clean_ch[:min_len]
        if len(clean_ch) < min_len:
            clean_ch = np.pad(clean_ch, (0, min_len - len(clean_ch)), mode="constant")
        clean_channels.append(clean_ch)

    clean_audio = np.column_stack(clean_channels)
    if mix.ndim == 1:
        clean_audio = clean_audio.flatten()
    return clean_audio.astype(mix.dtype)


def test_passthrough_returns_original():
    supp = SemanticSuppressor(
        detector=FakeDetector(), separator=FakeSeparator(),
        separator_backend="waveformer",
    )
    audio = make_impulse_audio()
    clean = supp.suppress(audio=audio, sample_rate=44100, suppress_categories=[])
    np.testing.assert_array_equal(audio, clean)


def test_semantic_suppressor_defaults_to_waveformer():
    supp = SemanticSuppressor(detector=FakeDetector(), separator=FakeSeparator())
    assert supp.separator_backend == "waveformer"


def test_impulse_is_reduced_when_category_active():
    supp = SemanticSuppressor(
        detector=FakeDetector(0.9), separator=FakeSeparator(0.8),
        separator_backend="waveformer",
    )
    audio = make_impulse_audio()
    clean = supp.suppress(
        audio=audio,
        sample_rate=44100,
        suppress_categories=["pets"],
        detection_threshold=-1,
        aggressiveness=1.0,
    )
    center = len(audio) // 2
    burst_len = int(0.005 * 44100)
    original_energy = np.sum(audio[center : center + burst_len] ** 2)
    clean_energy = np.sum(clean[center : center + burst_len] ** 2)
    assert clean_energy < original_energy * 0.8


def test_stereo_shape_preserved():
    supp = SemanticSuppressor(
        detector=FakeDetector(), separator=FakeSeparator(0.6),
        separator_backend="waveformer",
    )
    audio = np.random.randn(44100, 2).astype(np.float32) * 0.2
    clean = supp.suppress(
        audio=audio,
        sample_rate=44100,
        suppress_categories=["pets"],
        detection_threshold=-1,
    )
    assert clean.shape == audio.shape


def test_no_musical_noise():
    """Verify the Wiener-IRM mask doesn't introduce musical noise artifacts.

    Creates a mix of broadband noise + narrowband tone (simulating unwanted),
    runs suppression, and checks that the 1 kHz tone energy is reduced in output.
    """
    from scipy.signal import butter, sosfilt, welch

    sr = 44100
    n_samples = sr
    t = np.linspace(0, 1.0, n_samples, endpoint=False)

    # Broadband "speech-like" signal
    np.random.seed(42)
    speech = np.random.randn(n_samples).astype(np.float32) * 0.3

    # Narrowband tone (unwanted noise at 1 kHz)
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)

    mix = speech + tone

    # Separator bandpass-filters input around 1 kHz to isolate the tone
    class BandpassSeparator:
        def separate(self, audio, sample_rate, targets=None):
            audio_1d = audio.ravel() if audio.ndim > 1 else audio
            sos = butter(4, [800, 1200], btype="bandpass", fs=sample_rate, output="sos")
            filtered = sosfilt(sos, audio_1d).astype(np.float32)
            return filtered.reshape(-1, 1)

    supp = SemanticSuppressor(
        detector=FakeDetector(0.9),
        separator=BandpassSeparator(),
        separator_backend="waveformer",
    )
    clean = supp.suppress(
        audio=mix,
        sample_rate=sr,
        suppress_categories=["pets"],
        detection_threshold=-1,
        aggressiveness=1.0,
    )

    # Compute spectral energy in clean output
    freqs, psd_clean = welch(clean, fs=sr, nperseg=2048)
    _, psd_mix = welch(mix, fs=sr, nperseg=2048)

    # Energy at 1 kHz should be significantly reduced vs the original mix
    tone_idx = np.argmin(np.abs(freqs - 1000))

    # The 1 kHz tone energy should be reduced by at least 40%
    assert psd_clean[tone_idx] < psd_mix[tone_idx] * 0.6, (
        f"Musical noise: 1kHz tone not sufficiently suppressed "
        f"(clean={psd_clean[tone_idx]:.6f}, mix={psd_mix[tone_idx]:.6f})"
    )


def test_temporal_smoothness():
    """Verify EMA smoothing produces consistent energy across chunk boundaries.

    Runs two consecutive chunks through the suppressor and checks that
    the energy transition between chunks is smooth (no sudden jumps).
    """
    sr = 44100
    chunk_size = sr  # 1 second chunks
    np.random.seed(123)

    # Create two chunks of consistent noise
    chunk1 = np.random.randn(chunk_size).astype(np.float32) * 0.3
    chunk2 = np.random.randn(chunk_size).astype(np.float32) * 0.3

    supp = SemanticSuppressor(
        detector=FakeDetector(0.9),
        separator=FakeSeparator(0.6),
        separator_backend="waveformer",
    )

    # Process both chunks sequentially (EMA state should carry over)
    clean1 = supp.suppress(
        audio=chunk1,
        sample_rate=sr,
        suppress_categories=["pets"],
        detection_threshold=-1,
    )
    clean2 = supp.suppress(
        audio=chunk2,
        sample_rate=sr,
        suppress_categories=["pets"],
        detection_threshold=-1,
    )

    # Compare RMS energy at boundary regions (last 10% of chunk1, first 10% of chunk2)
    boundary_size = chunk_size // 10
    rms_end = np.sqrt(np.mean(clean1[-boundary_size:] ** 2))
    rms_start = np.sqrt(np.mean(clean2[:boundary_size] ** 2))

    # Energy ratio should be within 3x (no sudden jumps)
    if rms_end > 1e-8 and rms_start > 1e-8:
        ratio = max(rms_end, rms_start) / min(rms_end, rms_start)
        assert ratio < 3.0, (
            f"Energy discontinuity at chunk boundary: ratio={ratio:.2f} "
            f"(end_rms={rms_end:.6f}, start_rms={rms_start:.6f})"
        )


# ===================================================================
# cIRM masking path tests
# ===================================================================

def test_cirm_passthrough_returns_original():
    supp = SemanticSuppressor(
        detector=FakeDetector(), separator=FakeSeparator(),
        separator_backend="waveformer", masking_method="cirm",
    )
    audio = make_impulse_audio()
    clean = supp.suppress(audio=audio, sample_rate=44100, suppress_categories=[])
    np.testing.assert_array_equal(audio, clean)


def test_cirm_impulse_is_reduced():
    supp = SemanticSuppressor(
        detector=FakeDetector(0.9), separator=FakeSeparator(0.8),
        separator_backend="waveformer", masking_method="cirm",
    )
    audio = make_impulse_audio()
    clean = supp.suppress(
        audio=audio, sample_rate=44100,
        suppress_categories=["pets"], detection_threshold=-1,
        aggressiveness=1.0,
    )
    center = len(audio) // 2
    burst_len = int(0.005 * 44100)
    original_energy = np.sum(audio[center : center + burst_len] ** 2)
    clean_energy = np.sum(clean[center : center + burst_len] ** 2)
    assert clean_energy < original_energy * 0.8


def test_cirm_stereo_shape_preserved():
    supp = SemanticSuppressor(
        detector=FakeDetector(), separator=FakeSeparator(0.6),
        separator_backend="waveformer", masking_method="cirm",
    )
    audio = np.random.randn(44100, 2).astype(np.float32) * 0.2
    clean = supp.suppress(
        audio=audio, sample_rate=44100,
        suppress_categories=["pets"], detection_threshold=-1,
    )
    assert clean.shape == audio.shape


def test_cirm_tone_suppression():
    """Verify cIRM suppresses a 1 kHz tone just like Wiener-DD."""
    from scipy.signal import butter, sosfilt, welch

    sr = 44100
    n_samples = sr
    t = np.linspace(0, 1.0, n_samples, endpoint=False)

    np.random.seed(42)
    speech = np.random.randn(n_samples).astype(np.float32) * 0.3
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    mix = speech + tone

    class BandpassSeparator:
        def separate(self, audio, sample_rate, targets=None):
            audio_1d = audio.ravel() if audio.ndim > 1 else audio
            sos = butter(4, [800, 1200], btype="bandpass", fs=sample_rate, output="sos")
            filtered = sosfilt(sos, audio_1d).astype(np.float32)
            return filtered.reshape(-1, 1)

    supp = SemanticSuppressor(
        detector=FakeDetector(0.9), separator=BandpassSeparator(),
        separator_backend="waveformer", masking_method="cirm",
    )
    # cIRM soft-blend reduces aggressiveness for weak unwanted signals,
    # so use higher aggressiveness to compensate in this synthetic test.
    clean = supp.suppress(
        audio=mix, sample_rate=sr,
        suppress_categories=["pets"], detection_threshold=-1,
        aggressiveness=2.5,
    )

    freqs, psd_clean = welch(clean, fs=sr, nperseg=2048)
    _, psd_mix = welch(mix, fs=sr, nperseg=2048)
    tone_idx = np.argmin(np.abs(freqs - 1000))
    assert psd_clean[tone_idx] < psd_mix[tone_idx] * 0.7


def test_cirm_masking_stays_finite_for_near_silence():
    masking = CIRMMasking(nperseg=512)
    mix = np.zeros(4096, dtype=np.float32)
    mix[2048] = 1e-8
    unwanted = np.roll(mix, 3)

    clean = masking.apply(
        mix=mix,
        unwanted=unwanted,
        aggressiveness=1.8,
        sample_rate=16000,
    )

    assert np.all(np.isfinite(clean))
    assert np.max(np.abs(clean)) < 1e-4


def test_cirm_masking_has_bounded_peak_gain():
    np.random.seed(7)
    masking = CIRMMasking(nperseg=1024)
    mix = (np.random.randn(8192) * 0.08).astype(np.float32)
    unwanted = (0.75 * np.roll(mix, 5)).astype(np.float32)

    clean = masking.apply(
        mix=mix,
        unwanted=unwanted,
        aggressiveness=1.6,
        sample_rate=16000,
    )

    assert np.max(np.abs(clean)) <= np.max(np.abs(mix)) * 1.15


def test_codecsep_aggregates_sfx_prompts_once():
    detector = MultiCategoryDetector(
        {"typing": 0.95, "pets": 0.85, "traffic": 0.75, "phone": 0.65},
    )
    codecsep = FakeCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.random.randn(16000).astype(np.float32) * 0.05
    supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["typing", "pets", "traffic", "phone"],
        detection_threshold=-1,
        aggressiveness=1.0,
    )

    assert len(codecsep.calls) == 1
    call = codecsep.calls[0]
    assert set(call["stems"]) == {"speech", "music", "sfx"}
    assert len(call["prompt_overrides"]["sfx"]) == 1
    sfx_prompt = call["prompt_overrides"]["sfx"][0]
    assert "keyboard typing sounds" in sfx_prompt
    assert "a dog barking" in sfx_prompt
    assert "traffic noise" in sfx_prompt


def test_codecsep_audiocaps_native_compiles_fixed_slot_plan():
    detector = MultiCategoryDetector({"typing": 0.92})
    codecsep = FakeQueryCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["typing"],
        detection_threshold=-1,
        codecsep_mode="audiocaps_native",
        codecsep_query_strategy="slot_search",
        codecsep_multistep_steps=3,
    )

    assert len(codecsep.query_calls) == 1
    call = codecsep.query_calls[0]
    plan = call["plan"]
    assert plan.preferred_slot == "sfx"
    assert plan.reconstruction_policy == "wiener_mask"
    assert plan.query_strategy == "single_pass"
    assert plan.multistep_steps == 0
    assert "keyboard typing" in plan.target_prompts[0]
    assert len(plan.negative_prompts) > 0  # negative prompts now wired through native mode


def test_codecsep_audiocaps_native_enriches_target_prompt_with_explicit_override():
    detector = MultiCategoryDetector({"typing": 0.90})
    codecsep = FakeQueryCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(4096, dtype=np.float32)
    supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["typing"],
        detection_threshold=-1,
        codecsep_mode="audiocaps_native",
        codecsep_prompt_overrides={"sfx": ["mechanical keyboard clicks"]},
    )

    plan = codecsep.query_calls[0]["plan"]
    assert any("keyboard typing" in prompt for prompt in plan.target_prompts)
    assert "mechanical keyboard clicks" in plan.target_prompts


def test_codecsep_audiocaps_native_uses_query_path_for_universal_prompts():
    codecsep = FakeQueryCodecSepSeparator()
    universal = FakeUniversalSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
        universal=universal,
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(4096, dtype=np.float32)
    supp.suppress(
        audio=audio,
        sample_rate=16000,
        universal_prompts=["dog barking", "bark"],
        codecsep_mode="audiocaps_native",
        codecsep_query_strategy="slot_search",
    )

    assert len(codecsep.query_calls) == 1
    assert universal.calls == []
    plan = codecsep.query_calls[0]["plan"]
    assert plan.target_label == "universal"
    assert "dog barking" in plan.target_prompts[0]
    assert plan.preferred_slot == "sfx"
    assert plan.reconstruction_policy == "subtract_target"


def test_codecsep_audiocaps_native_does_not_reuse_slot_cache():
    detector = MultiCategoryDetector({"chimes": 0.94})
    codecsep = FakeQueryCodecSepSeparator(auto_selected_slot="music")
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(4096, dtype=np.float32)
    for _ in range(2):
        supp.suppress(
            audio=audio,
            sample_rate=16000,
            suppress_categories=["chimes"],
            detection_threshold=-1,
            codecsep_mode="audiocaps_native",
            codecsep_query_strategy="slot_search",
        )

    assert len(codecsep.query_calls) == 2
    assert codecsep.query_calls[0]["selected_slot_hint"] is None
    assert codecsep.query_calls[1]["selected_slot_hint"] is None
    assert codecsep.query_calls[1]["plan"].query_strategy == "single_pass"


def test_codecsep_audiocaps_native_speech_uses_keep_complement_policy():
    detector = MultiCategoryDetector({"speech": 0.95})
    codecsep = FakeQueryCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["speech"],
        detection_threshold=-1,
        codecsep_mode="audiocaps_native",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.7), atol=1e-6)
    assert codecsep.query_calls[0]["plan"].reconstruction_policy == "keep_complement"


def test_codecsep_audiocaps_native_return_details_exposes_exact_target_audio():
    codecsep = FakeQueryCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(1024, dtype=np.float32)
    result = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["typing"],
        codecsep_mode="audiocaps_native",
        return_details=True,
    )

    plan = codecsep.query_calls[0]["plan"]
    assert plan.reconstruction_policy == "wiener_mask"
    # wiener_mask fake returns complement (speech 0.30 + music 0.20 = 0.50)
    expected_clean = np.full_like(audio, 0.50)
    np.testing.assert_allclose(result["clean_audio"], expected_clean, atol=1e-6)
    np.testing.assert_allclose(result["removed_audio"], np.full_like(audio, 0.5), atol=1e-6)


def test_codecsep_uses_distinct_per_stem_prompts_in_single_call():
    detector = MultiCategoryDetector({"speech": 0.92, "typing": 0.88})
    codecsep = FakeCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.random.randn(16000).astype(np.float32) * 0.05
    supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["speech", "typing"],
        detection_threshold=-1,
    )

    assert len(codecsep.calls) == 1
    call = codecsep.calls[0]
    assert set(call["stems"]) == {"speech", "music", "sfx"}
    assert call["prompt_overrides"]["speech"] == ["speech, talking, voice"]
    assert call["prompt_overrides"]["sfx"] == [
        "keyboard typing sounds, key clicks from a computer keyboard"
    ]


def test_codecsep_explicit_prompt_override_takes_precedence():
    detector = MultiCategoryDetector({"typing": 0.88})
    codecsep = FakeCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=detector,
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.random.randn(16000).astype(np.float32) * 0.05
    supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["typing"],
        detection_threshold=-1,
        codecsep_prompt_overrides={"sfx": ["custom keyboard stem prompt"]},
    )

    assert len(codecsep.calls) == 1
    call = codecsep.calls[0]
    assert call["prompt_overrides"]["sfx"] == ["custom keyboard stem prompt"]


def test_codecsep_skips_detection_for_always_suppress_category():
    codecsep = FakeCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.random.randn(16000).astype(np.float32) * 0.05
    supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["pets"],
        codecsep_mode="compat",
    )

    assert len(codecsep.calls) == 1


def test_codecsep_pets_reconstructs_clean_audio_from_kept_normalized_stems():
    codecsep = ComplementCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep
    supp.category_map["pets"]["aggressiveness_override"] = 0.0

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["pets"],
        codecsep_mode="compat",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.5))
    assert len(codecsep.calls) == 1
    assert set(codecsep.calls[0]["stems"]) == {"speech", "music", "sfx"}


def test_codecsep_speech_category_suppresses_speech_stem():
    supp = SemanticSuppressor(
        detector=MultiCategoryDetector({"speech": 0.95}),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = ComplementCodecSepSeparator()

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["speech"],
        detection_threshold=-1,
        codecsep_mode="compat",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.7))


def test_codecsep_music_category_suppresses_music_stem():
    codecsep = ComplementCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=MultiCategoryDetector({"music": 0.95}),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["music"],
        detection_threshold=-1,
        codecsep_mode="compat",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.8))


def test_codecsep_sfx_categories_use_selective_residual_reconstruction():
    codecsep = BundledCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep
    supp.category_map["pets"]["aggressiveness_override"] = 0.0

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["pets"],
        aggressiveness=1.5,
        codecsep_mode="compat",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.25))
    assert len(codecsep.calls) == 1
    assert set(codecsep.calls[0]["stems"]) == {"speech", "music", "sfx"}


def test_codecsep_sfx_residual_path_is_energy_calibrated():
    class WeakRawBundledCodecSepSeparator(BundledCodecSepSeparator):
        def separate_stem_bundle(self, audio, sample_rate, stems=None, prompt_overrides=None):
            bundle = super().separate_stem_bundle(
                audio,
                sample_rate,
                stems=stems,
                prompt_overrides=prompt_overrides,
            )
            if "sfx" in bundle["raw"]:
                bundle["raw"]["sfx"] = np.full(len(audio), 0.10, dtype=np.float32)
            if "sfx" in bundle["normalized"]:
                bundle["normalized"]["sfx"] = np.full(len(audio), 0.30, dtype=np.float32)
            return bundle

    codecsep = WeakRawBundledCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep
    supp.category_map["pets"]["aggressiveness_override"] = 0.0

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["pets"],
        aggressiveness=1.5,
        codecsep_mode="compat",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.55), atol=1e-6)


def test_codecsep_bypasses_post_masking_for_paper_faithful_path(monkeypatch):
    codecsep = ComplementCodecSepSeparator()
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="codecsep",
        masking_method="cirm",
    )
    supp._codecsep_separator = codecsep
    supp.category_map["pets"]["aggressiveness_override"] = 0.0
    monkeypatch.setattr(
        supp,
        "_get_masking_strategy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("CodecSep should not call post-separation masking"),
        ),
    )

    audio = np.ones(16000, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["pets"],
        codecsep_mode="compat",
    )

    np.testing.assert_allclose(clean, np.full_like(audio, 0.5))


def test_audiosep_hive15cat_routes_through_post_masking(monkeypatch):
    separator = FakeAudioSepHive15CatSeparator({"keyboard typing": 0.25})
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="audiosep_hive15cat",
        masking_method="cirm",
        audiosep_hive15cat=separator,
    )
    supp.under_extract_scale = 1.0

    captured: dict = {}

    class FakeMasking:
        def apply(self, *, mix, unwanted, aggressiveness, sample_rate, **kwargs):
            captured["mix"] = np.asarray(mix)
            captured["unwanted"] = np.asarray(unwanted)
            captured["aggressiveness"] = aggressiveness
            captured["sample_rate"] = sample_rate
            captured["kwargs"] = kwargs
            return np.full_like(np.asarray(mix, dtype=np.float32), 0.125)

    monkeypatch.setattr(supp, "_get_masking_strategy", lambda *_args, **_kwargs: FakeMasking())

    audio = np.ones(4096, dtype=np.float32)
    result = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["keyboard typing"],
        return_details=True,
    )

    assert len(separator.calls) == 1
    assert separator.calls[0]["categories"] == ["keyboard typing"]
    np.testing.assert_allclose(captured["unwanted"], np.full_like(audio, 0.25), atol=1e-6)
    assert captured["kwargs"]["mask_floor"] == pytest.approx(0.05)
    assert captured["kwargs"]["max_suppression_ratio"] == pytest.approx(0.82)
    assert captured["kwargs"]["speech_dominance_threshold"] == pytest.approx(2.5)
    np.testing.assert_allclose(result["clean_audio"], np.full_like(audio, 0.125), atol=1e-6)
    np.testing.assert_allclose(result["removed_audio"], np.full_like(audio, 0.875), atol=1e-6)


def test_audiosep_hive15cat_skips_detection_for_manual_exact_labels():
    separator = FakeAudioSepHive15CatSeparator({"alarm": 0.2})
    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="audiosep_hive15cat",
        audiosep_hive15cat=separator,
    )

    audio = np.ones(4096, dtype=np.float32)
    clean = supp.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["alarm"],
    )

    assert len(separator.calls) == 1
    assert separator.calls[0]["categories"] == ["alarm"]
    assert clean.shape == audio.shape


@pytest.mark.parametrize(
    ("category", "target_freq"),
    [
        ("keyboard typing", 3200),
        ("phone ringing", 2000),
        ("alarm", 2800),
    ],
)
def test_audiosep_hive15cat_synthetic_suppression_reduces_target_band(category, target_freq):
    from scipy.signal import butter, sosfilt, welch

    class BandTargetSeparator:
        def separate(self, audio, sample_rate, categories):
            del categories
            audio_1d = np.asarray(audio, dtype=np.float32).ravel()
            low = max(80, target_freq - 250)
            high = min(sample_rate // 2 - 100, target_freq + 250)
            sos = butter(4, [low, high], btype="bandpass", fs=sample_rate, output="sos")
            filtered = sosfilt(sos, audio_1d).astype(np.float32)
            return filtered

    supp = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="audiosep_hive15cat",
        audiosep_hive15cat=BandTargetSeparator(),
    )

    sr = 16000
    duration = 1.0
    n_samples = int(sr * duration)
    t = np.linspace(0.0, duration, n_samples, endpoint=False)
    speech_like = (0.35 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    target = (0.45 * np.sin(2 * np.pi * target_freq * t)).astype(np.float32)
    mix = speech_like + target

    clean = supp.suppress(
        audio=mix,
        sample_rate=sr,
        suppress_categories=[category],
        aggressiveness=1.8,
    )

    freqs, psd_mix = welch(mix, fs=sr, nperseg=1024)
    _, psd_clean = welch(clean, fs=sr, nperseg=1024)
    target_idx = np.argmin(np.abs(freqs - target_freq))
    speech_idx = np.argmin(np.abs(freqs - 440))

    assert psd_clean[target_idx] < psd_mix[target_idx] * 0.7
    assert psd_clean[speech_idx] > psd_mix[speech_idx] * 0.5
