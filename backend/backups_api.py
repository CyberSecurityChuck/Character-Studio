"""Backups in Studio settings: create, list, check, download and delete (PLAN.md §22).

Restoring replaces the data folder, so it runs only while the studio is stopped
(`Restore-Studio.cmd`); the page explains how.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from backend.backup import NAME, BackupError, backups_dir, list_backups, verify_backup
from backend.backup_crypto import MAX_PASSWORD, check_password

router = APIRouter(prefix="/api")


class CreateInput(BaseModel):
    """Phase 6D: a password protects the backup; it is used once and never stored."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    # Checked in code (never by the validator), so an error can never echo the password.
    password: str | None = None


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    # Checked in code (never by the validator), so an error can never echo the password.
    password: str | None = None


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
async def create(request: Request, body: CreateInput | None = None):
    password = body.password if body else None
    if password is not None:
        try:
            check_password(password)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    if not request.app.state.backups.start(password):
        raise HTTPException(409, "A backup is already being made. Wait for it to finish.")
    return await run_in_threadpool(state, request)


@router.post("/backups/{name}/verify")
async def verify(request: Request, name: str, body: PasswordInput | None = None):
    path = require_backup(request, name)
    password = body.password if body else None
    if password is not None and len(password) > MAX_PASSWORD:
        raise HTTPException(422, "That password is too long.")
    try:
        return await run_in_threadpool(verify_backup, path, password)
    except BackupError as error:
        return {"ok": False, "problem": str(error)}


@router.get("/backups/{name}/download")
def download(request: Request, name: str):
    kind = "application/zip" if name.endswith(".zip") else "application/octet-stream"
    return FileResponse(require_backup(request, name), media_type=kind, filename=name)


@router.delete("/backups/{name}")
async def remove(request: Request, name: str):
    require_backup(request, name).unlink()
    return await run_in_threadpool(state, request)
