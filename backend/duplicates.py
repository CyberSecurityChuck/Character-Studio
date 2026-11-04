"""Free, local duplicate checks for Base Images (Phase 7A, D031).

Exact copies share the SHA-256 content hash already stored on every scene. Near copies
(re-saved, resized, recompressed or another format) are found with a 64-bit difference
hash: the upright image in greyscale at 9x8, one bit per neighbouring pixel pair. Heavy
crops and mirrored copies are usually not caught.
"""

import io
from pathlib import Path

from PIL import Image, ImageOps

# Two fingerprints at most this many bits apart are near copies (user's choice, D031).
NEAR_COPY_BITS = 6


def fingerprint(source: bytes | Path) -> str:
    """The difference hash of an already validated image, as 16 hex digits."""
    with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as image:
        # A JPEG can be decoded at reduced size; the hash only needs 9x8 pixels.
        image.draft("L", (160, 160))
        small = ImageOps.exif_transpose(image).convert("L").resize((9, 8), Image.Resampling.BOX)
    pixels = small.tobytes()
    bits = 0
    for row in range(8):
        for column in range(8):
            left, right = pixels[row * 9 + column], pixels[row * 9 + column + 1]
            bits = bits << 1 | (left > right)
    return f"{bits:016x}"


def distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


class Families:
    """Scenes linked by Duplicate scene count as one family and never as each other's copies."""

    def __init__(self, links: dict[str, str | None]):
        self.parent = {scene: scene for scene in links}
        for scene, source in links.items():
            if source in self.parent:
                self.join(scene, source)

    def find(self, scene: str) -> str:
        while self.parent[scene] != scene:
            self.parent[scene] = self.parent[self.parent[scene]]
            scene = self.parent[scene]
        return scene

    def join(self, first: str, second: str) -> None:
        self.parent[self.find(first)] = self.find(second)


def groups(pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Connected groups of scene ids from matching pairs, in first-seen order."""
    linked = Families({scene: None for pair in pairs for scene in pair})
    for first, second in pairs:
        linked.join(first, second)
    found: dict[str, list[str]] = {}
    for pair in pairs:
        for scene in pair:
            members = found.setdefault(linked.find(scene), [])
            if scene not in members:
                members.append(scene)
    return list(found.values())
