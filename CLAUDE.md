# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Video Transcriber — a video-to-text transcription service using Alibaba's SenseVoice model for speech recognition. Optimized for Chinese, supports multilingual transcription. Processes videos locally (privacy-first).

**Python version: 3.8–3.11 (NOT 3.12+, PyTorch incompatibility)**

## Common Commands

```bash
# Run CLI
python main.py transcribe <file> --language zh --format srt --timestamps
python main.py batch <file_list.txt> --max-concurrent 2

# Start web API server
python main.py serve --port 8665
# Or directly:
uvicorn api.main:app --host 0.0.0.0 --port 8665 --reload

# Download model
python main.py download-model sensevoice-small

# System check
python main.py check

# Tests
pytest                                          # all tests with coverage
pytest tests/test_api.py                        # single file
pytest tests/test_api.py::TestHealthEndpoint::test_health_check  # single test
pytest -m unit                                  # unit tests only
pytest -m "not gpu and not network"             # skip GPU/network tests

# Lint / format
black . && isort . && flake8 . && mypy .
```

## Architecture

Layered service architecture with clear separation:

```
CLI (main.py, Click) / Web API (api/main.py, FastAPI) / WebSocket
        ↓
Service Layer: services/transcription_service.py → file_service.py, task_service.py
        ↓
Core Layer: core/engine.py (orchestrator) → downloader.py (audio extract), sensevoice_transcriber.py (ASR)
        ↓
Utilities: utils/audio/chunking.py, utils/ffmpeg/, utils/file/, utils/logging/, utils/retry.py
        ↓
Config/Data: config/settings.py (pydantic-settings), models/schemas.py (Pydantic models)
```

**Processing pipeline:** File input → audio extraction (FFmpeg) → audio chunking (long files) → SenseVoice ASR → post-processing (punctuation, special token cleanup) → output formatting (JSON/TXT/SRT/VTT)

### Key files

- `main.py` — CLI entry point (Click commands: transcribe, batch, serve, check, download-model, info, cleanup, models)
- `api/main.py` — FastAPI app; routes in `api/routes/` (health, transcribe); WebSocket in `api/websocket.py`
- `core/engine.py` — `VideoTranscriptionEngine` orchestrates the full pipeline
- `core/sensevoice_transcriber.py` — `SenseVoiceTranscriber` wraps FunASR/SenseVoice model
- `core/downloader.py` — `AudioExtractor` extracts audio via FFmpeg
- `services/transcription_service.py` — high-level API combining all core components
- `models/schemas.py` — all Pydantic data models (TranscriptionModel, Language, OutputFormat, ProcessOptions, etc.)
- `config/settings.py` — type-safe config via pydantic-settings, loads from env vars and `.env`

### Configuration

All settings in `config/settings.py`, overridable via environment variables or `.env` file. Key areas:
- Model: `DEFAULT_MODEL`, `DEFAULT_LANGUAGE`, `ENABLE_GPU`, `MODEL_CACHE_DIR`
- Audio chunking: `ENABLE_AUDIO_CHUNKING`, `CHUNK_DURATION_SECONDS`
- Server: `HOST`, `PORT`, `WORKERS`, `CORS_ORIGINS`, `RATE_LIMIT_PER_MINUTE`
- Tasks: `TASK_TIMEOUT`, `MAX_CONCURRENT_TASKS`, `TASK_RETENTION_HOURS`

## Testing

pytest.ini configures: strict markers, auto asyncio mode, coverage for `core/`, `api/`, `utils/`.

Markers: `unit`, `integration`, `slow`, `network`, `gpu`

## Docker

```bash
docker build -t video-transcriber -f docker/Dockerfile .
docker run --gpus all -p 8665:8665 -v $(pwd)/temp:/app/temp video-transcriber
# Or: docker-compose -f docker/docker-compose.yml up -d
```

## Dependencies

Core stack: FastAPI + Uvicorn, FunASR + ModelScope + PyTorch (SenseVoice ASR), Pydantic, Click + Rich (CLI), pydub/librosa (audio), loguru (logging), httpx (async HTTP).

The project includes `ffmpeg_bin/` for bundled FFmpeg on Windows — `check_ffmpeg_installed()` in `utils/ffmpeg/` handles detection.
