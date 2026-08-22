from hashlib import sha256

import pytest

from eor_corpus_compiler.scheduler import CorpusTaskGraphBuilder, IncrementalScheduler, task_fingerprint
from eor_corpus_compiler.scheduler_model import (
    CacheEntry,
    CacheStatus,
    PlanDisposition,
    TaskGraphError,
    TaskKey,
    TaskSpec,
)


def h(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def spec(stage, partition, input_value, deps=(), version="1"):
    return TaskSpec(TaskKey(stage, partition), version, f"contract:{stage}", h(f"config:{stage}"), h(input_value), tuple(deps))


def test_unknown_dependency_is_rejected():
    item = spec("B", "x", "b", (TaskKey("A", "x"),))
    with pytest.raises(TaskGraphError):
        IncrementalScheduler().plan((item,), {})


def test_dependency_cycle_is_rejected():
    a = spec("A", "x", "a", (TaskKey("B", "x"),))
    b = spec("B", "x", "b", (a.key,))
    with pytest.raises(TaskGraphError):
        IncrementalScheduler().plan((a, b), {})


def test_exact_cache_hit_reuses_task():
    item = spec("A", "x", "input")
    output = h("output")
    entry = IncrementalScheduler.complete_entry(item, {}, output)
    plan = IncrementalScheduler().plan((item,), {item.key: entry})
    assert plan.tasks[0].disposition == PlanDisposition.REUSE
    assert plan.waves == ()


def test_input_change_invalidates_task_and_dependency_chain_but_not_independent_partition():
    old_a = spec("A", "one", "old")
    new_a = spec("A", "one", "new")
    independent = spec("A", "two", "stable")
    downstream = spec("B", "global", "global", (new_a.key, independent.key))

    old_a_entry = IncrementalScheduler.complete_entry(old_a, {}, h("a-output"))
    independent_entry = IncrementalScheduler.complete_entry(independent, {}, h("i-output"))
    old_downstream = spec("B", "global", "global", (old_a.key, independent.key))
    downstream_entry = IncrementalScheduler.complete_entry(
        old_downstream,
        {old_a.key: h("a-output"), independent.key: h("i-output")},
        h("b-output"),
    )
    cache = {old_a.key: old_a_entry, independent.key: independent_entry, downstream.key: downstream_entry}
    plan = IncrementalScheduler().plan((new_a, independent, downstream), cache)
    dispositions = {p.spec.key: p.disposition for p in plan.tasks}
    assert dispositions[new_a.key] == PlanDisposition.RUN
    assert dispositions[independent.key] == PlanDisposition.REUSE
    assert dispositions[downstream.key] == PlanDisposition.RUN


def test_compiler_version_change_invalidates_cache():
    old = spec("A", "x", "input", version="1")
    new = spec("A", "x", "input", version="2")
    entry = IncrementalScheduler.complete_entry(old, {}, h("output"))
    plan = IncrementalScheduler().plan((new,), {new.key: entry})
    assert plan.tasks[0].disposition == PlanDisposition.RUN
    assert "fingerprint_changed" in plan.tasks[0].reason_codes


def test_failed_cache_entry_is_rerun():
    item = spec("A", "x", "input")
    failed = CacheEntry(item.key, task_fingerprint(item, {}), None, CacheStatus.FAILED)
    plan = IncrementalScheduler().plan((item,), {item.key: failed})
    assert plan.tasks[0].disposition == PlanDisposition.RUN
    assert "previous_failure" in plan.tasks[0].reason_codes


def test_same_wave_partitions_are_parallelizable():
    one = spec("K01", "conversation:1", "one")
    two = spec("K01", "conversation:2", "two")
    reducer = spec("K04", "global", "global", (one.key, two.key))
    plan = IncrementalScheduler().plan((one, two, reducer), {})
    assert plan.waves[0].wave == 0
    assert plan.waves[0].task_keys == tuple(sorted((one.key, two.key)))
    assert plan.waves[1].task_keys == (reducer.key,)


def test_replan_can_restore_downstream_cache_when_changed_task_output_is_identical():
    old_a = spec("A", "x", "old-input")
    new_a = spec("A", "x", "new-input")
    b = spec("B", "x", "b-input", (new_a.key,))
    a_output = h("same-semantic-output")
    b_output = h("b-output")

    old_a_entry = IncrementalScheduler.complete_entry(old_a, {}, a_output)
    old_b = spec("B", "x", "b-input", (old_a.key,))
    b_entry = IncrementalScheduler.complete_entry(old_b, {old_a.key: a_output}, b_output)
    first_plan = IncrementalScheduler().plan((new_a, b), {new_a.key: old_a_entry, b.key: b_entry})
    assert all(task.disposition == PlanDisposition.RUN for task in first_plan.tasks)

    new_a_entry = IncrementalScheduler.complete_entry(new_a, {}, a_output)
    second_plan = IncrementalScheduler().plan((new_a, b), {new_a.key: new_a_entry, b.key: b_entry})
    dispositions = {task.spec.key: task.disposition for task in second_plan.tasks}
    assert dispositions[new_a.key] == PlanDisposition.REUSE
    assert dispositions[b.key] == PlanDisposition.REUSE


def test_reference_corpus_graph_maps_conversations_then_reduces_globally():
    builder = CorpusTaskGraphBuilder({}, {})
    specs = builder.build({"conv-a": h("a"), "conv-b": h("b")}, global_input_hash=h("global"))
    by_key = {item.key: item for item in specs}
    assert TaskKey("K01", "conv-a") in by_key
    assert TaskKey("K01", "conv-b") in by_key
    assert set(by_key[TaskKey("K04", "global")].dependencies) == {
        TaskKey("K03", "conv-a"), TaskKey("K03", "conv-b")
    }
    assert TaskKey("K10", "global") in by_key[TaskKey("K11", "global")].dependencies

    plan = IncrementalScheduler().plan(specs, {})
    wave_by_key = {task.spec.key: task.wave for task in plan.tasks}
    assert wave_by_key[TaskKey("K01", "conv-a")] == 0
    assert wave_by_key[TaskKey("K03", "conv-a")] == 2
    assert wave_by_key[TaskKey("K04", "global")] == 3
    assert wave_by_key[TaskKey("K06", "global")] == wave_by_key[TaskKey("K07", "global")]
    assert wave_by_key[TaskKey("K11", "global")] > wave_by_key[TaskKey("K10", "global")]
