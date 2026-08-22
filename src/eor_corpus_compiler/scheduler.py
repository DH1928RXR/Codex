from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
from typing import Mapping, Sequence

from .build import canonical_json
from .scheduler_model import (
    BuildPlan,
    BuildWave,
    CacheEntry,
    CacheStatus,
    PlanDisposition,
    PlannedTask,
    TaskGraphError,
    TaskKey,
    TaskSpec,
)


def task_fingerprint(spec: TaskSpec, dependency_outputs: Mapping[TaskKey, str]) -> str:
    missing = [dep for dep in spec.dependencies if dep not in dependency_outputs]
    if missing:
        raise TaskGraphError(f"missing dependency outputs for fingerprint: {missing}")
    payload = {
        "stage": spec.key.stage,
        "partition": spec.key.partition,
        "compiler_version": spec.compiler_version,
        "contract": spec.contract,
        "config_hash": spec.config_hash,
        "input_hash": spec.input_hash,
        "dependencies": [
            {"key": dep, "output_hash": dependency_outputs[dep]}
            for dep in spec.dependencies
        ],
    }
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class IncrementalScheduler:
    """K12 deterministic DAG planner with content-bound cache reuse.

    Planning is conservative: if a dependency must rerun, its dependents are marked
    RUN for the current plan. After a completed wave, callers may replan using the
    new cache; if the dependency's output hash is unchanged, downstream tasks can
    collapse back to REUSE rather than doing unnecessary work.
    """

    @staticmethod
    def _validate_graph(specs: Sequence[TaskSpec]) -> tuple[dict[TaskKey, TaskSpec], dict[TaskKey, int]]:
        by_key: dict[TaskKey, TaskSpec] = {}
        for spec in specs:
            if spec.key in by_key:
                raise TaskGraphError(f"duplicate task key: {spec.key}")
            by_key[spec.key] = spec
        for spec in specs:
            unknown = [dep for dep in spec.dependencies if dep not in by_key]
            if unknown:
                raise TaskGraphError(f"task {spec.key} has unknown dependencies: {unknown}")

        indegree = {key: 0 for key in by_key}
        children: dict[TaskKey, list[TaskKey]] = defaultdict(list)
        for spec in specs:
            indegree[spec.key] = len(spec.dependencies)
            for dep in spec.dependencies:
                children[dep].append(spec.key)

        queue = deque(sorted(key for key, degree in indegree.items() if degree == 0))
        wave_index: dict[TaskKey, int] = {}
        visited = 0
        while queue:
            key = queue.popleft()
            visited += 1
            spec = by_key[key]
            wave_index[key] = 0 if not spec.dependencies else 1 + max(wave_index[dep] for dep in spec.dependencies)
            for child in sorted(children.get(key, [])):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(by_key):
            raise TaskGraphError("task graph contains a dependency cycle")
        return by_key, wave_index

    def plan(self, specs: Sequence[TaskSpec], cache: Mapping[TaskKey, CacheEntry]) -> BuildPlan:
        by_key, wave_index = self._validate_graph(specs)
        planned: dict[TaskKey, PlannedTask] = {}

        for key in sorted(by_key, key=lambda k: (wave_index[k], k)):
            spec = by_key[key]
            reasons: list[str] = []
            dependency_dirty = any(planned[dep].disposition == PlanDisposition.RUN for dep in spec.dependencies)
            if dependency_dirty:
                reasons.append("dependency_dirty")
                planned[key] = PlannedTask(spec, PlanDisposition.RUN, wave_index[key], tuple(reasons), None)
                continue

            dep_outputs: dict[TaskKey, str] = {}
            dependency_cache_invalid = False
            for dep in spec.dependencies:
                entry = cache.get(dep)
                if entry is None or entry.status != CacheStatus.COMPLETE or entry.output_hash is None:
                    dependency_cache_invalid = True
                    reasons.append("dependency_cache_unavailable")
                    break
                dep_outputs[dep] = entry.output_hash
            if dependency_cache_invalid:
                planned[key] = PlannedTask(spec, PlanDisposition.RUN, wave_index[key], tuple(reasons), None)
                continue

            expected = task_fingerprint(spec, dep_outputs)
            entry = cache.get(key)
            if entry is None:
                reasons.append("no_cache")
                disposition = PlanDisposition.RUN
            elif entry.status != CacheStatus.COMPLETE:
                reasons.append("previous_failure")
                disposition = PlanDisposition.RUN
            elif entry.build_fingerprint != expected:
                reasons.append("fingerprint_changed")
                disposition = PlanDisposition.RUN
            else:
                reasons.append("exact_cache_hit")
                disposition = PlanDisposition.REUSE
            planned[key] = PlannedTask(spec, disposition, wave_index[key], tuple(reasons), expected)

        max_wave = max(wave_index.values(), default=-1)
        waves = tuple(
            BuildWave(
                wave,
                tuple(sorted(key for key, index in wave_index.items() if index == wave and planned[key].disposition == PlanDisposition.RUN)),
            )
            for wave in range(max_wave + 1)
            if any(index == wave and planned[key].disposition == PlanDisposition.RUN for key, index in wave_index.items())
        )
        return BuildPlan(
            tuple(sorted(planned.values(), key=lambda task: (task.wave, task.spec.key))),
            waves,
        )

    @staticmethod
    def complete_entry(spec: TaskSpec, dependency_outputs: Mapping[TaskKey, str], output_hash: str) -> CacheEntry:
        if len(output_hash) != 64:
            raise ValueError("output_hash must be SHA-256")
        return CacheEntry(spec.key, task_fingerprint(spec, dependency_outputs), output_hash, CacheStatus.COMPLETE)

    @staticmethod
    def failed_entry(spec: TaskSpec, dependency_outputs: Mapping[TaskKey, str]) -> CacheEntry:
        return CacheEntry(spec.key, task_fingerprint(spec, dependency_outputs), None, CacheStatus.FAILED)


