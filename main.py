from __future__ import annotations

import asyncio
import os
import time
from functools import partial
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="OmniBrowser Media Resolver API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

MAX_URL_LENGTH = 4096
MIN_INTERVAL_SECONDS = float(os.getenv("MIN_INTERVAL_SECONDS", "1.0"))
_last_request_by_ip: dict[str, float] = {}


def validate_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if len(value) > MAX_URL_LENGTH or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="A valid HTTP(S) URL is required")
    return value


def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    previous = _last_request_by_ip.get(ip, 0.0)
    if now - previous < MIN_INTERVAL_SECONDS:
        raise HTTPException(status_code=429, detail="Please wait before retrying")
    _last_request_by_ip[ip] = now
    # Keep the simple free-tier guard from growing forever.
    if len(_last_request_by_ip) > 10000:
        cutoff = now - 3600
        for key, timestamp in list(_last_request_by_ip.items()):
            if timestamp < cutoff:
                _last_request_by_ip.pop(key, None)


def _extract(url: str, audio_only: bool) -> dict[str, Any]:
    # No downloads are written to disk. yt-dlp only resolves metadata and a
    # time-limited direct CDN URL for media the caller is authorized to access.
    fmt = (
        "bestaudio[ext=m4a]/bestaudio/best"
        if audio_only
        else "best"
    )
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": fmt,
        "socket_timeout": 20,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
    if not info:
        raise ValueError("No media metadata was returned")
    requested = info.get("requested_formats") or []
    selected = requested[0] if requested else info
    direct_url = selected.get("url")
    if not direct_url:
        raise ValueError("The provider did not expose a direct stream URL")
    mime = selected.get("mime_type") or selected.get("ext") or ("audio/m4a" if audio_only else "video/mp4")
    return {
        "original_url": url,
        "title": info.get("title") or "Untitled media",
        "thumbnail_url": info.get("thumbnail"),
        "duration_seconds": info.get("duration") or 0,
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "stream_url": direct_url,
        "format": selected.get("ext") or "mp4",
        "mime_type": mime,
        "filesize": selected.get("filesize") or selected.get("filesize_approx") or 0,
        "quality": selected.get("format_note") or selected.get("resolution") or "best",
        "is_audio_only": audio_only,
        "headers": {"User-Agent": "Mozilla/5.0"},
        "expires_soon": True,
    }


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "running", "service": "omni-media-resolver", "version": app.version}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/resolve")
async def resolve_url(
    request: Request,
    url: str = Query(..., min_length=8, max_length=MAX_URL_LENGTH),
    audio: bool = False,
) -> dict[str, Any]:
    rate_limit(request)
    clean_url = validate_url(url)
    try:
        return await asyncio.wait_for(asyncio.to_thread(partial(_extract, clean_url, audio)), timeout=45)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Media provider timed out") from exc
    except (yt_dlp.utils.DownloadError, ValueError) as exc:
        # Avoid returning provider internals to the client.
        raise HTTPException(status_code=422, detail="This URL could not be resolved") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Media resolver temporarily unavailable") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
