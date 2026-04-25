from __future__ import annotations

import numpy as np
import pytest

from ai.scripts.demos import virtual_mic_streamer


def test_find_cable_input_device_prefers_requested_playback_endpoint(monkeypatch):
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_input_channels": 0,
            "max_output_channels": 2,
        },
        {"name": "Other CABLE Device", "max_input_channels": 0, "max_output_channels": 2},
    ]
    monkeypatch.setattr(virtual_mic_streamer.sd, "query_devices", lambda *_args, **_kwargs: devices)

    assert virtual_mic_streamer.find_cable_input_device("CABLE Input") == 2


def test_find_cable_input_device_supports_exact_output_device_id(monkeypatch):
    devices = [
        {"name": "CABLE Output", "max_input_channels": 2, "max_output_channels": 0},
        {"name": "CABLE Input", "max_input_channels": 0, "max_output_channels": 2},
    ]
    monkeypatch.setattr(virtual_mic_streamer.sd, "query_devices", lambda *_args, **_kwargs: devices)

    assert virtual_mic_streamer.find_cable_input_device(device_id=1) == 1
    with pytest.raises(ValueError, match="not an output"):
        virtual_mic_streamer.find_cable_input_device(device_id=0)


def test_match_channels_keeps_debug_playback_shapes_predictable():
    mono = np.array([[0.1], [0.2]], dtype=np.float32)
    stereo = virtual_mic_streamer._match_channels(mono, 2)

    assert stereo.shape == (2, 2)
    np.testing.assert_allclose(stereo[:, 0], mono[:, 0])
    np.testing.assert_allclose(stereo[:, 1], mono[:, 0])

    multi = virtual_mic_streamer._match_channels(stereo, 1)
    assert multi.shape == (2, 1)
    np.testing.assert_allclose(multi[:, 0], mono[:, 0])


def test_parser_allows_device_listing_without_input():
    args = virtual_mic_streamer.build_parser().parse_args(["--list-devices"])

    assert args.list_devices is True
    assert args.input is None
