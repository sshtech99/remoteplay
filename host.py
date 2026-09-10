import argparse
import asyncio
import base64
import contextlib
import ipaddress
import json
import secrets
import ssl
import time
import zipfile
import pathlib
from typing import Any, Dict, Tuple

import aiohttp
from aiohttp import web
import mss
import pyautogui


DEFAULT_FPS = 12
MAX_EVENTS_PER_SECOND = 300
PAIR_CODE_LEN = 8
PAIR_TTL_SECONDS = 120
SESSION_TTL_SECONDS = 600
PACK_NAME = "simple-remote-package.zip"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _now() -> float:
    return time.time()


def _build_acl(allow_ips: str):
    nets = set()
    for raw in allow_ips.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if "/" in raw:
            nets.add(ipaddress.ip_network(raw, strict=False))
        else:
            nets.add(ipaddress.ip_network(f"{raw}/32", strict=False))
    return nets


def _is_allowed(remote: str | None, allow_nets) -> bool:
    if not allow_nets:
        return True
    if not remote:
        return False
    ip_text = remote
    if ip_text.startswith("["):
        ip_text = ip_text[1:].split("]")[0]
    elif ":" in ip_text and ip_text.count(":") > 1:
        # IPv6
        pass
    elif ":" in ip_text:
        ip_text = ip_text.split(":")[0]
    ip = ipaddress.ip_address(ip_text)
    return any(ip in net for net in allow_nets)


def _ssl_context(cert: str | None, key: str | None) -> ssl.SSLContext | None:
    if not cert and not key:
        return None
    if not cert or not key:
        raise ValueError("Informe ssl-cert e ssl-key juntos.")
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    return ctx


def _make_pair_code(length: int = PAIR_CODE_LEN) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def stream_screen(ws: web.WebSocketResponse, width: int, height: int, interval: float):
    loop = asyncio.get_running_loop()
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        monitor["top"] = 0
        monitor["left"] = 0
        monitor["width"] = width
        monitor["height"] = height

        while not ws.closed:
            start = loop.time()
            img = sct.grab(monitor)
            png_bytes = mss.tools.to_png(img.rgb, img.size)
            encoded = base64.b64encode(png_bytes).decode("ascii")
            await ws.send_json(
                {
                    "type": "frame",
                    "w": width,
                    "h": height,
                    "ts": _now(),
                    "img": encoded,
                }
            )
            elapsed = loop.time() - start
            await asyncio.sleep(max(0.0, interval - elapsed))


async def handle_input(event: Dict[str, Any]):
    etype = event.get("type")
    if etype == "mouse":
        x = _safe_float(event.get("x"))
        y = _safe_float(event.get("y"))
        action = event.get("action")
        button = event.get("button", "left")
        client_w = max(1.0, _safe_float(event.get("cw", 0.0)))
        client_h = max(1.0, _safe_float(event.get("ch", 0.0)))
        host_w, host_h = pyautogui.size()
        sx = int((x / client_w) * host_w)
        sy = int((y / client_h) * host_h)

        if action == "move":
            pyautogui.moveTo(sx, sy)
        elif action == "down":
            pyautogui.mouseDown(x=sx, y=sy, button=button)
        elif action == "up":
            pyautogui.mouseUp(x=sx, y=sy, button=button)
        elif action == "scroll":
            dy = _safe_float(event.get("dy"))
            pyautogui.scroll(-int(dy), x=sx, y=sy)
    elif etype == "key":
        code = event.get("code")
        action = event.get("action")
        if not code or not isinstance(code, str):
            return
        if action == "down":
            pyautogui.keyDown(code)
        elif action == "up":
            pyautogui.keyUp(code)


def _cleanup_state(state: Dict[str, Tuple[float, bool]]) -> None:
    now = _now()
    for key, (expires, _approved) in list(state["pair_codes"].items()):
        if expires < now:
            state["pair_codes"].pop(key, None)
    for sid, (expires, _payload) in list(state["sessions"].items()):
        if expires < now:
            state["sessions"].pop(sid, None)


async def create_pair(request: web.Request):
    app = request.app
    if not app["pairing_enabled"]:
        return web.Response(status=404, text="pairing disabled")
    now = _now()
    code = _make_pair_code()
    while code in app["pair_codes"]:
        code = _make_pair_code()
    app["pair_codes"][code] = (now + PAIR_TTL_SECONDS, False)
    return web.json_response({"code": code, "expires_in": PAIR_TTL_SECONDS})


