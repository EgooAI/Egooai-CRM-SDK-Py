"""Run one experiment step across several variants.

The SDK owns the scheduling policy only: steps run in order, variants run in
parallel within a step, and one variant's failure never aborts its siblings.
What a variant actually *is* (a preset, a draft snapshot, a pinned revision)
and what a step *produces* stay with the caller through ``execute``.

Cancellation is cooperative and applies at step and variant boundaries; the
caller remains responsible for checking the same token inside each run.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, TypeVar

from agent_pipeline.cancel import CancellationToken
from agent_pipeline.errors import RunCancelledError

T = TypeVar("T")

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

DEFAULT_MAX_PARALLEL = 4


@dataclass(frozen=True)
class ExperimentStep:
    """One input applied to every variant; ``index`` is the position in order."""

    index: int
    input: str = ""
    kind: str = "buyer"
    label: str = ""


@dataclass(frozen=True)
class VariantRun(Generic[T]):
    variant_id: str
    status: str
    result: Optional[T] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class StepRun(Generic[T]):
    step: ExperimentStep
    variants: list[VariantRun[T]] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return all(run.status == STATUS_COMPLETED for run in self.variants)


@dataclass(frozen=True)
class ExperimentRun(Generic[T]):
    """Results of a whole experiment run, one entry per attempted step."""

    steps: list[StepRun[T]] = field(default_factory=list)
    cancelled: bool = False

    @property
    def last_step(self) -> Optional[StepRun[T]]:
        return self.steps[-1] if self.steps else None


def run_experiment(
    *,
    steps: list[ExperimentStep],
    variant_ids: list[str],
    execute: Any,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
    cancel_token: Optional[CancellationToken] = None,
) -> ExperimentRun[Any]:
    """Run ``execute(variant_id, step)`` for every ``(step, variant)`` pair.

    ``execute`` is called concurrently and must be thread-safe. Variants whose
    call raised are marked ``failed`` and are not retried for later steps in
    the same run; the remaining variants keep going. Cancellation stops at the
    next boundary and reports every unfinished variant as ``cancelled``.
    """
    if max_parallel < 1:
        raise ValueError("max_parallel must be greater than 0")
    ordered_variants = list(dict.fromkeys(variant_ids))
    if not ordered_variants:
        raise ValueError("variant_ids must not be empty")

    run = ExperimentRun[Any]()
    failed: set[str] = set()
    cancelled = False

    for step in steps:
        if cancel_token is not None and cancel_token.cancelled:
            cancelled = True
            break
        active = [variant_id for variant_id in ordered_variants if variant_id not in failed]
        if not active:
            break
        results = _run_step(execute, step, active, max_parallel, cancel_token)
        run.steps.append(StepRun(step=step, variants=results))
        for result in results:
            if result.status == STATUS_FAILED:
                failed.add(result.variant_id)
        if any(result.status == STATUS_CANCELLED for result in results):
            cancelled = True
            break
        if failed:
            # Report the failure once, then stop: a later step would compare
            # unequal inputs across variants.
            break

    return ExperimentRun(steps=run.steps, cancelled=cancelled)


def _run_step(
    execute: Any,
    step: ExperimentStep,
    variant_ids: list[str],
    max_parallel: int,
    cancel_token: Optional[CancellationToken],
) -> list[VariantRun[Any]]:
    with ThreadPoolExecutor(max_workers=min(max_parallel, len(variant_ids))) as pool:
        futures: list[Future] = [
            pool.submit(_execute_one, execute, variant_id, step, cancel_token)
            for variant_id in variant_ids
        ]
    return [future.result() for future in futures]


def _execute_one(
    execute: Any,
    variant_id: str,
    step: ExperimentStep,
    cancel_token: Optional[CancellationToken],
) -> VariantRun[Any]:
    if cancel_token is not None and cancel_token.cancelled:
        return VariantRun(variant_id=variant_id, status=STATUS_CANCELLED)
    try:
        result = execute(variant_id, step)
    except RunCancelledError:
        return VariantRun(variant_id=variant_id, status=STATUS_CANCELLED)
    except Exception as exc:  # one variant's failure must not abort the step
        return VariantRun(variant_id=variant_id, status=STATUS_FAILED, error=str(exc))
    return VariantRun(variant_id=variant_id, status=STATUS_COMPLETED, result=result)


__all__ = [
    "DEFAULT_MAX_PARALLEL",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "ExperimentRun",
    "ExperimentStep",
    "StepRun",
    "VariantRun",
    "run_experiment",
]
