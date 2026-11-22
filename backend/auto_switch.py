"""Automatic switching to another account or key (Phase 8C; D009 as changed on 2026-11-22,
DECISIONS.md D046).

Off by default. Only when the user ticked "Switch automatically" in an engine panel, and
only because the run's own account or key cannot be used:

- a Claude Code / Codex account that is signed out or was removed, found by the sign-in
  check before the run starts, so nothing was sent;
- an API key that was removed (found before sending) or that the provider refused
  (`key_problem`). The refused run has been sent, so it stays failed and is never
  retried; only the items that have not started move.

Never because of a usage limit. The run moves to the first account or key of the panel's
list, in the user's order, that works now: an account must pass the same sign-in check,
a key the free model-list check that "Test key" uses, and only keys the run's charge
confirmation named are considered. One pass through the list; when none works, the run
pauses (or fails) exactly as before. Every switch is recorded on the job, the batch and
the run (from, to, reason, time), and the one that worked becomes the panel's choice for
new runs (the user's choice, D046).
"""

import json

from sqlalchemy import select

from backend import cli_accounts, keystore
from backend.models import Batch, EngineJob, EngineSettings, PipelineRun
from backend.scene_store import now

REASONS = {
    "signed_out": "signed out",
    "account_removed": "account removed",
    "key_removed": "key removed",
    "key_refused": "key refused",
}


def account_candidates(settings, engine: str, kind: str | None, current: str) -> list[dict]:
    """The accounts a run may move to, in the panel's order (none when switching is off)."""
    chain = cli_accounts.fallback_of(settings, engine, cli_accounts.purpose_of(engine, kind))
    if not chain["on"]:
        return []
    found = (cli_accounts.find(settings, engine, i) for i in chain["order"] if i != current)
    return [a for a in found if a is not None]


def key_candidates(settings, engine: str, kind: str | None, values: dict) -> list[dict]:
    """The keys a paid run may move to: those its charge confirmation named, in that order,
    while the panel's switching is on."""
    chain = keystore.fallback_of(settings, engine, keystore.purpose_of(engine, kind))
    if not chain["on"]:
        return []
    current = keystore.recorded(json.dumps(values))[0]
    found = (
        keystore.find(settings, engine, i)
        for i in values.get("fallback_keys") or []
        if i != current
    )
    return [k for k in found if k is not None]


def _settings_of(item) -> dict:
    return json.loads(item.settings_json or "{}")


def _save(item, values: dict) -> None:
    item.settings_json = json.dumps(values)


def move(
    session,
    settings,
    engine: str,
    target: dict,
    old: dict,
    reason: str,
    job_id: str,
    batch_ids: list[str],
    include_job: bool,
) -> dict:
    """Move a run to `target` and record the switch. With `include_job` the job itself moves
    (it was stopped before sending); otherwise only the batches' items that have not started.
    Returns the record."""
    owner = keystore if engine in keystore.PURPOSES else cli_accounts
    entry = {
        "from": old["id"],
        "from_label": old["label"],
        "to": target["id"],
        "to_label": target["label"],
        "reason": reason,
        "at": now(),
        "job_id": job_id,
    }
    job = session.get(EngineJob, job_id)
    kind = job.kind if job is not None else None
    if include_job and job is not None:
        owner.move(job, target)
        _save(job, {**_settings_of(job), "switched": entry})
    for batch in session.scalars(select(Batch).where(Batch.id.in_(batch_ids))):
        owner.move(batch, target)
        values = _settings_of(batch)
        _save(batch, {**values, "switches": [*values.get("switches", []), entry]})
        batch.updated_at = now()
        for item in session.scalars(
            select(EngineJob).where(
                EngineJob.batch_id == batch.id, EngineJob.status == "not_started"
            )
        ):
            owner.move(item, target)
        run_id = values.get("pipeline_id")
        run = session.get(PipelineRun, run_id) if run_id else None
        if run is not None:
            from backend.pipeline import remember_account  # imports scenes, which imports jobs

            # Later batches of the run (Run everything's images) use it too.
            remember_account(run, engine, target["id"], settings, {batch.kind})
            outcome = json.loads(run.outcome_json or "{}")
            outcome["switches"] = [*outcome.get("switches", []), entry | {"kind": batch.kind}]
            run.outcome_json = json.dumps(outcome)
            run.updated_at = now()
    # The one that worked becomes the panel's choice (D046); a page showing the old choice
    # must reload before saving, so the engine settings revision moves on.
    purpose = owner.purpose_of(engine, kind)
    owner.promote(settings, engine, purpose, old["id"], target["id"])
    item = session.get(EngineSettings, 1)
    if item is not None:
        item.revision += 1
    return entry


def describe(entry: dict) -> str:
    return (
        f"Switched automatically from “{entry['from_label']}” to "
        f"“{entry['to_label']}” ({REASONS.get(entry['reason'], entry['reason'])})."
    )
