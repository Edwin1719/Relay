#!/usr/bin/env python3
"""Relay launcher — starts everything with a single command.

Opens the browser automatically when ready.
Ctrl+C stops all services cleanly.

Usage:
    python run.py                  # Development (backend + Vite HMR)
    python run.py --build          # Production preview (backend serves built frontend)
    python run.py --backend-only   # Only the backend, no browser
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

# ── ANSI helpers ────────────────────────────────────────────────

def _print(label, message, color=""):
    ts = time.strftime("%H:%M:%S")
    print(f" {color}{ts} [{label}]\x1b[0m {message}")


def info(msg):
    _print("RELAY", msg, "\x1b[36m")


def ok(msg):
    _print("  OK  ", msg, "\x1b[32m")


def warn(msg):
    _print(" INFO ", msg, "\x1b[33m")


def err(msg):
    _print("ERROR ", msg, "\x1b[31m")


# ── Process management ──────────────────────────────────────────

processes: list[subprocess.Popen] = []
_browser_opened = False


def _cleanup(signum=None, frame=None):
    info("Deteniendo servicios...")
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
    ok("Todo detenido.")
    sys.exit(0)


def _open_browser(url: str):
    global _browser_opened
    if not _browser_opened:
        webbrowser.open(url)
        _browser_opened = True
        ok(f"Navegador abierto en {url}")


def _wait_for_url(url: str, label: str, max_attempts=30):
    import urllib.request
    import urllib.error

    for attempt in range(max_attempts):
        try:
            urllib.request.urlopen(url, timeout=1)
            ok(f"{label} listo en {url}")
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


def run_backend():
    info("Iniciando backend (FastAPI)...")
    p = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    processes.append(p)

    if _wait_for_url("http://127.0.0.1:8000/api/status", "Backend"):
        return p
    err("El backend no respondió a tiempo.")
    _cleanup()


def run_frontend():
    info("Iniciando frontend (Vite)...")
    p = subprocess.Popen(
        ["npx.cmd", "vite", "--host"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    processes.append(p)

    if _wait_for_url("http://localhost:5173", "Frontend"):
        return p
    err("El frontend no respondió a tiempo.")
    _cleanup()


def stream_output(p: subprocess.Popen, prefix: str):
    try:
        if p.stdout:
            for line in iter(p.stdout.readline, ""):
                sys.stdout.write(f"  [{prefix}] {line}")
                sys.stdout.flush()
    except ValueError:
        pass


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Relay launcher")
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build frontend first, then serve from backend",
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Start only the backend",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication token (allow unauthenticated local access)",
    )
    args = parser.parse_args()

    print()
    print("  ╔══════════════════════════════╗")
    print("  ║      ⚡ Relay Launcher      ║")
    print("  ╚══════════════════════════════╝")
    print()

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    if args.no_auth:
        os.environ["KODAMA_NO_AUTH"] = "1"
        warn("Auth deshabilitado — el backend aceptará requests sin token")

    if args.build:
        info("Construyendo frontend...")
        result = subprocess.run(
            ["npx.cmd", "vite", "build"],
            cwd=FRONTEND_DIR,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            err("Build falló:")
            print(result.stderr)
            sys.exit(1)
        ok("Frontend construido")

    if args.backend_only:
        p = run_backend()
        if p:
            _open_browser("http://127.0.0.1:8000")
            stream_output(p, "backend")
    elif args.build:
        p = run_backend()
        if p:
            _open_browser("http://127.0.0.1:8000")
            stream_output(p, "backend")
    else:
        p_backend = run_backend()
        p_frontend = run_frontend()

        if p_backend and p_frontend:
            _open_browser("http://localhost:5173")
            print()
            print("  🚀  Relay está corriendo")
            print("  ─────────────────────────────────────────────")
            print("  Frontend:  http://localhost:5173")
            print("  Backend:   http://127.0.0.1:8000")
            print("  API Docs:  http://127.0.0.1:8000/docs")
            print()
            print("  Ctrl+C para detener todo")
            print("  ─────────────────────────────────────────────")
            print()

            import threading
            threads = [
                threading.Thread(target=stream_output, args=(p_backend, "backend"), daemon=True),
                threading.Thread(target=stream_output, args=(p_frontend, "frontend"), daemon=True),
            ]
            for t in threads:
                t.start()

            p_backend.wait()
            _cleanup()


if __name__ == "__main__":
    main()
