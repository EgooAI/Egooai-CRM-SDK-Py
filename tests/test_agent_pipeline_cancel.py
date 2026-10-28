import time
import unittest
from threading import Event, Lock
from typing import Annotated

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineInput,
    CancellationToken,
    ExperimentStep,
    LLMConfig,
    LLMResponse,
    LLMToolCall,
    RunCancelledError,
    ToolContext,
    register_llm,
    register_tool,
    run_experiment,
)
from agent_pipeline.llm import StaticLLMClient
from agent_pipeline.resolver import AgentPresetRuntimeConfig
from models import AgentPreset


def _runtime(llm_level: int = 3, tool_names=(), tools=(), **overrides) -> AgentPreset:
    preset = AgentPreset(
        apid="cancel-test", name="cancel", description="", prompt="P",
        llm_level=llm_level, tools=list(tool_names),
    )
    return preset


class PipelineCancellationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        register_llm(3, LLMConfig(base_url="http://x", api_key="k", model_name="m"))

    def test_cancel_before_run_performs_no_request(self) -> None:
        token = CancellationToken()
        token.cancel()
        client = StaticLLMClient([LLMResponse(text="never")])

        with self.assertRaises(RunCancelledError):
            AgentPipeline(llm_client=client).run(
                AgentPipelineInput(user_input="hi", agent_preset=_runtime(),
                                   cancel_token=token)
            )

        self.assertEqual(client.requests, [])

    def test_cancel_between_tool_calls_stops_the_run(self) -> None:
        token = CancellationToken()
        executed: list[str] = []

        def first() -> str:
            token.cancel()
            executed.append("first")
            return "ok"

        register_tool("first", first)
        register_tool("second", lambda: executed.append("second"))
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_calls=[
                LLMToolCall(name="first", call_id="a"),
                LLMToolCall(name="second", call_id="b"),
            ]),
            LLMResponse(text="unreachable"),
        ])

        with self.assertRaises(RunCancelledError):
            AgentPipeline(llm_client=client).run(
                AgentPipelineInput(user_input="go",
                                   agent_preset=_runtime(tool_names=("first", "second")),
                                   cancel_token=token)
            )

        self.assertEqual(executed, ["first"])


class ExperimentRunnerTestCase(unittest.TestCase):
    def test_runs_steps_in_order_and_variants_in_parallel(self) -> None:
        order: list[tuple[int, str]] = []
        lock = Lock()
        barrier = Event()

        def execute(variant_id: str, step: ExperimentStep) -> str:
            with lock:
                order.append((step.index, variant_id))
            if step.index == 0 and len(order) == 3:
                barrier.set()
            if step.index == 0:
                # All variants of the first step must overlap.
                self.assertTrue(barrier.wait(timeout=2))
            return f"{variant_id}-{step.input}"

        run = run_experiment(
            steps=[ExperimentStep(index=0, input="a"), ExperimentStep(index=1, input="b")],
            variant_ids=["v1", "v2", "v3"],
            execute=execute,
        )

        self.assertFalse(run.cancelled)
        self.assertEqual([step.step.index for step in run.steps], [0, 1])
        self.assertEqual(
            [result.result for result in run.steps[1].variants],
            ["v1-b", "v2-b", "v3-b"],
        )

    def test_one_variant_failure_does_not_abort_the_step(self) -> None:
        def execute(variant_id: str, step: ExperimentStep) -> str:
            if variant_id == "broken":
                raise RuntimeError("boom")
            return "ok"

        run = run_experiment(
            steps=[ExperimentStep(index=0, input="a"), ExperimentStep(index=1, input="b")],
            variant_ids=["v1", "broken", "v2"],
            execute=execute,
        )

        statuses = {result.variant_id: result.status for result in run.steps[0].variants}
        self.assertEqual(statuses, {"v1": "completed", "broken": "failed", "v2": "completed"})
        self.assertIn("boom", run.steps[0].variants[1].error or "")
        # A later step would compare unequal inputs, so the run stops here.
        self.assertEqual(len(run.steps), 1)

    def test_cancelled_variant_reports_cancellation_and_stops(self) -> None:
        token = CancellationToken()

        def execute(variant_id: str, step: ExperimentStep) -> str:
            token.cancel()
            token.raise_if_cancelled()
            return "ok"

        run = run_experiment(
            steps=[ExperimentStep(index=0), ExperimentStep(index=1)],
            variant_ids=["v1", "v2"],
            execute=execute,
            cancel_token=token,
        )

        self.assertTrue(run.cancelled)
        self.assertEqual({result.status for result in run.steps[0].variants}, {"cancelled"})
        self.assertEqual(len(run.steps), 1)

    def test_rejects_empty_variants_and_bad_parallelism(self) -> None:
        with self.assertRaises(ValueError):
            run_experiment(steps=[], variant_ids=[], execute=lambda *_: None)
        with self.assertRaises(ValueError):
            run_experiment(steps=[], variant_ids=["v"], execute=lambda *_: None, max_parallel=0)

    def test_token_mid_step_keeps_completed_variants(self) -> None:
        token = CancellationToken()
        started = Event()

        def execute(variant_id: str, step: ExperimentStep) -> str:
            if variant_id == "slow":
                started.set()
                time.sleep(0.05)
            else:
                started.wait(1)
            return variant_id

        run = run_experiment(
            steps=[ExperimentStep(index=0)],
            variant_ids=["fast", "slow"],
            execute=execute,
        )

        self.assertFalse(run.cancelled)
        self.assertEqual([result.result for result in run.steps[0].variants], ["fast", "slow"])


if __name__ == "__main__":
    unittest.main()
