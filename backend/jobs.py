"""One job runner for every engine run (PLAN.md §12.1, DECISIONS.md D010).

Jobs are persisted before anything starts and run one at a time, oldest first.
Each click queues a single analysis, polish or generation run, but several jobs may wait as
not_started. Nothing is ever retried or resumed automatically: after a restart,
runs that were in progress become Interrupted and waiting ones become Cancelled.
"""

import json
import threading
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.analysis_schema import ENGINE_INSTRUCTION, JSON_SCHEMA
from backend.configuration import Settings, asset_path
from backend.engines import (
    ENGINE_NAMES,
    EngineError,
    analysis_command,
    interpret_analysis,
    interpret_polish,
    polish_command,
    require_ready,
    resolve_command,
    run_process,
)
from backend.generation import (
    PackageError,
    generation_command,
    interpret_generation,
    prepare_generation_folder,
    read_run,
    snapshot_of,
    store_codex_images,
)
from backend.models import EngineJob, PromptVersion, Scene, SceneAnalysis
from backend.persistence import writing_session
from backend.prompting import POLISH_SCHEMA, polish_instruction
from backend.scene_store import latest, now
from backend.workflow import add_analysis, analysis_of, check_approval, refresh_workflow

MAX_PROMPT_LENGTH = 40_000

INTERRUPTED_MESSAGE = (
    "The studio stopped while this run was in progress. It may already have used some of your "
    "plan's allowance or saved output, so check its job folder before trying again."
)
NOT_STARTED_MESSAGE = "The studio stopped before this run started. Nothing was sent."


def reconcile_on_startup(engine) -> None:
    with writing_session(engine) as session:
        session.execute(
            update(EngineJob)
            .where(EngineJob.status == "running")
            .values(
                status="interrupted",
                error_kind="interrupted",
                error_details=INTERRUPTED_MESSAGE,
                finished_at=now(),
            )
        )
        session.execute(
            update(EngineJob)
            .where(EngineJob.status == "not_started")
            .values(
                status="cancelled",
                error_kind="not_started",
                error_details=NOT_STARTED_MESSAGE,
                finished_at=now(),
            )
        )
        for scene in session.scalars(select(Scene)):
            refresh_workflow(session, scene)


def _new_folder(settings: Settings, scene_id: str, kind: str) -> tuple[str, Path]:
    root = asset_path(settings, f"jobs/{scene_id}")
    root.mkdir(parents=True, exist_ok=True)
    number = 1
    while (root / f"{kind}-{number}").exists():
        number += 1
    folder = root / f"{kind}-{number}"
    folder.mkdir()
    return f"jobs/{scene_id}/{kind}-{number}", folder


def prepare_analysis_folder(settings: Settings, scene: Scene) -> str:
    """Create the job folder with a metadata-free copy of the Base Image (PLAN.md §22)."""
    key, folder = _new_folder(settings, scene.id, "analysis")
    with Image.open(asset_path(settings, scene.original_path)) as source:
        upright = ImageOps.exif_transpose(source).convert("RGB")
        # A fresh image carries no EXIF/GPS or other source metadata.
        clean = Image.new("RGB", upright.size)
        clean.paste(upright)
        clean.save(folder / "base.jpg", "JPEG", quality=95)
    (folder / "instruction.txt").write_text(ENGINE_INSTRUCTION, encoding="utf-8")
    (folder / "schema.json").write_text(json.dumps(JSON_SCHEMA, indent=2), encoding="utf-8")
    return key


def prepare_polish_folder(settings: Settings, scene_id: str, instruction: str) -> str:
    """Polish runs need no images: the folder only records what was sent."""
    key, folder = _new_folder(settings, scene_id, "polish")
    (folder / "instruction.txt").write_text(instruction, encoding="utf-8")
    return key


def polish_input(session, job: EngineJob) -> str:
    """The instruction for a polish run: fixed rules, the prompt version and its analysis."""
    prompt = session.get(PromptVersion, job.input_id)
    analysis = session.get(SceneAnalysis, prompt.analysis_id) if prompt.analysis_id else None
    analysis = analysis or latest(session, SceneAnalysis, job.scene_id)
    return polish_instruction(prompt.prompt_text, analysis_of(analysis))


