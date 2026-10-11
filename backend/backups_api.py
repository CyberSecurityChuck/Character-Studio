"""Backups in Studio settings: create, list, check, download and delete (PLAN.md §22).

Restoring replaces the data folder, so it runs only while the studio is stopped
(`Restore-Studio.cmd`); the page explains how.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from backend.backup import NAME, BackupError, backups_dir, list_backups, verify_backup

router = APIRouter(prefix="/api")


def state(request: Request) -> dict:
    runner = request.app.state.backups
    return {
        "running": runner.running,
        "error": runner.error,
        "last": runner.last,
        "folder": str(backups_dir(request.app.state.settings)),
        "items": list_backups(request.app.state.settings),
    }


def require_backup(request: Request, name: str):
    path = backups_dir(request.app.state.settings) / name
    if not NAME.match(name) or not path.is_file():
        raise HTTPException(404, "This backup no longer exists. Reload the list.")
    return path


@router.get("/backups")
async def backups(request: Request):
    return await run_in_threadpool(state, request)


@router.post("/backups", status_code=202)
async def create(request: Request):
    if not request.app.state.backups.start():
        raise HTTPException(409, "A backup is already being made. Wait for it to finish.")
    return await run_in_threadpool(state, request)


@router.post("/backups/{name}/verify")
async def verify(request: Request, name: str):
    path = require_backup(request, name)
    try:
        return await run_in_threadpool(verify_backup, path)
    except BackupError as error:
        return {"ok": False, "problem": str(error)}


@router.get("/backups/{name}/download")
def download(request: Request, name: str):
    return FileResponse(require_backup(request, name), media_type="application/zip", filename=name)


@router.delete("/backups/{name}")
async def remove(request: Request, name: str):
    require_backup(request, name).unlink()
    return await run_in_threadpool(state, request)
