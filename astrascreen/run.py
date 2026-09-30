"""Start AstraScreen:  python run.py   then open http://localhost:8000"""
import argparse, sys, threading, webbrowser

p = argparse.ArgumentParser()
p.add_argument("--port", type=int, default=8000)
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--no-browser", action="store_true")
p.add_argument("--basic", action="store_true", help="use the built-in server even if FastAPI is installed")
a = p.parse_args()
url = f"http://localhost:{a.port}"
if not a.no_browser:
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

try:
    if a.basic:
        raise ImportError
    import uvicorn
    from app.server_fastapi import app  # noqa: F401
    print(f"AstraScreen (FastAPI) running at {url}  - press Ctrl+C to stop")
    uvicorn.run("app.server_fastapi:app", host=a.host, port=a.port, log_level="warning")
except ImportError:
    from app.server_basic import serve
    print(f"AstraScreen (built-in server) running at {url}  - press Ctrl+C to stop")
    print("Tip: pip install -r requirements.txt to use FastAPI.")
    try:
        serve(a.host, a.port)
    except KeyboardInterrupt:
        sys.exit(0)
