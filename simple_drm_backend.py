import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional
from urllib.parse import urlparse


class DRMBackend:
    def __init__(self):
        self._codes: Dict[str, Dict[str, object]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _normalize_code(code: str) -> str:
        cleaned = re.sub(r"[^A-Z0-9]", "", str(code or "").strip().upper())
        if len(cleaned) != 6:
            raise ValueError("Code must be 6 characters")
        return cleaned

    def generate_code(self, app_id: str, max_uses: int = 1) -> Dict[str, object]:
        code = self._normalize_code(self._make_code())
        with self._lock:
            self._codes[code] = {
                "app_id": str(app_id),
                "max_uses": max(1, int(max_uses)),
                "uses_remaining": max(1, int(max_uses)),
                "used": 0,
                "appticket": "A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4E5F60718293",
                "eticket": "0102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F20",
            }
        return {"success": True, "code": code, "app_id": app_id, "max_uses": max_uses}

    def redeem_code(self, code: str) -> Dict[str, object]:
        normalized = self._normalize_code(code)
        with self._lock:
            entry = self._codes.get(normalized)
            if not entry:
                return {"success": False, "reason": "Unknown or expired code"}
            if int(entry["used"]) >= int(entry["max_uses"]):
                return {"success": False, "reason": "Code already used"}
            entry["used"] = int(entry["used"]) + 1
            entry["uses_remaining"] = int(entry["max_uses"]) - int(entry["used"])
            return {
                "success": True,
                "app_id": entry["app_id"],
                "appticket": entry["appticket"],
                "eticket": entry["eticket"],
                "uses_remaining": entry["uses_remaining"],
            }

    def _make_code(self) -> str:
        import random
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(random.choice(alphabet) for _ in range(6))


class _RequestHandler(BaseHTTPRequestHandler):
    server_version = "SimpleDRM/1.0"

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"success": True, "service": "simple_drm_backend"})
            return
        self._send_json(404, {"ok": False, "reason": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/drm/generate":
            result = self.server.backend.generate_code(
                payload.get("app_id", ""),
                payload.get("max_uses", 1),
            )
            self._send_json(200, result)
            return
        if parsed.path == "/drm/redeem":
            result = self.server.backend.redeem_code(payload.get("code", ""))
            self._send_json(200, result)
            return
        self._send_json(404, {"ok": False, "reason": "Not found"})

    def log_message(self, format, *args):
        return

    def _read_json(self) -> Dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(body) or {}
        except Exception:
            return {}

    def _send_json(self, status: int, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SimpleDRMHTTPServer(HTTPServer):
    def __init__(self, server_address, handler_cls, backend: DRMBackend):
        super().__init__(server_address, handler_cls)
        self.backend = backend


def start_server(backend: Optional[DRMBackend] = None, host: str = "0.0.0.0", port: Optional[int] = None):
    backend = backend or DRMBackend()
    port = int(port or os.environ.get("PORT", "8091"))
    server = SimpleDRMHTTPServer((host, port), _RequestHandler, backend)
    return server


if __name__ == "__main__":
    server = start_server()
    print(f"Simple DRM backend listening on http://0.0.0.0:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
