"""FastAPI web server (used automatically when FastAPI + Uvicorn are installed)."""
from fastapi import FastAPI, Request
from fastapi.responses import Response
from . import api

app = FastAPI(title="AstraScreen", description="AI-driven anomaly detection in component burn-in (SIH26170)")


@app.on_event("startup")
def _startup():
    api.startup()


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def everything(path: str, request: Request):
    body = await request.body()
    status, ctype, data, extra = api.handle(request.method, "/" + path, dict(request.query_params),
                                            dict(request.headers), body)
    return Response(content=data, status_code=status, media_type=ctype.split(";")[0], headers=extra)
