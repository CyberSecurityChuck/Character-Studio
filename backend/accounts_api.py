"""Studio settings for several Claude Code and Codex sign-ins (Phase 8A, D041, D042).

The user adds an account (a label and an empty profile folder), signs in with the
CLI's own sign-in in a console window, and chooses which account new runs use. Status
comes from the CLI's own status command; only "found / signed in / plan" is kept.
Removing an account asks first in the studio, then runs the CLI's own sign-out for that
folder and deletes the folder.
"""

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend import cli_accounts
from backend.cli_accounts import ACCOUNT_ENGINES, DEFAULT, AccountError
from backend.engines import ENGINE_NAMES, clean_environment, engine_status, resolve_command
from backend.models import EngineJob

router = APIRouter(prefix="/api")


class LabelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=200)


class ChooseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1, max_length=40)


def require_engine(engine: str) -> str:
    if engine not in ACCOUNT_ENGINES:
        raise HTTPException(404, "Accounts are only for Claude Code and Codex.")
    return engine


def _problem(error: AccountError) -> HTTPException:
    return HTTPException(409, str(error))


def waiting_on(session, engine: str, account_id: str) -> int:
    """Runs queued or in progress on this account (they keep it once queued)."""
    jobs = session.scalars(
        select(EngineJob.settings_json).where(
            EngineJob.engine == engine, EngineJob.status.in_(("not_started", "running"))
        )
    )
    return sum(1 for raw in jobs if cli_accounts.recorded(raw)[0] == account_id)


def account_status(request, engine: str, account_id: str) -> dict:
    overrides = request.app.state.settings.engine_commands
    try:
        env = cli_accounts.account_env(request.app.state.settings, engine, account_id)
    except AccountError:
        return {"installed": False, "signed_in": False, "plan": None, "message": "Removed."}
    status = engine_status(engine, overrides, env)
    if not status["signed_in"] and status["installed"]:
        status["message"] = "Signed out. Use Sign in to sign this account in."
    return {key: status[key] for key in ("installed", "version", "signed_in", "plan", "message")}


def engine_accounts(request, engine: str, with_status: bool = True) -> dict:
    settings = request.app.state.settings
    listed = cli_accounts.accounts(settings, engine)
    with Session(request.app.state.engine) as session:
        busy = {a["id"]: waiting_on(session, engine, a["id"]) for a in listed}
    statuses = {}
    if with_status:
        with ThreadPoolExecutor(max_workers=4) as pool:
            found = pool.map(lambda a: account_status(request, engine, a["id"]), listed)
            statuses = dict(zip((a["id"] for a in listed), found, strict=True))
    return {
        "engine": engine,
        "name": "Claude Code" if engine == "claude_cli" else ENGINE_NAMES[engine],
        "active": cli_accounts.active(settings, engine)["id"],
        "accounts": [
            {
                "id": a["id"],
                "label": a["label"],
                "default": a["default"],
                "created_at": a.get("created_at"),
                "waiting": busy[a["id"]],
                "status": statuses.get(a["id"]),
            }
            for a in listed
        ],
    }


@router.get("/cli-accounts")
async def list_accounts(request: Request, status: bool = True):
    """Every account per engine; `status=false` skips the sign-in checks (a quick list)."""

    def check():
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(
                pool.map(lambda e: engine_accounts(request, e, status), ACCOUNT_ENGINES)
            )

    return await run_in_threadpool(check)


@router.post("/cli-accounts/{engine}", status_code=201)
def add_account(request: Request, engine: str, body: LabelInput):
    require_engine(engine)
    try:
        account = cli_accounts.add(request.app.state.settings, engine, body.label)
    except AccountError as error:
        raise _problem(error) from error
    return {"account": account, **engine_accounts(request, engine, with_status=False)}


@router.put("/cli-accounts/{engine}/active")
def choose_account(request: Request, engine: str, body: ChooseInput):
    """Use this account for new runs. Runs already queued keep the account they have."""
    require_engine(engine)
    try:
        cli_accounts.choose(request.app.state.settings, engine, body.account_id)
    except AccountError as error:
        raise _problem(error) from error
    return engine_accounts(request, engine, with_status=False)


@router.put("/cli-accounts/{engine}/{account_id}")
def rename_account(request: Request, engine: str, account_id: str, body: LabelInput):
    require_engine(engine)
    try:
        cli_accounts.rename(request.app.state.settings, engine, account_id, body.label)
    except AccountError as error:
        raise _problem(error) from error
    return engine_accounts(request, engine, with_status=False)


@router.post("/cli-accounts/{engine}/{account_id}/sign-in", status_code=202)
def sign_in(request: Request, engine: str, account_id: str):
    """Open the CLI's own sign-in in a console window; the user completes it there."""
    require_engine(engine)
    settings = request.app.state.settings
    if cli_accounts.find(settings, engine, account_id) is None:
        raise HTTPException(404, "That account no longer exists. Reload the page.")
    command = resolve_command(engine, settings.engine_commands)
    if command is None:
        raise HTTPException(409, f"{ENGINE_NAMES[engine]} was not found on this PC.")
    try:
        env = clean_environment(cli_accounts.account_env(settings, engine, account_id))
        cli_accounts.open_sign_in(command, engine, env)
    except AccountError as error:
        raise _problem(error) from error
    except OSError as error:
        raise HTTPException(409, "The sign-in window could not be opened. Try again.") from error
    return {"opened": True}


@router.delete("/cli-accounts/{engine}/{account_id}")
def remove_account(request: Request, engine: str, account_id: str):
    """Sign the account out with the CLI's own sign-out, then delete its folder.

    The studio asks first (D042). Past jobs keep the account's name. Refused while runs
    are waiting or in progress on it, so nothing queued loses its account.
    """
    require_engine(engine)
    settings = request.app.state.settings
    if account_id == DEFAULT:
        raise HTTPException(409, "The Default account is your usual sign-in and cannot be removed.")
    account = cli_accounts.find(settings, engine, account_id)
    if account is None:
        raise HTTPException(404, "That account no longer exists. Reload the page.")
    with Session(request.app.state.engine) as session:
        busy = waiting_on(session, engine, account_id)
    if busy:
        runs = "1 run is" if busy == 1 else f"{busy} runs are"
        raise HTTPException(
            409,
            f"{runs} waiting or in progress on “{account['label']}”. Let them finish, cancel "
            "them or continue them with another account first.",
        )
    command = resolve_command(engine, settings.engine_commands)
    signed_out = False
    if command is not None:
        env = clean_environment(cli_accounts.account_env(settings, engine, account_id))
        signed_out = cli_accounts.sign_out(command, engine, env)
    try:
        cli_accounts.forget(settings, engine, account_id)
    except AccountError as error:
        raise _problem(error) from error
    return {"signed_out": signed_out, **engine_accounts(request, engine, with_status=False)}
