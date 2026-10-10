"""The studio's own prompt template. Engines never write the main prompt (PLAN.md Phase 3).

Images are labelled by number (Image 1 is always the Base Image, then each subject's
reference photos in subject order) and people by "Subject N", so polishing and
generation can refer to them reliably. Character names never enter the prompt.
"""

import json
import re
from dataclasses import dataclass

from backend.analysis_schema import SceneAnalysisData

IDENTITY_LOCK = (
    "Use each subject's identity reference photographs solely to establish that person's "
    "identity: recognizable face, facial structure and proportions, distinctive facial features, "
    "natural skin tone and hair. Do not copy their original poses, camera angles, expressions, "
    "clothing, lighting or backgrounds."
)

COMPOSITION_LOCK = (
    "Reproduce Image 1's visual composition as faithfully as possible. Preserve the pose, viewing "
    "angle, body orientation, head rotation, gaze, framing, outfit, environment and lighting."
)

NEGATIVE = (
    "Do not change the pose, camera angle, framing, crop or outfit. Do not add, remove or merge "
    "people. Do not blend identities between subjects. Do not copy poses, expressions, clothing, "
    "lighting or backgrounds from identity reference photographs. No text, captions, logos or "
    "watermarks. No extra or missing limbs or fingers, distorted hands or warped faces."
)


@dataclass(frozen=True)
class Assignment:
    """One subject's role in the prompt: replace (with these image numbers), keep or unresolved."""

    label: str
    action: str
    images: tuple[int, ...] = ()


def _sentence(label: str, value: str) -> str:
    value = value.strip().rstrip(".")
    return f"{label}: {value}." if value else ""


def image_list(images: tuple[int, ...]) -> str:
    names = [f"Image {number}" for number in images]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def subject_lines(subject) -> list[str]:
    parts = [
        _sentence("Pose", subject.pose_summary),
        _sentence("Body direction", subject.body_direction),
        _sentence("Torso", subject.torso_orientation),
        _sentence("Shoulders", subject.shoulder_alignment),
        _sentence("Head direction", subject.head_direction),
        _sentence("Face angle to camera", subject.facial_viewing_angle),
        _sentence("Eyes and gaze", subject.eye_direction),
        _sentence("Expression", subject.expression),
        _sentence("Arms and hands", subject.arms_and_hands),
        _sentence("Legs and feet", subject.legs_and_feet),
        _sentence("Outfit", subject.outfit),
        _sentence("Hairstyle", subject.hairstyle),
        _sentence("Accessories", subject.accessories),
    ]
    position = subject.position.strip().rstrip(".")
    head = f"- {subject.label} ({position})." if position else f"- {subject.label}."
    return [head] + [f"  {part}" for part in parts if part]


def _attachment_lines(analysis: SceneAnalysisData, roles: dict[str, Assignment]) -> list[str]:
    lines = ["- Image 1: the BASE IMAGE (scene and composition reference)."]
    unassigned = []
    for subject in analysis.subjects:
        role = roles[subject.label]
        if role.action == "replace" and role.images:
            noun = "identity reference" if len(role.images) == 1 else "identity references"
            lines.append(f"- {image_list(role.images)}: {noun} for {subject.label} (one person).")
        else:
            unassigned.append(subject.label)
    if unassigned and len(unassigned) == len(analysis.subjects):
        verb = "keeps" if len(unassigned) == 1 else "keep"
        lines.append(
            f"- Identity references: not assigned yet. {', '.join(unassigned)} {verb} the "
            "appearance shown in Image 1 until characters are assigned."
        )
    elif unassigned:
        has, keep = ("has", "keeps") if len(unassigned) == 1 else ("have", "keep")
        lines.append(
            f"- {', '.join(unassigned)} {has} no identity reference and {keep} the appearance "
            "shown in Image 1."
        )
    return lines


def _assignment_lines(analysis: SceneAnalysisData, roles: dict[str, Assignment]) -> list[str]:
    lines = []
    for subject in analysis.subjects:
        role = roles[subject.label]
        if role.action == "replace" and role.images:
            lines.append(
                f"- {subject.label}: take this person's identity only from "
                f"{image_list(role.images)}."
            )
        elif role.action == "keep":
            lines.append(
                f"- {subject.label}: keep original. Keep this person exactly as they appear in "
                "Image 1, with their face and identity unchanged."
            )
        else:
            lines.append(
                f"- {subject.label}: not assigned yet. Keep this person as they appear in Image 1."
            )
    if len(analysis.subjects) > 1:
        lines.append("Keep every identity separate. Never blend features between subjects.")
    return lines


