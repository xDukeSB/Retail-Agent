# RetailAI Agent Context & State Tracker

This file serves as a persistent memory and state tracker for the coding assistant. If the assistant loses context, forgets active configuration values, or makes errors regarding setup parameters, refer directly to this file.

---

## 📋 Project Overview: What We Are Building
**RetailAI Local Agent** is a production-grade, local-first CCTV AI analytics platform designed to transform existing standard IP/RTSP security cameras in retail stores into intelligent business sensors.

It tracks customer behavior, counts foot traffic, runs queue analytics, maps dwell-time heatmaps, and triggers real-time retail events completely on-premise without requiring expensive cloud GPU infrastructure.

---

## 🎯 Main Features & Important Points
1. **Local-First Processing:** Runs fully offline on local store PCs. Data is saved in a local SQLite database and periodically synced to a cloud backend (when connected) to protect customer privacy and eliminate bandwidth costs.
2. **Real-time Ingestion & Multi-Object Tracking:** Uses isolated processes per camera stream (to avoid bottlenecks), powered by **YOLOv8n** for object detection and **ByteTrack** for high-precision person re-identification and path tracking.
3. **Low-latency Streaming:** Employs zero-latency bounded frame queues (older frames are dropped instantly if inference lags behind capture) to ensure real-time analytics. **Frames are JPEG-encoded before inter-process transfer** to reduce payload from ~6MB to ~50KB per frame.
4. **Interactive Dashboard:** Built using Next.js (App Router), featuring live MJPEG video streams overlayed with active YOLO bounding boxes, real-time WebSocket camera state updates (CONNECTING → CONNECTED → INFERENCE RUNNING), zone management, and analytics timelines.
5. **Zero-Configuration Deployment:** Distributed as a lightweight single-file ZIP archive with a PowerShell installer that automatically provisions prerequisites (Node, Python, MediaMTX, GPU libraries) on store machines.

---

## 1. Core Deployment & Version Tracking
* **Active Version (v-number):** `v=32`
* **One-Line Store Installation Command:**
  ```powershell
  iwr -useb https://storage.googleapis.com/retailai-downloads/bootstrapper.ps1?v=32 | iex
  ```
* **ZIP Generation Script:** `archive.py` (Excludes `.pt` weights, `.db` databases, and dependency folders to keep installer size at a lean ~700 KB).
* **ZIP Archive Name:** `RetailAI_Agent_Production_Ready.zip`

---

## 2. Test Environment Parameters
* **Verified RTSP Stream URL:** `rtsp://127.0.0.1:8554/store`
* **Local Media Server:** MediaMTX (Running locally on Windows test environment)
* **Local Backend URL:** `http://127.0.0.1:8000` (FastAPI/Uvicorn)
* **Local Frontend URL:** `http://127.0.0.1:3000` (Next.js App Router)
* **Database Path:** `apps/backend/data/db/retailai.db` (SQLite)
* **Default Admin Credentials:** `admin@retailai.local` / `admin123`

---

## 3. Active Architecture & Implementation Details

### CV Pipeline (3-Queue Architecture — CRITICAL)
```
CaptureWorker ──[frame_queue]──► InferenceWorker ──[annotated_queue]──► EngineManager.latest_frames
     │                                   │                                        │
     └──[event_queue]────────────────────┘                              MJPEG /video_feed endpoint
                                         │
                                   [event_queue]
                                         │
                                   EngineManager._event_queue_bridge()
                                         │
                                   asyncio.Queue (_async_event_queue)
                                         │
                                   EventEngine.run_loop()
                                         │
                          ┌──────────────┴──────────────────┐
                          │                                  │
                     SQLite DB update              WebSocket broadcast
                    (Camera.status)            (camera_status_update)
                                                             │
                                                      Frontend liveStates
                                                   (per-camera WS state map)
```

### Key Architectural Decisions
- **`mp.get_context('spawn')`** — used for all child processes (required for CUDA/PyTorch on Windows/macOS).
- **JPEG encoding in CaptureWorker** — frames are encoded to JPEG (~50KB) before `output_queue.put_nowait()`. InferenceWorker decodes with `cv2.imdecode()` before running YOLO.
- **Separate `annotated_queue`** — InferenceWorker pushes JPEG-annotated frames to `annotated_queue` (NOT the event_queue) for MJPEG streaming.
- **`daemon=True`** — all child processes are daemonized to ensure they terminate with the parent.
- **`start_async()`** — `EngineManager.start()` is sync (mp setup). `await engine_manager.start_async()` must be called inside the FastAPI async lifespan to safely create asyncio bridge tasks.

