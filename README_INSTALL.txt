=====================================================================
  RetailAI Agent — Installation Instructions
  v39 | Local-First CCTV AI Platform for Retail Stores
=====================================================================

WHAT IS THIS?
  RetailAI Agent turns your existing RTSP security cameras into smart
  retail analytics sensors — foot traffic, queue detection, dwell-time
  heatmaps, all running 100% on-premise with no cloud fees.

=====================================================================
  HOW TO INSTALL (Windows 10 / 11 / Server 2019+)
=====================================================================

OPTION A — One-Line Cloud Install (requires internet):
  1. Open PowerShell as Administrator.
  2. Paste this command and press Enter:

     iwr -useb https://raw.githubusercontent.com/xDukeSB/Retail-Agent/main/deploy/windows/bootstrapper.ps1 | iex

  The installer downloads the latest ZIP from GitHub Releases, extracts it to C:\RetailAI,
  installs Python 3.11, Node.js 20, MediaMTX, and all dependencies
  automatically, then registers everything as Windows Services.

----------------------------------------------------------------------

OPTION B — Local Install from this ZIP (no internet needed after copy):
  1. Copy this ZIP file to the Windows machine.
  2. Extract the ZIP to any folder (e.g. C:\RetailAI).
  3. Open PowerShell as Administrator.
  4. Navigate to the extracted folder:

     cd C:\RetailAI

  5. Run the installer:

     powershell -ExecutionPolicy Bypass -File deploy\windows\bootstrapper.ps1

  The script detects it is running from an extracted package and skips
  the download step automatically.

----------------------------------------------------------------------

OPTION C — Double-click (simplest):
  1. Extract the ZIP to C:\RetailAI.
  2. Right-click:  deploy\windows\bootstrapper.ps1
  3. Select:       "Run with PowerShell"
  4. If prompted about execution policy, type Y and press Enter.

=====================================================================
  AFTER INSTALLATION
=====================================================================
  Dashboard:  http://localhost:3000
  API Docs:   http://localhost:8000/api/docs
  Login:      admin@retailai.local / admin123 (auto-login by default)

  Three Windows Services are installed and auto-start on boot:
    • RetailAI_MediaMTX   — RTSP relay server
    • RetailAI_Backend    — FastAPI AI backend (port 8000)
    • RetailAI_Frontend   — Next.js dashboard (port 3000)

=====================================================================
  ADDING YOUR FIRST CAMERA
=====================================================================
  1. Open the dashboard: http://localhost:3000
  2. Click "Cameras" in the sidebar.
  3. Click "+ Add RTSP Camera".
  4. Enter a name and your RTSP URL, e.g.:
       rtsp://admin:password@192.168.1.100/stream
  5. Click "Connect Camera".
  6. The status badge will update in real-time:
       CONNECTING → CONNECTED → INFERENCE RUNNING (LIVE)

  Test stream (if using the bundled FFmpeg/MediaMTX demo):
       rtsp://127.0.0.1:8554/store

=====================================================================
  TROUBLESHOOTING
=====================================================================
  Backend logs:   C:\RetailAI\tools\RetailAI_Backend.log
  Backend errors: C:\RetailAI\tools\RetailAI_Backend.err
  MediaMTX logs:  C:\RetailAI\tools\RetailAI_MediaMTX.log

  Check service status:
    Get-Service RetailAI_*

  Restart all services:
    Restart-Service RetailAI_MediaMTX, RetailAI_Backend, RetailAI_Frontend

  Uninstall:
    powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall.ps1

=====================================================================
  ARCHITECTURE OVERVIEW
=====================================================================
  RTSP Camera
      ↓ (rtsp://)
  MediaMTX (RTSP relay)
      ↓
  CaptureWorker (OpenCV, JPEG-encoded frames)
      ↓ [frame_queue]
  InferenceWorker (YOLOv8n + ByteTrack)
      ↓ [annotated_queue]     ↓ [event_queue]
  MJPEG /video_feed       EventEngine
                              ↓               ↓
                          SQLite DB      WebSocket
                                             ↓
                                     Browser Dashboard

  Privacy: No facial recognition. No biometric data stored.
           All tracking is anonymous (Visitor #ID only).

=====================================================================
