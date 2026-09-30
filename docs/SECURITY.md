# Security and local privacy

## What is implemented (and tested in `backend/tests/integration/test_security.py`)

| Control | Implementation |
|---|---|
| Loopback only | `app.run` refuses non-loopback hosts; binds `127.0.0.1`. |
| Per-session token | Random 256-bit token per launch. Required as `X-HVS-Token` on every `/api` call except `GET /api/health`. Constant-time comparison. |
| Token in URLs | Only for `GET` media/SSE routes (`<audio>`, `EventSource` can't send headers): `/api/assets/{id}/audio`, `/api/exports/{id}/file`, `/api/events`, `/api/jobs/{id}/events`, transcript export. The launcher puts the token in the URL *fragment*, which browsers never send to servers. |
| Origin check | Any request with an `Origin` header not in the allowlist (`http://127.0.0.1:<port>`, `http://localhost:<port>`, optional dev origins) → 403. Combined with the custom header requirement this blocks cross-site request forgery. |
| Host check | `TrustedHostMiddleware` rejects non-loopback `Host` headers (DNS-rebinding defence). |
| CORS | Only for explicitly configured dev origins. |
| Security headers | CSP (`default-src 'self'`, no framing, no objects), `nosniff`, `no-referrer`, COOP. |
| Uploads | Size limit enforced while streaming; content validated by **decoding with FFmpeg**, not by extension; duration limits; files re-encoded into managed storage. |
| Paths | API accepts IDs only. Storage keys are server-generated and resolved with a containment check. Export file names are sanitised and never overwrite existing files. |
| Subprocesses | FFmpeg/ffprobe via argument arrays (no shell), fixed codecs/filters, timeouts. |
| Archives | Model tarballs extracted with Python's `filter="data"` (blocks `..`, absolute paths, devices, unsafe links); checksum verified before extraction when pinned. |
| Downloads | HTTPS only; only URLs from the pinned registry; explicit user approval in the UI. |
| Logs | IDs, codes and timings only. Script text and recordings are not logged. Validation errors don't echo input. |
| Errors | Unexpected exceptions return a generic message; details stay in the local log. |
| Telemetry | None. No analytics code exists. No remote processing exists. |

## Desktop (Electron)

`nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`; the preload exposes only
`token()`, `revealExport(fileName)` and `platform`. IPC handlers verify the sender URL and
validate arguments (basename only, must exist inside the exports folder). Navigation away
from the local origin is blocked; new windows are denied (HTTPS links open in the system
browser). Only microphone (`media`/audio) permission is granted, only to the local origin.

## Consent

Adding a voice requires choosing a permission basis and confirming it. The consent record
(basis, statement, timestamp, optional document reference, revocation time) is stored. **A
checkbox is not proof of ownership**; the UI says so. Revoked profiles cannot be used for
generation. Deleting a voice deletes the reference audio and keeps the consent record
(marked revoked, no audio) as an audit trail.

## Known limitations

- Any local process running as the same OS user could read the database/files or the
  token from process arguments/environment; this is a single-user desktop tool.
- The optional secret store for external credentials is not implemented because no external
  service is integrated.
- The unsigned desktop build will trigger SmartScreen/Gatekeeper warnings.