async def request_session(request: web.Request):
    app = request.app
    if not app["pairing_enabled"]:
        return web.Response(status=404, text="pairing disabled")
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    code = (payload.get("code") or "").strip().upper()
    _cleanup_state(app)

    pair = app["pair_codes"].get(code)
    if not pair:
        return web.Response(status=403, text="invalid/expired code")
    if _now() > pair[0]:
        app["pair_codes"].pop(code, None)
        return web.Response(status=403, text="code expired")

    app["pair_codes"].pop(code, None)
    sid = secrets.token_urlsafe(12)
    expires = _now() + SESSION_TTL_SECONDS
    app["sessions"][sid] = (expires, app["auto_approve"])
    if app["auto_approve"]:
        print(f"[PAIR] sessão auto-aprovada: {sid}")
    print(f"[PAIR] sessao criada: {sid} para codigo {code}")
    return web.json_response({"sid": sid, "expires_in": SESSION_TTL_SECONDS, "status": "pending"})


async def session_status(request: web.Request):
    app = request.app
    sid = request.query.get("sid", "")
    _cleanup_state(app)
    if not sid:
        return web.Response(status=400, text="sid required")
    if sid not in app["sessions"]:
        return web.json_response({"exists": False, "status": "not_found"})
    expires, approved = app["sessions"][sid]
    if _now() > expires:
        app["sessions"].pop(sid, None)
        return web.json_response({"exists": False, "status": "expired"})
    return web.json_response(
        {"exists": True, "status": "approved" if approved else "pending", "expires_in": int(expires - _now())}
    )


async def approve_session(request: web.Request):
    app = request.app
    if request.query.get("token", "") != app["token"]:
        return web.Response(status=403, text="invalid token")
    sid = request.query.get("sid", "")
    if sid not in app["sessions"]:
        return web.Response(status=404, text="session not found")
    expires, _ = app["sessions"][sid]
    if _now() > expires:
        app["sessions"].pop(sid, None)
        return web.Response(status=404, text="session expired")
    app["sessions"][sid] = (expires, True)
    return web.json_response({"sid": sid, "status": "approved"})


async def active_sessions(request: web.Request):
    app = request.app
    token = request.query.get("token", "")
    if token != app["token"]:
        return web.Response(status=403, text="invalid token")
    _cleanup_state(app)
    sessions = []
    for sid, (exp, approved) in list(app["sessions"].items()):
        sessions.append(
            {
                "sid": sid,
                "expires_in": int(exp - _now()),
                "approved": approved,
            }
        )
    pairs = []
    for code, (exp, _) in list(app["pair_codes"].items()):
        pairs.append({"code": code, "expires_in": int(exp - _now())})
    return web.json_response({"pairs": pairs, "sessions": sessions})


def _validate_auth(request: web.Request) -> bool:
    app = request.app
    if not app["pairing_enabled"]:
        return request.query.get("token", "") == app["token"]
    sid = request.query.get("sid", "")
    token = request.query.get("token", "")
    if token and token == app["token"]:
        return True
    _cleanup_state(app)
    if sid and sid in app["sessions"]:
        expires, approved = app["sessions"][sid]
        if _now() > expires:
            app["sessions"].pop(sid, None)
            return False
        return approved
    return False


async def websocket_handler(request: web.Request):
    app = request.app
    if not _is_allowed(request.remote, app["allow_nets"]):
        return web.Response(status=403, text="forbidden ip")

    if not _validate_auth(request):
        return web.Response(status=403, text="forbidden")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    app["connections"].add(ws)

    screen_w, screen_h = pyautogui.size()
    await ws.send_json({"type": "hello", "screen": {"w": screen_w, "h": screen_h}, "server": "simple-remote-core"})

    stream_task = asyncio.create_task(
        stream_screen(ws, width=screen_w, height=screen_h, interval=app["frame_interval"])
    )
    window_start = 0.0
    event_count = 0

    try:
        async for message in ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                now = _now()
                if now - window_start > 1.0:
                    window_start = now
                    event_count = 0
                event_count += 1
                if event_count > MAX_EVENTS_PER_SECOND:
                    continue

                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError:
                    continue

                if payload.get("type") == "ping":
                    await ws.send_json({"type": "pong", "ts": now})
                    continue
                await handle_input(payload)
            elif message.type == aiohttp.WSMsgType.ERROR:
                break
    finally:
        app["connections"].discard(ws)
        stream_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stream_task


