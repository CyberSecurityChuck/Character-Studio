"""Approving a whole scene set (Phase 7C-1, D030, D037).

The list of scenes that can be approved (it feeds the Approve step, the review queue and the
Approve all dialog) and Approve all itself. Every scene is approved on its own: it goes through
the same checks and gets its own immutable snapshot (mode "bulk") as an approval given in the
scene. Uncertain details, warnings and people-count mismatches are accepted only for the
categories the user ticked, and nothing here generates anything.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.models import PromptVersion, Scene, SceneAnalysis
from backend.preparation import accept_scene_details, set_scenes
from backend.scene_store import active_job, latest
from backend.scenes import approve_in_session, writing
from backend.workflow import (
    analysis_of,
    current_approval,
    mismatch_note,
    review,
    uncertain_blocker,
)

router = APIRouter(prefix="/api")


def approval_row(session, scene: Scene) -> dict:
    """Where one scene stands on the way to approval.

    state is "approved", "ready" (can be approved after the user's ticks) or "blocked" (with
    the reason). Uncertain details and warnings do not block: the user accepts them.
    """
    row = {
        "scene_id": scene.id,
        "title": scene.title,
        "thumbnail_url": f"/api/scenes/{scene.id}/image/thumbnail",
        "state": "blocked",
        "reason": None,
        "uncertain": 0,
        "warnings": [],
        "mismatch": None,
        "analysis_id": None,
        "prompt_id": None,
        "prompt_version": None,
    }
    if current_approval(session, scene.id) is not None:
        row["state"] = "approved"
        return row
    if active_job(session, scene.id):
        row["reason"] = "A run is running or waiting for it."
        return row
    analysis = latest(session, SceneAnalysis, scene.id)
    if analysis is None:
        row["reason"] = "It has not been analysed yet."
        return row
    result = review(session, scene)
    hard = [b for b in result.blockers if b != uncertain_blocker(result.uncertain)]
    if hard:
        row["reason"] = hard[0]
        return row
    prompt = latest(session, PromptVersion, scene.id)
    row.update(
        state="ready",
        uncertain=result.uncertain,
        warnings=result.warnings,
        mismatch=mismatch_note(scene, analysis_of(analysis)),
        analysis_id=analysis.id,
        prompt_id=prompt.id,
        prompt_version=prompt.version,
    )
    return row


@router.get("/scene-sets/{scene_set_id}/approval")
def approval_list(request: Request, scene_set_id: str):
    """Every scene of the set with its approval state, plus the counts the Approve step shows."""
    with Session(request.app.state.engine) as session:
        rows = [approval_row(session, scene) for scene in set_scenes(session, scene_set_id)]
    ready = [r for r in rows if r["state"] == "ready"]
    return {
        "rows": rows,
        "counts": {
            "total": len(rows),
            "approved": sum(r["state"] == "approved" for r in rows),
            "blocked": sum(r["state"] == "blocked" for r in rows),
            "ready": len(ready),
            "clean": sum(not (r["uncertain"] or r["warnings"] or r["mismatch"]) for r in ready),
            "uncertain": sum(bool(r["uncertain"]) for r in ready),
            "warnings": sum(bool(r["warnings"]) for r in ready),
            "mismatched": sum(bool(r["mismatch"]) for r in ready),
        },
    }


class ApproveItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(max_length=32)
    # What the user saw in the dialog; a scene that changed since is skipped, not approved.
    prompt_id: str = Field(max_length=32)
    analysis_id: str = Field(max_length=32)


class ApproveAllInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ApproveItem] = Field(min_length=1, max_length=500)
    accept_uncertain: bool = False
    accept_warnings: bool = False
    # "Extra people may keep their original look": scenes labelled as a people/character mismatch.
    allow_mismatch: bool = False


def approve_one(request: Request, scene_set_id: str, item: ApproveItem, body: ApproveAllInput):
    """Approve one scene in its own transaction; any refusal undoes everything done to it."""
    with writing(request) as session:
        scene = session.get(Scene, item.scene_id)
        if scene is None or scene.scene_set_id != scene_set_id:
            raise HTTPException(404, "This scene is no longer in the set.")
        row = approval_row(session, scene)
        if row["state"] == "approved":
            raise HTTPException(409, "It is already approved.")
        if row["state"] == "blocked":
            raise HTTPException(409, row["reason"])
        if row["analysis_id"] != item.analysis_id or row["prompt_id"] != item.prompt_id:
            raise HTTPException(409, "It changed since the list was made. Reload and look again.")
        if row["mismatch"] and not body.allow_mismatch:
            raise HTTPException(
                409,
                f"{row['mismatch']}. Left out because “extra people may keep their original "
                "look” is not ticked.",
            )
        if row["warnings"] and not body.accept_warnings:
            raise HTTPException(
                409, "It has warnings. Left out because “accept warnings” is not ticked."
            )
        prompt_id = item.prompt_id
        if row["uncertain"]:
            if not body.accept_uncertain:
                raise HTTPException(
                    409,
                    f"{row['uncertain']} uncertain "
                    f"{'detail' if row['uncertain'] == 1 else 'details'}. Left out because "
                    "“accept uncertain details” is not ticked.",
                )
            accept_scene_details(session, scene, item.analysis_id, keep_prompt=True)
            prompt_id = latest(session, PromptVersion, scene.id).id
        # Warnings are decided on what is left after the details were accepted.
        accepted = bool(row["warnings"]) and body.accept_warnings
        approve_in_session(
            request.app.state.settings, session, scene, prompt_id, accepted, mode="bulk"
        )
        return scene.title


@router.post("/scene-sets/{scene_set_id}/approve-all")
def approve_all(request: Request, scene_set_id: str, body: ApproveAllInput):
    """Approve the listed scenes of the set, each with its own snapshot (mode "bulk")."""
    with Session(request.app.state.engine) as session:
        set_scenes(session, scene_set_id)
    done, skipped = [], []
    for item in body.items:
        try:
            title = approve_one(request, scene_set_id, item, body)
            done.append({"scene_id": item.scene_id, "title": title})
        except HTTPException as error:
            with Session(request.app.state.engine) as session:
                scene = session.get(Scene, item.scene_id)
                title = scene.title if scene else "A scene"
            skipped.append({"scene_id": item.scene_id, "title": title, "reason": error.detail})
    return {"done": done, "skipped": skipped}
