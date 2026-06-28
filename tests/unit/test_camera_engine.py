from __future__ import annotations

import asyncio
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

# ── Mock heavy deps so tests run without OpenCV/NumPy installed ───────────────
_np_mock = types.ModuleType("numpy")
_np_mock.ndarray = MagicMock
sys.modules.setdefault("numpy", _np_mock)

_cv2_mock = types.ModuleType("cv2")
_cv2_mock.VideoCapture      = MagicMock
_cv2_mock.CAP_FFMPEG        = 0
_cv2_mock.CAP_PROP_FOURCC   = 0
_cv2_mock.CAP_PROP_BUFFERSIZE = 0
_cv2_mock.CAP_PROP_FPS      = 0
_cv2_mock.CAP_PROP_FRAME_WIDTH  = 0
_cv2_mock.CAP_PROP_FRAME_HEIGHT = 0
_cv2_mock.VideoWriter_fourcc = MagicMock(return_value=0)
sys.modules.setdefault("cv2", _cv2_mock)

from app.services.stream_health import StreamHealthMonitor, StreamState  # noqa: E402
from app.services.camera_service import ReconnectPolicy                  # noqa: E402


class TestStreamStateMachine:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        h = StreamHealthMonitor("cam-1", target_fps=10)
        assert h.state == StreamState.INITIALIZING

    @pytest.mark.asyncio
    async def test_valid_transition(self):
        h = StreamHealthMonitor("cam-1")
        await h.transition(StreamState.CONNECTING)
        assert h.state == StreamState.CONNECTING

    @pytest.mark.asyncio
    async def test_invalid_transition_ignored(self):
        h = StreamHealthMonitor("cam-1")
        # INITIALIZING → ACTIVE is invalid (must go through CONNECTING)
        await h.transition(StreamState.ACTIVE)
        assert h.state == StreamState.INITIALIZING  # unchanged

    @pytest.mark.asyncio
    async def test_reconnect_increments_counter(self):
        h = StreamHealthMonitor("cam-1")
        await h.transition(StreamState.CONNECTING)
        await h.transition(StreamState.RECONNECTING)
        assert h._reconnect_count == 1

    @pytest.mark.asyncio
    async def test_full_happy_path(self):
        h = StreamHealthMonitor("cam-1")
        await h.transition(StreamState.CONNECTING)
        await h.transition(StreamState.ACTIVE)
        await h.transition(StreamState.DISCONNECTED)
        assert h.state == StreamState.DISCONNECTED


class TestFPSCalculation:
    def test_no_frames_returns_zero(self):
        h = StreamHealthMonitor("cam-1", target_fps=10)
        assert h.avg_fps == 0.0

    def test_single_frame_returns_zero(self):
        h = StreamHealthMonitor("cam-1", target_fps=10)
        h.record_frame()
        assert h.avg_fps == 0.0  # Need at least 2 timestamps

    def test_fps_approximately_correct(self):
        h = StreamHealthMonitor("cam-1", target_fps=10)
        # Simulate 10 frames over ~1 second
        for i in range(11):
            h._frame_times.append(time.monotonic())
            if i < 10:
                time.sleep(0.1)
        fps = h.avg_fps
        assert 8.0 <= fps <= 12.0, f"Expected ~10 FPS, got {fps:.2f}"

    def test_drop_rate_calculation(self):
        h = StreamHealthMonitor("cam-1")
        for _ in range(8):
            h.record_frame()
        for _ in range(2):
            h.record_dropped_frame()
        assert abs(h.drop_rate - 0.2) < 0.01

    def test_drop_rate_zero_with_no_frames(self):
        h = StreamHealthMonitor("cam-1")
        assert h.drop_rate == 0.0

    @pytest.mark.asyncio
    async def test_degradation_not_triggered_immediately(self):
        h = StreamHealthMonitor("cam-1", target_fps=10)
        await h.transition(StreamState.CONNECTING)
        await h.transition(StreamState.ACTIVE)
        # Low FPS but within grace period
        h._degraded_since = time.monotonic() - 5.0  # only 5s (grace=10s)
        await h.check_degradation()
        assert h.state == StreamState.ACTIVE  # Not degraded yet

    def test_health_snapshot_fields(self):
        h = StreamHealthMonitor("cam-99", target_fps=15)
        h.record_frame(latency_ms=12.5, resolution=(1920, 1080))
        snap = h.snapshot()
        assert snap.camera_id    == "cam-99"
        assert snap.target_fps   == 15
        assert snap.resolution   == (1920, 1080)
        assert snap.latency_ms is not None

    def test_reset_clears_frame_history(self):
        h = StreamHealthMonitor("cam-1")
        for _ in range(20):
            h.record_frame()
        h.reset_metrics()
        assert h.avg_fps == 0.0


class TestReconnectPolicy:
    def test_initial_delay(self):
        p = ReconnectPolicy(initial_delay=2.0)
        assert p.next_delay() == 2.0

    def test_exponential_backoff(self):
        p = ReconnectPolicy(initial_delay=2.0, multiplier=2.0, max_delay=60.0)
        delays = [p.next_delay() for _ in range(5)]
        assert delays[0] == 2.0
        assert delays[1] == 4.0
        assert delays[2] == 8.0
        assert delays[3] == 16.0
        assert delays[4] == 32.0

    def test_max_delay_cap(self):
        p = ReconnectPolicy(initial_delay=30.0, multiplier=3.0, max_delay=60.0)
        p.next_delay()  # 30
        delay = p.next_delay()  # would be 90, capped at 60
        assert delay == 60.0

    def test_infinite_retries(self):
        p = ReconnectPolicy(max_attempts=0)
        for _ in range(1000):
            assert p.should_retry() is True

    def test_max_attempts_limit(self):
        p = ReconnectPolicy(max_attempts=3)
        for _ in range(3):
            p.next_delay()
        assert p.should_retry() is False

    def test_reset_restores_initial(self):
        p = ReconnectPolicy(initial_delay=2.0)
        p.next_delay()
        p.next_delay()
        p.reset()
        assert p.next_delay() == 2.0
        assert p.attempts == 1
