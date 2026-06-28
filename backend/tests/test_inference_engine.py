"""
test_inference_engine.py — Multiprocessing and CV Engine tests.
"""
import pytest
import time
import multiprocessing as mp
from unittest.mock import MagicMock, patch

from backend.inference_engine.capture_worker import CaptureWorker
from backend.inference_engine.engine_manager import EngineManager

def test_capture_worker_drops_frames_when_queue_full():
    """Test that CaptureWorker uses get_nowait() to drop frames if inference is slow."""
    queue = mp.Queue(maxsize=1)
    worker = CaptureWorker("cam_1", "rtsp://mock", queue)
    
    # Fill the queue manually
    queue.put_nowait(("cam_1", time.time(), "frame1"))
    
    # Mock a new frame coming in
    worker._latest_frame = "frame2"
    worker._push_to_queue()
    
    # The queue should now contain frame2 (frame1 was dropped)
    cam_id, ts, frame = queue.get_nowait()
    assert frame == "frame2"

@pytest.mark.asyncio
async def test_engine_manager_add_remove_camera():
    manager = EngineManager()
    manager.start()
    
    manager.add_camera("cam_1", "rtsp://mock")
    assert "cam_1" in manager.capture_workers
    assert manager.capture_workers["cam_1"]._running is True
    
    manager.remove_camera("cam_1")
    assert "cam_1" not in manager.capture_workers
    
    await manager.stop()
