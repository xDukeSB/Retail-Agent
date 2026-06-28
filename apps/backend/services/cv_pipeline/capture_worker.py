"""
capture_worker.py — RTSP Frame Grabber with Buffer Management.

Runs as an independent process per camera.
Continuously reads frames from RTSP to drain the internal OpenCV buffer.
JPEG-encodes each frame before queuing to keep inter-process transfer payloads small.
Implements robust exponential backoff and structured error logging.
"""

import time
import cv2
import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import multiprocessing as mp
import traceback
import logging

logger = logging.getLogger("retailai.cv.capture")


class CaptureWorker(mp.Process):
    def __init__(self, camera_id: str, rtsp_url: str, output_queue: mp.Queue, event_queue: mp.Queue):
        super().__init__(name=f"CaptureWorker-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.output_queue = output_queue
        self.event_queue = event_queue

        self._running = mp.Event()
        self._cap = None

        # Exponential backoff
        self._reconnect_delay = 1.0
        self._max_delay = 30.0
        self._frames_read = 0
        self._last_fps_time = time.time()
        self._fps_frame_count = 0

    def _emit_state(self, state: str, details: str = ""):
        try:
            self.event_queue.put_nowait({
                "type": "camera_state",
                "camera_id": self.camera_id,
                "state": state,
                "details": details,
                "timestamp": time.time()
            })
        except Exception:
            pass

    def run(self):
        """Starts the capture worker process."""
        self._running.set()
        logger.info(f"[CaptureWorker] Process started for camera {self.camera_id}")
        self._emit_state("CONNECTING")
        self._capture_loop()

    def stop(self):
        """Stops the capture worker gracefully."""
        self._running.clear()
        logger.info(f"[CaptureWorker] Stop requested for camera {self.camera_id}")
        self._emit_state("CAMERA OFFLINE")

    def _connect(self) -> bool:
        """Attempts to open the RTSP stream using the FFmpeg backend."""
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

        logger.info(f"[CaptureWorker] Connecting to {self.rtsp_url} (camera: {self.camera_id})")
        self._emit_state("AUTHENTICATING")

        try:
            # CAP_FFMPEG is mandatory for reliable RTSP on Windows/Linux
            self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            # Minimize internal buffer to 1 frame for near-zero latency
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self._cap.isOpened():
                logger.error(
                    f"[CaptureWorker] cv2.VideoCapture.isOpened() == False\n"
                    f"  Camera ID: {self.camera_id}\n"
                    f"  RTSP URL:  {self.rtsp_url}\n"
                    f"  Stage:     Decoder Initialization\n"
                    f"  Recovery:  Will retry with backoff ({self._reconnect_delay}s)"
                )
                self._emit_state("MEDIA SERVER OFFLINE")
                return False

            logger.info(f"[CaptureWorker] VideoCapture.isOpened() == True for {self.camera_id}")
            self._reconnect_delay = 1.0  # Reset backoff on success
            self._frames_read = 0
            self._fps_frame_count = 0
            self._last_fps_time = time.time()
            self._emit_state("STREAM STARTING")
            return True

        except Exception as e:
            logger.error(
                f"[CaptureWorker] Exception during connect:\n"
                f"  Camera ID: {self.camera_id}\n"
                f"  URL:       {self.rtsp_url}\n"
                f"  Error:     {e}\n"
                f"  Trace:     {traceback.format_exc()}\n"
                f"  Recovery:  Retrying after {self._reconnect_delay}s"
            )
            self._emit_state("DECODER ERROR", str(e))
            return False

    def _capture_loop(self):
        """Main loop: continuously reads frames and pushes JPEG-encoded bytes to queue."""
        while self._running.is_set():
            if not self._cap or not self._cap.isOpened():
                success = self._connect()
                if not success:
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, self._max_delay)
                    continue

            try:
                ret, frame = self._cap.read()
            except Exception as e:
                logger.error(
                    f"[CaptureWorker] cv2.read() raised exception:\n"
                    f"  Camera: {self.camera_id}\n"
                    f"  Error:  {e}\n"
                    f"  Trace:  {traceback.format_exc()}"
                )
                ret = False
                frame = None

            if not ret or frame is None:
                logger.warning(
                    f"[CaptureWorker] ret=False or frame=None for {self.camera_id}. "
                    f"Stream may have ended. Reconnecting in {self._reconnect_delay}s..."
                )
                self._emit_state("STREAM OFFLINE")
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_delay)
                continue

            # Validate frame dimensions
            if frame.size == 0 or len(frame.shape) < 2 or frame.shape[0] == 0 or frame.shape[1] == 0:
                logger.warning(f"[CaptureWorker] Corrupted/empty frame shape for {self.camera_id}: {frame.shape}")
                continue

            self._frames_read += 1
            self._fps_frame_count += 1

            # Emit CONNECTED state on first good frame
            if self._frames_read == 1:
                logger.info(
                    f"[CaptureWorker] First frame received for {self.camera_id}! "
                    f"Shape={frame.shape}, dtype={frame.dtype}"
                )
                self._emit_state("CONNECTED")

            # Emit FPS update every ~30 frames
            now = time.time()
            if self._fps_frame_count >= 30:
                elapsed = now - self._last_fps_time
                fps = self._fps_frame_count / elapsed if elapsed > 0 else 0
                self._emit_state("CONNECTED", f"Capture FPS: {fps:.1f}")
                self._fps_frame_count = 0
                self._last_fps_time = now

            self._push_to_queue(frame)

    def _push_to_queue(self, frame):
        """JPEG-encodes the frame and places it in the output queue.
        
        JPEG encoding reduces inter-process payload from ~6MB to ~50KB per frame.
        This is critical for stable operation with the 'spawn' multiprocessing context.
        """
        try:
            # Encode to JPEG at 85% quality — good balance of quality vs. speed
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                logger.warning(f"[CaptureWorker] cv2.imencode() failed for {self.camera_id}")
                return

            jpeg_bytes = buffer.tobytes()

            # Drain queue of old frames to keep only the latest (zero-latency guarantee)
            while not self.output_queue.empty():
                try:
                    self.output_queue.get_nowait()
                except Exception:
                    break

            self.output_queue.put_nowait((self.camera_id, time.time(), jpeg_bytes))

        except Exception as e:
            logger.debug(f"[CaptureWorker] Queue push failed for {self.camera_id} (dropping frame): {e}")