def build_prompt(
    analysis: SceneAnalysisData,
    scene_changes: str = "",
    assignments: list[Assignment] | None = None,
) -> tuple[str, str]:
    """Return (prompt, negative prompt) for a validated analysis and its assignments."""
    roles = {a.label: a for a in assignments or []}
    for subject in analysis.subjects:
        roles.setdefault(subject.label, Assignment(subject.label, "unresolved"))
    camera = analysis.camera
    image = analysis.image_properties
    count = len(analysis.subjects)
    people = "no people" if count == 0 else "1 person" if count == 1 else f"{count} people"
    lines = ["ATTACHED IMAGES", *_attachment_lines(analysis, roles)]
    lines += [
        "",
        "TASK",
        f"Create one new photorealistic image that recreates Image 1 ({people}) as faithfully as "
        "possible.",
    ]
    if count and any(role.action != "unresolved" for role in roles.values()):
        lines += ["", "IDENTITY ASSIGNMENTS", *_assignment_lines(analysis, roles)]
    lines += [
        "",
        "IDENTITY LOCK",
        IDENTITY_LOCK,
        "",
        "COMPOSITION LOCK (from Image 1)",
        COMPOSITION_LOCK,
        f"- Frame: {image.orientation}, about {image.approximate_aspect_ratio}; "
        f"{camera.framing.strip().rstrip('.')}.",
        f"- Camera: {camera.height.strip().rstrip('.')}; {camera.direction.strip().rstrip('.')}; "
        f"{camera.shot_type.strip().rstrip('.')}; {camera.perspective.strip().rstrip('.')}.",
        f"- Style: {image.style.strip().rstrip('.')}.",
        f"- Scene: {analysis.scene_description.strip().rstrip('.')}.",
    ]
    for subject in analysis.subjects:
        lines += subject_lines(subject)
    lines += [
        f"- Environment: {analysis.environment.strip().rstrip('.')}.",
        f"- Lighting and shadows: {analysis.lighting.strip().rstrip('.')}.",
        f"- Colour palette: {analysis.color_palette.strip().rstrip('.')}.",
        f"- Atmosphere: {analysis.atmosphere.strip().rstrip('.')}.",
    ]
    if analysis.composition_constraints:
        lines += ["", "MUST PRESERVE"]
        lines += [f"- {item.strip()}" for item in analysis.composition_constraints]
    if analysis.uncertainties:
        lines += ["", "UNCERTAIN DETAILS (keep these exactly as they appear in Image 1)"]
        lines += [f"- {item.field}: {item.note.strip()}" for item in analysis.uncertainties]
    if scene_changes.strip():
        lines += ["", "REQUESTED CHANGES (these override Image 1 where they conflict)"]
        lines += [scene_changes.strip()]
    return "\n".join(lines), NEGATIVE


def _has(pattern: str, text: str) -> bool:
    # "Subject 1" must not match "Subject 12"; "Image 2" must not match "Image 20".
    return re.search(rf"\b{re.escape(pattern)}\b(?!\d)", text, re.IGNORECASE) is not None


def check_prompt(text: str, assignments: list[Assignment], total_images: int) -> list[str]:
    """Required elements missing from a prompt (PLAN.md Phase 4). Empty means all present.

    Each replaced subject needs one sentence that names it together with each of its
    image numbers; each kept subject needs one that names it with "keep" or "unchanged".
    """
    missing = []
    if not _has("Image 1", text):
        missing.append("Image 1 (the Base Image) is not mentioned.")
    sentences = [s for s in re.split(r"(?<=[.;!?])\s+|\n", text) if s.strip()]
    for role in assignments:
        if role.action == "replace" and role.images:
            if not any(
                _has(role.label, s) and all(_has(f"Image {n}", s) for n in role.images)
                for s in sentences
            ):
                missing.append(
                    f"{role.label} is not linked to {image_list(role.images)} in one sentence."
                )
        elif role.action == "keep":
            if not any(
                _has(role.label, s) and re.search(r"\b(keep|kept|unchanged)\b", s, re.I)
                for s in sentences
            ):
                missing.append(f"The instruction to keep {role.label} original is missing.")
    for number in sorted({int(n) for n in re.findall(r"\bImages? (\d+)\b", text)}):
        if number > total_images or number < 1:
            missing.append(
                f"Image {number} is mentioned, but only {total_images} "
                f"{'image is' if total_images == 1 else 'images are'} attached."
            )
    return missing


# "Polish prompt" (PLAN.md Phase 4): Claude only, text only, no tools.
POLISH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["prompt"],
    "properties": {"prompt": {"type": "string"}},
}
POLISH_RULES = """You are the prompt-polishing step of a local image studio. Rewrite the image \
generation PROMPT below so it reads clearly and flows well for an image model.

Fixed rules:
- Keep every fact in the prompt. Add nothing new: no new details, objects, people, styles or \
assumptions.
- Keep every "Subject N" label exactly as written.
- Keep every image number exactly as written ("Image 1", "Image 2", ...) and keep each \
subject linked to the same image numbers in one sentence.
- Keep every identity instruction, the identity lock and the composition lock.
- Keep every instruction to keep a subject original or unchanged.
- Keep any requested changes.
- The SCENE ANALYSIS is for checking facts only. Do not add details from it that the prompt \
leaves out.
- Return only the polished prompt text, in the "prompt" field. No commentary."""


def polish_instruction(prompt_text: str, analysis: SceneAnalysisData) -> str:
    analysis_json = json.dumps(analysis.model_dump(), separators=(",", ":"), ensure_ascii=False)
    return (
        f"{POLISH_RULES}\n\nBEGIN PROMPT\n{prompt_text.strip()}\nEND PROMPT\n\n"
        f"BEGIN SCENE ANALYSIS\n{analysis_json}\nEND SCENE ANALYSIS"
    )
