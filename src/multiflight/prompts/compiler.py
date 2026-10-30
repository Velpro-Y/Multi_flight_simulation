"""Deterministically assemble protected and optimizable prompt blocks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..scene_registry import SceneSpec
from ..settings import PROMPT_DIR


@dataclass(frozen=True)
class PromptArtifact:
    scene_id: str
    version: str
    text: str
    prompt_hash: str
    protected_hash: str
    block_hashes: dict[str, str]


class PromptCompiler:
    PROTECTED_FILES = {
        "base_role": "base_role.md",
        "model_facts": "model_facts.md",
        "tool_contract": "tool_contract.md",
    }

    def __init__(self, prompt_dir: Path = PROMPT_DIR):
        self.prompt_dir = prompt_dir

    def compile(
        self,
        scene: SceneSpec,
        version: str,
        addendum: str = "",
    ) -> PromptArtifact:
        if scene.status != "enabled":
            raise ValueError(f"Scene {scene.scene_id} is not enabled")

        protected: list[tuple[str, str]] = []
        for block_name in scene.protected_prompt_blocks:
            filename = self.PROTECTED_FILES[block_name]
            protected.append((block_name, self._read(filename)))

        scene_text = self._read(f"scenes/{scene.scene_id}.md")
        blocks = protected + [("scene_policy", scene_text)]
        if addendum.strip():
            blocks.append(("decision_checklist", addendum.strip()))

        block_hashes = {name: _sha256(text) for name, text in blocks}
        protected_text = "\n\n".join(text for _, text in protected)
        compiled = "\n\n---\n\n".join(text.strip() for _, text in blocks).strip() + "\n"
        return PromptArtifact(
            scene_id=scene.scene_id,
            version=version,
            text=compiled,
            prompt_hash=_sha256(compiled),
            protected_hash=_sha256(protected_text),
            block_hashes=block_hashes,
        )

    def _read(self, relative_path: str) -> str:
        path = self.prompt_dir / relative_path
        return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

