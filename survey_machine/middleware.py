"""Bound request bodies and set browser security/CORS policy without native I/O."""

import json


class SecurityMiddleware:
    def __init__(self, app, cors_origins=(), max_body=512 * 1024):
        self.app, self.cors_origins, self.max_body = app, cors_origins, max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode()
        allowed = self.cors_origins
        if "env" in scope:
            allowed = tuple(v.strip() for v in str(scope["env"].CORS_ORIGINS).split(",") if v.strip())
        cors_headers = []
        if origin in allowed:
            cors_headers = [(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin"),
                            (b"access-control-expose-headers", b"Content-Disposition")]
        path = scope["path"]
        docs = path in ("/docs", "/docs/oauth2-redirect", "/redoc")
        script = "'self' https://cdn.jsdelivr.net 'unsafe-inline'" if docs else "'self'"
        style = "'self' https://cdn.jsdelivr.net 'unsafe-inline'" if docs else "'self'"
        ancestors = "*" if path.startswith("/s/") else "'self'"
        policy = f"default-src 'self'; script-src {script}; style-src {style}; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors {ancestors}"

        async def safe_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend(cors_headers)
                response_headers.extend([(b"x-content-type-options", b"nosniff"),
                                         (b"referrer-policy", b"no-referrer"),
                                         (b"content-security-policy", policy.encode()),
                                         (b"cache-control", b"no-store"),
                                         (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")])
                message = {**message, "headers": response_headers}
            await send(message)

        async def reject(status, detail):
            await safe_send({"type": "http.response.start", "status": status,
                             "headers": [(b"content-type", b"application/json")]})
            await safe_send({"type": "http.response.body", "body": json.dumps({"detail": detail}).encode()})

        if scope["method"] == "OPTIONS" and b"access-control-request-method" in headers:
            if origin not in allowed:
                return await reject(403, "This browser origin is not allowed.")
            requested_method = headers[b"access-control-request-method"].decode().upper()
            requested_headers = {h.strip().lower() for h in headers.get(b"access-control-request-headers", b"").decode().split(",") if h.strip()}
            if requested_method not in {"GET", "POST", "PUT", "DELETE"} or requested_headers - {"content-type", "x-api-key"}:
                return await reject(403, "This cross-origin request is not allowed.")
            await safe_send({"type": "http.response.start", "status": 204, "headers": [
                (b"access-control-allow-methods", b"GET, POST, PUT, DELETE"),
                (b"access-control-allow-headers", b"Content-Type, X-API-Key"),
                (b"access-control-max-age", b"600")]})
            return await safe_send({"type": "http.response.body", "body": b""})
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            chunks, length = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                length += len(chunk)
                if length > self.max_body:
                    return await reject(413, "Request body exceeds the 512 KiB limit.")
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body, consumed = b"".join(chunks), False

            async def replay_receive():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()
            return await self.app(scope, replay_receive, safe_send)
        return await self.app(scope, receive, safe_send)