### Queue Map
| Queue | Producer | Consumer | Content |
|---|---|---|---|
| `frame_queue` | `CaptureWorker` | `InferenceWorker` | `(camera_id, timestamp, jpeg_bytes)` |
| `annotated_queue` | `InferenceWorker` | `EngineManager._annotated_queue_bridge` | `(camera_id, timestamp, jpeg_bytes)` |
| `event_queue` | `CaptureWorker` + `InferenceWorker` | `EngineManager._event_queue_bridge` | `{"type": "camera_state"/"detections", ...}` |

### WebSocket Flow
- Backend: `ws://localhost:8000/ws/live`
- Frontend connects in `cameras/page.tsx` using `useEffect` + auto-reconnect (3s backoff)
- Events received: `camera_status_update` → updates `liveStates[camera_id]` → reactive UI
- Events received: `live_detections` → available for future bounding-box overlay
- **`ws_manager.broadcast()`** accepts raw `dict` OR pre-serialized `str` — never double-encodes

### MJPEG Stream
- Endpoint: `GET /api/v1/cameras/{camera_id}/video_feed`
- Waits up to **10 seconds** for first frame before streaming (prevents premature browser `img.onerror`)
- Response type: `multipart/x-mixed-replace; boundary=frame`
- Headers: `Cache-Control: no-cache` — forces browser to keep connection alive
- Frontend `<img>` tag auto-reloads with cache-busting `?t=Date.now()` when camera transitions to `active`

### Auth (Login-Free Mode)
- The login page is **bypassed** — `auth.tsx` auto-signs in as admin on page load.
- If no token in `localStorage`, it calls `POST /api/v1/auth/login` with:
  * **Email:** `admin@retailai.local`
  * **Password:** `admin123`
- Successful token is stored in `localStorage["retailai_token"]` for subsequent requests.

---

## 4. Five Forensic Bugs Fixed (v22)

| # | Bug | Root Cause | Fix |
|---|---|---|---|
| 1 | WebSocket events never parsed by frontend | `event_engine.py` called `broadcast(json.dumps({...}))` and `broadcast()` called `json.dumps()` again — double encoding | Pass raw dicts; `broadcast()` serializes internally |
| 2 | MJPEG feed always empty (`latest_frames` never populated) | `InferenceWorker` used same queue for annotated frames & events; annotated frames never reached `latest_frames` | Added separate `annotated_queue` + bridge task |
| 3 | Pipeline stalled / crashed silently | Raw NumPy frames (~6MB) sent over `mp.Queue` in spawn context causing serialization slowdowns | JPEG-encode in `CaptureWorker`, decode in `InferenceWorker` |
| 4 | Camera status stays `inactive` after adding | `create_camera` never called `engine_manager.add_camera()` | Auto-start worker when `is_enabled=True` on create |
| 5 | Bridge asyncio tasks never created | `asyncio.create_task()` called inside sync `start()` method before event loop was running | Split into `start()` + `await start_async()` in lifespan |

---

## 5. Key File Map

| File | Purpose |
|---|---|
| `apps/backend/main.py` | FastAPI app + lifespan (startup order critical) |
| `apps/backend/services/cv_pipeline/capture_worker.py` | RTSP → JPEG → frame_queue |
| `apps/backend/services/cv_pipeline/inference_worker.py` | JPEG → YOLO → annotated_queue + event_queue |
| `apps/backend/services/cv_pipeline/engine_manager.py` | mp.Queue → asyncio bridge, latest_frames cache |
| `apps/backend/services/cv_pipeline/event_engine.py` | asyncio events → SQLite + WebSocket broadcast |
| `apps/backend/routers/cameras.py` | Camera CRUD + MJPEG `/video_feed` + `/diagnostics` |
| `apps/backend/routers/websocket.py` | WS connection manager + broadcast |
| `apps/backend/services/auth.py` | JWT auth, role checker, admin credentials |
| `apps/frontend/src/app/cameras/page.tsx` | Live camera dashboard with WS state updates |
| `apps/frontend/src/lib/auth.tsx` | Auto-login on startup |
| `apps/frontend/src/lib/api.ts` | API client, token management |
| `archive.py` | Build ZIP for Windows deployment |
| `deploy/windows/bootstrapper.ps1` | One-line Windows installer |

---

## 6. Assistant Guidelines
1. **Always check this file first** before answering questions about active URLs, ports, credentials, or installation one-liners.
2. **Increment the version number** (`v=NN`) in this file and in the bootstrapper URL whenever a deployment-impacting code change is made.
3. **Never send raw NumPy arrays through `mp.Queue`** — always JPEG-encode first.
4. **Never call `asyncio.create_task()` from a sync function** — use `start_async()` pattern.
5. **Never pass `json.dumps()` output to `ws_manager.broadcast()`** — pass raw dicts only.
6. Keep the 3-queue architecture diagram in Section 3 up to date with any pipeline changes.
