from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import canonical_json, content_id


@dataclass(frozen=True, slots=True, order=True)
class TaskKey:
    stage: str
    partition: str

    def __post_init__(self) -> None:
        if not self.stage.strip() or not self.partition.strip():
            raise ValueError("task stage and partition must be non-empty")

    @property
    def task_id(self) -> str:
        return content_id("ktaskv0", self)


@dataclass(frozen=True, slots=True)
class TaskSpec:
    key: TaskKey
    compiler_version: str
    contract: str
    config_hash: str
    input_hash: str
    dependencies: tuple[TaskKey, ...] = ()

    def __post_init__(self) -> None:
        if not self.compiler_version.strip() or not self.contract.strip():
            raise ValueError("compiler_version and contract must be non-empty")
        for name in ("config_hash", "input_hash"):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(f"{name} must be a SHA-256 hex digest")
        if self.key in self.dependencies:
            raise ValueError("task may not depend on itself")
        object.__setattr__(self, "dependencies", tuple(sorted(set(self.dependencies))))


class CacheStatus(str, Enum):
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CacheEntry:
    key: TaskKey
    build_fingerprint: str
    output_hash: str | None
    status: CacheStatus

    def __post_init__(self) -> None:
        if len(self.build_fingerprint) != 64:
            raise ValueError("build_fingerprint must be SHA-256")
        if self.status == CacheStatus.COMPLETE:
            if self.output_hash is None or len(self.output_hash) != 64:
                raise ValueError("complete cache entry requires output_hash")
        elif self.output_hash is not None and len(self.output_hash) != 64:
            raise ValueError("output_hash must be SHA-256 when present")


class PlanDisposition(str, Enum):
    REUSE = "reuse"
    RUN = "run"


@dataclass(frozen=True, slots=True)
class PlannedTask:
    spec: TaskSpec
    disposition: PlanDisposition
    wave: int
    reason_codes: tuple[str, ...]
    expected_fingerprint: str | None

    def __post_init__(self) -> None:
        if self.wave < 0:
            raise ValueError("wave must be non-negative")
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))


@dataclass(frozen=True, slots=True)
class BuildWave:
    wave: int
    task_keys: tuple[TaskKey, ...]


@dataclass(frozen=True, slots=True)
class BuildPlan:
    tasks: tuple[PlannedTask, ...]
    waves: tuple[BuildWave, ...]

    @property
    def plan_hash(self) -> str:
        return sha256(canonical_json({"tasks": self.tasks, "waves": self.waves}).encode("utf-8")).hexdigest()


class TaskGraphError(ValueError):
    pass
