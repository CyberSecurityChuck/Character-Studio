"""The studio's own prompt template. Engines never write the main prompt (PLAN.md Phase 3).

Images are labelled by number (Image 1 is always the Base Image) and people by
"Subject N", so later polishing and generation can refer to them reliably.
Character assignments arrive in Phase 4; until then every subject is unassigned.
"""

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


def _sentence(label: str, value: str) -> str:
    value = value.strip().rstrip(".")
    return f"{label}: {value}." if value else ""


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
    return [f"- {subject.label} ({subject.position.strip().rstrip('.')})."] + [
        f"  {part}" for part in parts if part
    ]


def build_prompt(analysis: SceneAnalysisData, scene_changes: str = "") -> tuple[str, str]:
    """Return (prompt, negative prompt) for a validated analysis."""
    camera = analysis.camera
    image = analysis.image_properties
    count = len(analysis.subjects)
    people = "no people" if count == 0 else "1 person" if count == 1 else f"{count} people"
    lines = [
        "ATTACHED IMAGES",
        "- Image 1: the BASE IMAGE (scene and composition reference).",
    ]
    if count:
        labels = ", ".join(subject.label for subject in analysis.subjects)
        verb = "keeps" if count == 1 else "keep"
        lines.append(
            f"- Identity references: not assigned yet. {labels} {verb} the appearance shown in "
            "Image 1 until characters are assigned."
        )
    lines += [
        "",
        "TASK",
        f"Create one new photorealistic image that recreates Image 1 ({people}) as faithfully as "
        "possible.",
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