async def index(request: web.Request):
    return web.FileResponse("./viewer/index.html")


def create_app(token: str, frame_interval: float, allow_nets, pairing_enabled: bool):
    app = web.Application()
    app["token"] = token
    app["frame_interval"] = frame_interval
    app["allow_nets"] = allow_nets
    app["pairing_enabled"] = pairing_enabled
    app["connections"] = set()
    app["pair_codes"] = {}
    app["sessions"] = {}
    app["auto_approve"] = False
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/pair", create_pair)
    app.router.add_post("/pair", request_session)
    app.router.add_get("/session-status", session_status)
    app.router.add_get("/admin/sessions", active_sessions)
    app.router.add_post("/approve", approve_session)
    app.router.add_get("/health", lambda req: web.json_response({"ok": True, "connections": len(app["connections"])}))
    return app


def parse_args():
    p = argparse.ArgumentParser(description="Servidor simples de acesso remoto")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default="changeme")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS)
    p.add_argument("--allow-ips", default="", help="IPs ou CIDRs separados por vírgula")
    p.add_argument("--ssl-cert", default="")
    p.add_argument("--ssl-key", default="")
    p.add_argument("--pairing", action="store_true", help="Habilita conexão por código de pareamento")
    p.add_argument("--auto-approve", action="store_true", help="Auto-aprova sessões geradas por código")
    p.add_argument("--package", action="store_true", help="Gera pacote zip pronto para distribuição")
    return p.parse_args()


def package_distribution(output_dir: str, files: Tuple[str, ...] = ("host.py", "viewer/index.html", "requirements.txt", "README.md")):
    output_path = pathlib.Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    archive = output_path / PACK_NAME
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            p = pathlib.Path(file_path)
            if p.exists():
                zf.write(p, arcname=p.as_posix())
        scripts = [
            "scripts/start-host.bat",
            "scripts/start-host-pairing.bat",
            "scripts/start-viewer.bat",
            "scripts/install.ps1",
            "scripts/install.bat",
            "scripts/cloud-bootstrap.ps1",
        ]
        for s in scripts:
            p = pathlib.Path(s)
            if p.exists():
                zf.write(p, arcname=p.as_posix())
    return archive.as_posix()


def main():
    args = parse_args()
    allow_nets = _build_acl(args.allow_ips)
    frame_interval = 1.0 / args.fps if args.fps > 0 else 1.0 / DEFAULT_FPS
    ssl_ctx = _ssl_context(
        args.ssl_cert if args.ssl_cert else None,
        args.ssl_key if args.ssl_key else None,
    )
    app = create_app(
        token=args.token,
        frame_interval=frame_interval,
        allow_nets=allow_nets,
        pairing_enabled=args.pairing,
    )
    app["auto_approve"] = args.auto_approve

    scheme = "wss" if ssl_ctx else "ws"
    proto = "https" if ssl_ctx else "http"
    print("[*] Token de controle interno:", args.token)
    print(f"[*] Viewer:    {proto}://{args.host}:{args.port}/")
    print(f"[*] WebSocket: {scheme}://{args.host}:{args.port}/ws?token=<token>|sid=<id>")
    print(f"[*] API pareamento: POST {scheme}://{args.host}:{args.port}/pair")
    print(f"[*] Aprovar sessão: POST {scheme}://{args.host}:{args.port}/approve?token=<token>&sid=<sid>")
    if allow_nets:
        print("[*] ACL IP ativa:")
        for net in sorted(allow_nets, key=lambda n: str(n)):
            print(f"    - {net}")
    else:
        print("[*] ACL IP desativada (qualquer IP)")
    print(f"[*] FPS: {args.fps}")
    print(f"[*] Pareamento: {'ativado' if args.pairing else 'desativado'}")

    if args.pairing:
        print("[*] Gere código: GET /pair e compartilhe com o cliente no chat")

    if args.package:
        archive_path = package_distribution(".")
        print(f"[*] Pacote criado em: {archive_path}")
        return

    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_ctx)


if __name__ == "__main__":
    main()
