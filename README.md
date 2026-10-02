# OmniBrowser Media Resolver API

FastAPI service for resolving public media URLs through `yt-dlp`. It returns metadata and a short-lived direct stream URL; it does not store or proxy media files.

## Endpoints

- `GET /health` — Render health check.
- `GET /resolve?url=<encoded-url>` — resolve a public URL.
- `GET /resolve?url=<encoded-url>&audio=true` — prefer an audio-only stream.

Example:

```bash
curl --get 'https://YOUR-SERVICE.onrender.com/resolve' \
  --data-urlencode 'url=https://www.youtube.com/watch?v=VIDEO_ID'
```

## Deploying on Render

The included `render.yaml` uses the free Python web service, installs `requirements.txt`, starts Uvicorn on `$PORT`, and enables automatic deploys from the connected GitHub `main` branch.

## Important operational notes

- Direct CDN URLs expire. The Android client must resolve again when a download is retried or a URL expires.
- The free Render instance can sleep when idle, so the first request after inactivity can be slow. A paid always-on instance or an external uptime monitor is needed for strict latency guarantees.
- Provider availability changes over time. `yt-dlp` is pinned to a compatible range and should be updated regularly when providers change their protocols.
- Use the service only for media you are authorized to download and in accordance with each provider's terms and applicable law.
- This service intentionally does not bypass authentication, DRM, private content, or access controls.
