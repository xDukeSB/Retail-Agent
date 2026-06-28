# RetailAI Agent — Windows Deployment Guide

This guide outlines the procedure for installing the RetailAI Agent as a robust, auto-starting background service on Windows Edge PCs (e.g., store back-office computers).

## Prerequisites
Before running the installer, ensure the target Windows machine has the following installed and added to the system `PATH`:
1. **Python 3.9 or higher** (Ensure "Add Python to PATH" is checked during installation).
2. **Node.js (v18+) & npm** (Required for the Next.js frontend).
3. **PowerShell 5.1+** (Built into Windows 10/11).

## One-Click Installation

1. Open a **PowerShell terminal as Administrator**.
2. Navigate to the `deploy/windows` directory inside the project repository.
3. Execute the installer script:
   ```powershell
   .\install.ps1
   ```

### What the Installer Does:
- **MediaMTX**: Automatically downloads the latest Windows `amd64` release and extracts it.
- **Backend Environment**: Creates a Python virtual environment (`.venv`), upgrades `pip`, and installs all requirements (YOLO, ByteTrack, OpenCV, FastAPI, SQLAlchemy).
- **Frontend Environment**: Runs `npm install` and completely builds the production-ready Next.js bundle via `npm run build`.
- **NSSM Registration**: Downloads NSSM (Non-Sucking Service Manager) to wrap the apps.
- **Service Creation**: Registers 3 Windows Services that are configured to **start automatically on boot**:
  - `RetailAI_MediaMTX`
  - `RetailAI_Backend`
  - `RetailAI_Frontend`
- **Dashboard Launch**: Automatically opens your default web browser to `http://localhost:3000`.

## Verifying Services

You can verify the services are running by opening the **Windows Services App** (`services.msc`) and looking for:
- `RetailAI_MediaMTX`
- `RetailAI_Backend`
- `RetailAI_Frontend`

If a service fails to start, check the auto-generated log files located in the `tools/` directory (e.g., `tools/RetailAI_Backend.err`).

## Uninstallation

If you need to stop and remove the services (e.g., to perform a manual upgrade or migrate to a new PC), run the uninstaller:

1. Open **PowerShell as Administrator**.
2. Navigate to `deploy/windows`.
3. Execute:
   ```powershell
   .\uninstall.ps1
   ```
*(Note: This only removes the background services; it does not delete your local SQLite database or project files).*
