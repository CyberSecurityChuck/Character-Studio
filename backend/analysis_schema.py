"""The one scene-analysis format, shared by both CLI engines and the manual import.

The JSON Schema below is the one verified with `claude --json-schema` and
`codex exec --output-schema` in Phase 2.5. The Pydantic models enforce the same
shape (plus size limits) on every result, whichever engine produced it.
"""

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SCHEMA_VERSION = 1
Text = Annotated[str, Field(max_length=4000)]
Short = Annotated[str, Field(max_length=400)]


def _text(properties):
    return {name: {"type": "string"} for name in properties}


SUBJECT_FIELDS = (
    "position",
    "body_direction",
    "torso_orientation",
    "shoulder_alignment",
    "head_direction",
    "facial_viewing_angle",
    "eye_direction",
    "expression",
    "arms_and_hands",
    "legs_and_feet",
    "pose_summary",
    "outfit",
    "hairstyle",
    "accessories",
)
CAMERA_FIELDS = ("height", "direction", "shot_type", "framing", "perspective")
SCENE_TEXT_FIELDS = ("environment", "lighting", "color_palette", "atmosphere")

JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "image_properties",
        "scene_description",
        "camera",
        "subjects",
        *SCENE_TEXT_FIELDS,
        "composition_constraints",
        "uncertainties",
    ],
    "properties": {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "image_properties": {
            "type": "object",
            "additionalProperties": False,
            "required": ["orientation", "approximate_aspect_ratio", "style"],
            "properties": {
                "orientation": {"type": "string", "enum": ["portrait", "landscape", "square"]},
                "approximate_aspect_ratio": {"type": "string"},
                "style": {"type": "string"},
            },
        },
        "scene_description": {"type": "string"},
        "camera": {
            "type": "object",
            "additionalProperties": False,
            "required": list(CAMERA_FIELDS),
            "properties": _text(CAMERA_FIELDS),
        },
        "subjects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "bounding_box", *SUBJECT_FIELDS],
                "properties": {
                    "label": {"type": "string", "pattern": "^Subject [0-9]+$"},
                    "bounding_box": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["x", "y", "width", "height"],
                        "properties": {
                            key: {"type": "number", "minimum": 0, "maximum": 1}
                            for key in ("x", "y", "width", "height")
                        },
                    },
                    **_text(SUBJECT_FIELDS),
                },
            },
        },
        **_text(SCENE_TEXT_FIELDS),
        "composition_constraints": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["field", "note"],
                "properties": {"field": {"type": "string"}, "note": {"type": "string"}},
            },
        },
    },
}

_RULES = """Describe only what is visible. Do not identify or name any person. Label people \
"Subject 1", "Subject 2", ... from left to right.

For each subject, explicitly distinguish camera direction, body direction, head direction and \
eye direction. Describe pose, arms, hands, legs, feet, expression, outfit, hairstyle and \
accessories precisely enough to recreate the pose.

Give each subject an approximate bounding box as fractions of the image (x, y = top-left corner; \
width, height), each between 0 and 1.

Also describe the camera (height, direction, shot type, framing, perspective), environment, \
lighting and shadows, colour palette and atmosphere, and list composition constraints that a \
recreation must preserve.

If anything is ambiguous or hidden (for example eyes behind sunglasses), do not guess: write your \
best cautious description and add an entry to "uncertainties" naming the field and why."""

# Engine runs: the CLI reads base.jpg from its job folder and enforces the schema itself.
ENGINE_INSTRUCTION = f"""You are the scene-analysis step of a local image studio. Read the file \
base.jpg in the current folder and analyse it.

{_RULES}

Return only the JSON object matching the provided schema, with schema_version {SCHEMA_VERSION}. \
No other text."""

# Manual fallback: the user attaches the Base Image in another app and pastes the reply back.
MANUAL_INSTRUCTION = f"""You are the scene-analysis step of a local image studio. Analyse the \
attached image (the Base Image).

{_RULES}

Reply with only one JSON object, with schema_version {SCHEMA_VERSION}, that matches this JSON \
Schema exactly (no extra fields, no commentary, no Markdown):

{json.dumps(JSON_SCHEMA, indent=2)}"""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImageProperties(_Strict):
    orientation: Literal["portrait", "landscape", "square"]
    approximate_aspect_ratio: Short
    style: Text


class Camera(_Strict):
    height: Text
    direction: Text
    shot_type: Text
    framing: Text
    perspective: Text


class BoundingBox(_Strict):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(ge=0, le=1, allow_inf_nan=False)
    height: float = Field(ge=0, le=1, allow_inf_nan=False)


class Subject(_Strict):
    label: str = Field(pattern=r"^Subject [0-9]+$", max_length=20)
    bounding_box: BoundingBox
    position: Text
    body_direction: Text
    torso_orientation: Text
    shoulder_alignment: Text
    head_direction: Text
    facial_viewing_angle: Text
    eye_direction: Text
    expression: Text
    arms_and_hands: Text
    legs_and_feet: Text
    pose_summary: Text
    outfit: Text
    hairstyle: Text
    accessories: Text


class Uncertainty(_Strict):
    field: Short
    note: Text


class SceneAnalysisData(_Strict):
    schema_version: Literal[1]
    image_properties: ImageProperties
    scene_description: Text
    camera: Camera
    subjects: list[Subject] = Field(max_length=20)
    environment: Text
    lighting: Text
    color_palette: Text
    atmosphere: Text
    composition_constraints: list[Text] = Field(max_length=50)
    uncertainties: list[Uncertainty] = Field(max_length=50)

    @field_validator("subjects")
    @classmethod
    def unique_labels(cls, subjects):
        labels = [subject.label for subject in subjects]
        if len(labels) != len(set(labels)):
            raise ValueError("Each subject needs its own label (Subject 1, Subject 2, ...).")
        return subjects


class AnalysisFormatError(ValueError):
    """The analysis does not match the studio format; the message is safe to show."""


def _describe(error: ValidationError) -> str:
    problems = []
    for item in error.errors()[:5]:
        location = ".".join(str(part) for part in item["loc"]) or "analysis"
        problems.append(f"{location}: {item['msg']}")
    more = len(error.errors()) - len(problems)
    return "; ".join(problems) + (f" (and {more} more)" if more > 0 else "")


def validate_analysis(value: object) -> SceneAnalysisData:
    try:
        return SceneAnalysisData.model_validate(value)
    except ValidationError as error:
        raise AnalysisFormatError(
            f"The analysis does not match the studio format. {_describe(error)}"
        ) from error


def parse_analysis_text(raw: str) -> SceneAnalysisData:
    """Accept pasted replies that wrap the JSON in a Markdown fence or a short sentence."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text and "}" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise AnalysisFormatError(
            "The analysis is not valid JSON. Paste the whole reply, starting with { and "
            "ending with }."
        ) from error
    return validate_analysis(value)