class CorpusTaskGraphBuilder:
    """Reference K00-K11 graph: conversation-local map passes, then global reducers.

    The generic scheduler is partition-agnostic; later revisions may shard K04-K11
    by entity/topic without changing scheduler semantics.
    """

    def __init__(self, versions: Mapping[str, str], config_hashes: Mapping[str, str]):
        self.versions = dict(versions)
        self.config_hashes = dict(config_hashes)

    def _spec(self, stage: str, partition: str, contract: str, input_hash: str, dependencies=()) -> TaskSpec:
        version = self.versions.get(stage, "0.1.0")
        config_hash = self.config_hashes.get(stage, sha256(b"{}").hexdigest())
        return TaskSpec(TaskKey(stage, partition), version, contract, config_hash, input_hash, tuple(dependencies))

    def build(self, conversation_hashes: Mapping[str, str], *, global_input_hash: str) -> tuple[TaskSpec, ...]:
        if len(global_input_hash) != 64:
            raise ValueError("global_input_hash must be SHA-256")
        specs: list[TaskSpec] = []
        k02_keys = []
        k03_keys = []
        for conversation_id, input_hash in sorted(conversation_hashes.items()):
            k01 = self._spec("K01", conversation_id, "eor.corpus_candidate_assertion.v0", input_hash)
            k02 = self._spec("K02", conversation_id, "eor.corpus_candidate_validation.v0", input_hash, (k01.key,))
            k03 = self._spec("K03", conversation_id, "eor.corpus_entity_mentions.v0", input_hash, (k02.key,))
            specs.extend((k01, k02, k03))
            k02_keys.append(k02.key)
            k03_keys.append(k03.key)

        k04 = self._spec("K04", "global", "eor.corpus_entity_resolution.v0", global_input_hash, tuple(k03_keys))
        k05 = self._spec("K05", "global", "eor.corpus_semantic_normalization.v0", global_input_hash, tuple(k02_keys) + (k04.key,))
        k06 = self._spec("K06", "global", "eor.corpus_relation_compilation.v0", global_input_hash, (k05.key,))
        k07 = self._spec("K07", "global", "eor.corpus_temporal_state.v0", global_input_hash, (k05.key,))
        k08 = self._spec("K08", "global", "eor.corpus_conflict_compilation.v0", global_input_hash, (k06.key, k07.key))
        k09 = self._spec("K09", "global", "eor.corpus_synthesis_projection.v0", global_input_hash, (k04.key, k05.key, k06.key, k07.key, k08.key))
        k10 = self._spec("K10", "global", "eor.corpus_review_queue.v0", global_input_hash, (k04.key, k05.key, k06.key, k07.key, k08.key, k09.key))
        k11 = self._spec("K11", "global", "eor.corpus_m02_staging_adapter.v0", global_input_hash, tuple(k02_keys) + (k05.key, k06.key, k07.key, k08.key, k10.key))
        specs.extend((k04, k05, k06, k07, k08, k09, k10, k11))
        return tuple(specs)
