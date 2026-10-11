"""Files inside generation and export packages, and copies of reference photos in them.

Every package records the approval it was made from, and the approval snapshot says
which reference photo became which `image-<n>.jpg`. That is enough to find each copy of
a photo later, so deleting a character or photo can offer to remove its copies too
(the user decides; nothing is removed automatically). Results and approvals are kept.
"""

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.configuration import Settings, asset_path
from backend.models import Approval, EngineJob, Scene
from backend.prompting import image_list
from backend.scene_store import now

PACKAGE_KINDS = ("generation", "export")
TEXT_FILES = ("prompt.txt", "negative_prompt.txt", "mapping.txt", "README.txt")
REMOVED_NOTE = (
    "\nSome reference photos were removed from this package on {date} because they were "
    "deleted from the Character Library. The numbers of the remaining images are unchanged.\n"
)


def mapping_text(inputs: dict, names: dict[str, str] | None) -> str:
    """Who is who. Names appear only in packages the user handles themselves."""
    lines = ["Character Studio · subject mapping", "", "- Image 1: the Base Image."]
    for mapping in inputs["mappings"]:
        subject = mapping["subject"]
        images = tuple(r["image"] for r in mapping["references"])
        if mapping["action"] == "replace":
            who = (
                f" ({names.get(mapping['character_id'], 'Deleted character')})"
                if names is not None
                else ""
            )
            lines.append(f"- {subject}{who}: identity only from {image_list(images)}.")
        elif mapping["action"] == "keep":
            lines.append(f"- {subject}: kept as they appear in Image 1.")
        else:
            lines.append(f"- {subject}: not assigned; kept as they appear in Image 1.")
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    # "\n" exactly as approved; no Windows newline translation.
    path.write_text(text, encoding="utf-8", newline="\n")


def write_zip(folder: Path) -> None:
    """(Re)build package.zip from the numbered images and text files still in the folder."""
    images = sorted(folder.glob("image-*.jpg"), key=lambda p: int(p.stem.split("-")[1]))
    partial = folder / "package.zip.partial"
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in [*images, *(folder / name for name in TEXT_FILES)]:
            if path.is_file():
                archive.write(path, path.name)
    partial.replace(folder / "package.zip")


@dataclass
class Copy:
    job_id: str
    kind: str
    scene_id: str
    folder: str
    path: str


def find_copies(
    session,
    settings: Settings,
    *,
    character_ids: set[str] = frozenset(),
    photo_ids: set[str] = frozenset(),
) -> list[Copy]:
    """Existing copies of these characters' or photos' reference photos in any package."""
    found = []
    jobs = session.scalars(
        select(EngineJob).where(
            EngineJob.kind.in_(PACKAGE_KINDS),
            EngineJob.job_folder.is_not(None),
            EngineJob.input_id.is_not(None),
        )
    )
    for job in jobs:
        approval = session.get(Approval, job.input_id)
        if approval is None:
            continue
        for mapping in json.loads(approval.snapshot_json)["inputs"]["mappings"]:
            for reference in mapping["references"]:
                if mapping["character_id"] in character_ids or reference["photo_id"] in photo_ids:
                    key = f"{job.job_folder}/image-{reference['image']}.jpg"
                    if asset_path(settings, key).is_file():
                        found.append(Copy(job.id, job.kind, job.scene_id, job.job_folder, key))
    return found


def copy_summary(session, copies: list[Copy]) -> dict:
    scenes = sorted({c.scene_id for c in copies})
    titles = [session.get(Scene, s).title for s in scenes if session.get(Scene, s)]
    return {
        "count": len(copies),
        "packages": len({c.job_id for c in copies}),
        "scenes": titles,
    }


def deletion_paths(copies: list[Copy]) -> list[str]:
    """Photo copies plus the zip of every affected export (rebuilt after the deletion)."""
    zips = {f"{c.folder}/package.zip" for c in copies if c.kind == "export"}
    return [c.path for c in copies] + sorted(zips)


def rebuild_exports(engine, settings: Settings, copies: list[Copy], deleted: set[str]) -> None:
    """After the copies are gone: note it in the README, drop deleted names, rebuild the zip."""
    stamp = now()[:10]
    with Session(engine) as session:
        for job_id in {c.job_id for c in copies if c.kind == "export"}:
            job = session.get(EngineJob, job_id)
            approval = session.get(Approval, job.input_id) if job else None
            if approval is None:
                continue
            folder = asset_path(settings, job.job_folder)
            if not folder.is_dir():
                continue
            snapshot = json.loads(approval.snapshot_json)
            names = {
                key: value
                for key, value in snapshot["display"].get("character_names", {}).items()
                if key not in deleted
            }
            write_text(folder / "mapping.txt", mapping_text(snapshot["inputs"], names))
            readme = folder / "README.txt"
            if readme.is_file():
                text = readme.read_text(encoding="utf-8")
                if "were removed from this package" not in text:
                    write_text(readme, text + REMOVED_NOTE.format(date=stamp))
            write_zip(folder)


def missing_images(settings: Settings, job: EngineJob, inputs: dict) -> int:
    """How many of a package's reference images were removed since it was made."""
    folder = asset_path(settings, job.job_folder)
    numbers = [r["image"] for m in inputs["mappings"] for r in m["references"]]
    return sum(1 for n in numbers if not (folder / f"image-{n}.jpg").is_file())