class JobRunner:
    def __init__(self, engine, settings: Settings):
        self.engine = engine
        self.settings = settings
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, name="engine-jobs", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=30)

    def cancel(self, job_id: str) -> None:
        """Mark a job for cancellation; a running process is stopped within a moment."""
        with self._lock:
            self._cancelled.add(job_id)
        with writing_session(self.engine) as session:
            job = session.get(EngineJob, job_id)
            if job is not None and job.status == "not_started":
                self._finish(session, job, "cancelled", "cancelled", "Cancelled before it started.")

    def _cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled or self._stop.is_set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            job_id = self._claim_next()
            if job_id is None:
                self._wake.wait(timeout=1)
                self._wake.clear()
                continue
            self._execute(job_id)

    def _claim_next(self) -> str | None:
        with writing_session(self.engine) as session:
            job = session.scalar(
                select(EngineJob)
                .where(EngineJob.status == "not_started")
                .order_by(EngineJob.created_at, EngineJob.id)
                .limit(1)
            )
            if job is None:
                return None
            job.status = "running"
            job.started_at = now()
            return job.id

    def _finish(self, session, job, status, kind=None, details=None) -> None:
        job.status = status
        job.error_kind = kind
        job.error_details = details
        job.finished_at = now()
        session.flush()
        scene = session.get(Scene, job.scene_id)
        if scene is not None:
            refresh_workflow(session, scene)

    def _update(self, job_id: str, **values) -> None:
        with writing_session(self.engine) as session:
            session.execute(update(EngineJob).where(EngineJob.id == job_id).values(**values))

    def _execute(self, job_id: str) -> None:
        overrides = self.settings.engine_commands
        with Session(self.engine) as session:
            job = session.get(EngineJob, job_id)
            scene = session.get(Scene, job.scene_id)
            engine, timeout, kind = job.engine, job.timeout_seconds, job.kind
            instruction = polish_input(session, job) if kind == "polish" else None
            session.expunge_all()
        try:
            version = require_ready(engine, overrides)
            self._update(job_id, engine_version=version)
            if self._cancel_requested(job_id):
                raise _Stopped()
            if kind == "generation":
                self._run_generation(job_id, timeout)
                return
            if kind == "polish":
                folder = prepare_polish_folder(self.settings, scene.id, instruction)
            else:
                folder = prepare_analysis_folder(self.settings, scene)
            self._update(job_id, job_folder=folder)
            job_dir = asset_path(self.settings, folder)
            command = resolve_command(engine, overrides)
            if command is None:
                raise EngineError("not_installed", f"{ENGINE_NAMES[engine]} could not be started.")
            if kind == "polish":
                schema = json.dumps(POLISH_SCHEMA, separators=(",", ":"))
                argv, output_name = polish_command(command, instruction, schema), "output.json"
            else:
                argv, output_name = analysis_command(
                    engine, command, job_dir, json.dumps(JSON_SCHEMA, separators=(",", ":"))
                )
            outcome = run_process(
                argv,
                job_dir,
                job_dir / output_name,
                timeout,
                should_stop=lambda: self._cancel_requested(job_id),
            )
            if outcome.cancelled:
                raise _Stopped()
            if kind == "polish":
                polished = interpret_polish(job_dir, outcome, MAX_PROMPT_LENGTH)
                with writing_session(self.engine) as session:
                    job = session.get(EngineJob, job_id)
                    # Only a candidate: the prompt changes when the user chooses "Use polished".
                    job.output_text = polished
                    self._finish(session, job, "completed")
                return
            data = interpret_analysis(engine, job_dir, outcome)
            with writing_session(self.engine) as session:
                job = session.get(EngineJob, job_id)
                scene = session.get(Scene, job.scene_id)
                analysis = add_analysis(
                    session,
                    scene,
                    data,
                    engine,
                    engine_version=version,
                    raw_output_path=f"{folder}/{output_name}",
                    job_id=job_id,
                )
                job.result_id = analysis.id
                self._finish(session, job, "completed")
        except _Stopped:
            with writing_session(self.engine) as session:
                job = session.get(EngineJob, job_id)
                if self._stop.is_set():
                    self._finish(session, job, "interrupted", "interrupted", INTERRUPTED_MESSAGE)
                else:
                    self._finish(session, job, "cancelled", "cancelled", "You cancelled this run.")
        except EngineError as error:
            with writing_session(self.engine) as session:
                job = session.get(EngineJob, job_id)
                self._finish(session, job, "failed", error.kind, error.message)
        except Exception:
            # Never record internals or private paths; the job folder keeps the CLI's output.
            with writing_session(self.engine) as session:
                self._finish(
                    session,
                    session.get(EngineJob, job_id),
                    "failed",
                    "engine_error",
                    "The run could not be completed because of an unexpected problem in the "
                    "studio. Check the job folder, then try again or do it manually.",
                )
        finally:
            with self._lock:
                self._cancelled.discard(job_id)

    def _run_generation(self, job_id: str, timeout: int) -> None:
        """One Codex image run from the approval recorded with the job (PLAN.md Phase 5)."""
        with Session(self.engine) as session:
            job = session.get(EngineJob, job_id)
            scene = session.get(Scene, job.scene_id)
            approval, reason = check_approval(session, scene)
            # Inputs may have changed while the run was waiting; never send unapproved inputs.
            if approval is None or reason or approval.id != job.input_id:
                raise EngineError(
                    "approval_ended",
                    "The approval ended before this run started, so nothing was sent. Review "
                    "and approve the scene again, then generate.",
                )
            mode = json.loads(job.settings_json or "{}").get("mode", "generate")
            try:
                folder, images, instruction = prepare_generation_folder(
                    self.settings, session, scene.id, snapshot_of(approval)["inputs"], mode
                )
            except PackageError as error:
                raise EngineError("missing_file", f"{error} Nothing was sent.") from error
        self._update(job_id, job_folder=folder)
        job_dir = asset_path(self.settings, folder)
        command = resolve_command("codex_cli", self.settings.engine_commands)
        if command is None:
            raise EngineError("not_installed", "Codex could not be started.")
        outcome = run_process(
            generation_command(command, job_dir, images, instruction),
            job_dir,
            job_dir / "events.jsonl",
            timeout,
            should_stop=lambda: self._cancel_requested(job_id),
        )
        # Keep Codex's thread id whatever happened, so a saved image can be found later.
        thread_id = read_run(job_dir).thread_id
        if thread_id:
            self._update(job_id, provider_request_id=thread_id)
        if outcome.cancelled:
            raise _Stopped()
        _output, found = interpret_generation(job_dir, outcome)
        with Session(self.engine) as session:
            job = session.get(EngineJob, job_id)
            session.expunge(job)
        stored = store_codex_images(self.engine, self.settings, job, found)
        with writing_session(self.engine) as session:
            job = session.get(EngineJob, job_id)
            job.result_id = stored[0]
            self._finish(session, job, "completed")


class _Stopped(Exception):
    pass


def job_folder_path(settings: Settings, job: EngineJob) -> str | None:
    return str(asset_path(settings, job.job_folder)) if job.job_folder else None
