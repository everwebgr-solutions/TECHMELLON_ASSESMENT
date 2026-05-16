"""
Autonomous refinement loop orchestrator.

Cycle:
  1. Select scenario (rotating round-robin)
  2. Simulate conversation via ElevenLabs Chat Mode
  3. Evaluate transcript (LLM evaluator)
  4. Fix: prompt patches + code patches if needed
  5. Push updated prompt to ElevenLabs
  6. Repeat until all scores >= PASS_THRESHOLD or MAX_ITERATIONS reached

Run: python -m refinement.loop
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Callable, Dict, List, Optional

from config import (
    ELEVENLABS_AGENT_ID,
    MAX_ITERATIONS,
    PASS_THRESHOLD,
)
from elevenlabs_client.agent import get_agent, update_agent_prompt
from refinement.code_patcher import build_patch_requests_from_failures, generate_and_apply_patch
from refinement.evaluator import (
    EvaluationResult,
    average_score,
    evaluate_transcript,
    get_code_failures,
    get_prompt_failures,
    scores_dict,
)
from refinement.prompt_fixer import compute_diff, rewrite_prompt
from refinement.scenarios import get_rotating_scenario
from refinement.simulator import simulate_conversation
from refinement.state import LoopState
from refinement.system_prompt import get_initial_prompt

logger = logging.getLogger("loop")


EventCallback = Callable[[str, Dict], None]


def run_loop(
    agent_id: Optional[str] = None,
    on_event: Optional[EventCallback] = None,
) -> LoopState:
    """
    Run the full autonomous refinement loop.

    Args:
        agent_id: ElevenLabs agent ID. Uses ELEVENLABS_AGENT_ID from config if not provided.
        on_event: Optional callback(event_type, payload) for real-time UI streaming.

    Returns:
        Final LoopState with full iteration history.
    """
    agent_id = agent_id or ELEVENLABS_AGENT_ID

    if not agent_id:
        raise RuntimeError(
            "No ElevenLabs agent ID configured. "
            "Run 'python -m elevenlabs_client.setup' first or set ELEVENLABS_AGENT_ID in .env"
        )

    def emit(event_type: str, payload: Dict) -> None:
        if on_event:
            on_event(event_type, payload)
        logger.info("[%s] %s", event_type, payload.get("message", ""))

    # Fetch current prompt from ElevenLabs (source of truth)
    try:
        agent_data = get_agent(agent_id)
        current_prompt = (
            agent_data.get("conversation_config", {})
            .get("agent", {})
            .get("prompt", {})
            .get("prompt", get_initial_prompt())
        )
    except Exception:
        current_prompt = get_initial_prompt()

    state = LoopState.new(initial_prompt=current_prompt, agent_id=agent_id)

    emit("loop_started", {
        "message": f"Loop started — run_id={state.run_id}",
        "run_id": state.run_id,
        "max_iterations": MAX_ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
    })

    for iteration in range(1, MAX_ITERATIONS + 1):
        scenario = get_rotating_scenario(iteration)

        emit("iteration_started", {
            "message": f"Iteration {iteration}/{MAX_ITERATIONS} — scenario: {scenario['id']}",
            "iteration": iteration,
            "scenario_id": scenario["id"],
            "scenario_description": scenario["description"],
        })

        # ── Step 1: Simulate conversation ─────────────────────────────────────
        logger.info("[SIM] Starting conversation simulation for '%s'", scenario["id"])

        def on_turn(role: str, content: str) -> None:
            emit("conversation_turn", {"role": role, "content": content, "iteration": iteration})

        try:
            transcript = simulate_conversation(agent_id, scenario, on_turn=on_turn)
        except Exception as exc:
            logger.error("[SIM] Simulation failed: %s", exc)
            emit("error", {"message": f"Simulation failed: {exc}", "iteration": iteration})
            continue

        emit("simulation_complete", {
            "message": f"Conversation complete — {len(transcript)} turns",
            "iteration": iteration,
            "turn_count": len(transcript),
        })

        # ── Step 2: Evaluate ──────────────────────────────────────────────────
        logger.info("[EVAL] Evaluating transcript...")

        try:
            evaluation: EvaluationResult = evaluate_transcript(scenario, transcript)
        except Exception as exc:
            logger.error("[EVAL] Evaluation failed: %s", exc)
            emit("error", {"message": f"Evaluation failed: {exc}", "iteration": iteration})
            continue

        avg = average_score(evaluation)
        emit("evaluation_complete", {
            "message": f"Scores — avg: {avg:.1f} | {scores_dict(evaluation)} | pass: {evaluation.overall_pass}",
            "iteration": iteration,
            "scores": scores_dict(evaluation),
            "average": avg,
            "overall_pass": evaluation.overall_pass,
            "summary": evaluation.summary,
        })

        # ── Check early termination ────────────────────────────────────────────
        if evaluation.overall_pass:
            state.record_iteration(
                iteration=iteration,
                scenario_id=scenario["id"],
                transcript=transcript,
                evaluation=evaluation,
                prompt_diff="",
                code_patches=[],
            )
            state.finalize("all_passing")
            emit("loop_complete", {
                "message": f"All scores >= {PASS_THRESHOLD}. Loop complete in {iteration} iterations.",
                "reason": "all_passing",
                "iterations": iteration,
            })
            return state

        # ── Step 3: Plan and apply fixes ──────────────────────────────────────
        prompt_failures = get_prompt_failures(evaluation)
        code_failures = get_code_failures(evaluation)

        prompt_diff = ""
        applied_patches = []

        # Prompt fix
        if prompt_failures:
            logger.info("[FIX] Rewriting prompt for %d prompt failures", len(prompt_failures))
            new_prompt = rewrite_prompt(current_prompt, prompt_failures)

            if new_prompt != current_prompt:
                prompt_diff = compute_diff(current_prompt, new_prompt)
                current_prompt = new_prompt
                state.current_prompt = new_prompt

                # Push to ElevenLabs
                try:
                    update_agent_prompt(agent_id, new_prompt)
                    emit("prompt_updated", {
                        "message": "System prompt updated on ElevenLabs",
                        "iteration": iteration,
                        "diff": prompt_diff,
                    })
                except Exception as exc:
                    logger.error("[FIX] Failed to push prompt to ElevenLabs: %s", exc)
            else:
                logger.info("[FIX] Prompt rewrite produced no change — skipping update")

        # Code patches
        if code_failures:
            patch_requests = build_patch_requests_from_failures(code_failures)

            for req in patch_requests:
                logger.info("[PATCH] Patching %s::%s", req.file_path, req.function_name)
                result = generate_and_apply_patch(req)

                patch_record = {
                    "file": req.file_path,
                    "function": req.function_name,
                    "success": result.success,
                    "reason": result.reason,
                }
                applied_patches.append(patch_record)

                emit("code_patched", {
                    "message": f"Patch {'applied' if result.success else 'FAILED'}: {req.file_path}::{req.function_name} — {result.reason}",
                    "iteration": iteration,
                    **patch_record,
                })

        # ── Record iteration ───────────────────────────────────────────────────
        state.record_iteration(
            iteration=iteration,
            scenario_id=scenario["id"],
            transcript=transcript,
            evaluation=evaluation,
            prompt_diff=prompt_diff,
            code_patches=applied_patches,
        )

        emit("iteration_complete", {
            "message": f"Iteration {iteration} complete. Prompt changed: {bool(prompt_diff)}. Patches: {len(applied_patches)}.",
            "iteration": iteration,
        })

        # Small pause between iterations to avoid rate limiting
        if iteration < MAX_ITERATIONS:
            time.sleep(2)

    # Max iterations reached
    state.finalize("max_iterations")
    emit("loop_complete", {
        "message": f"Max iterations ({MAX_ITERATIONS}) reached.",
        "reason": "max_iterations",
        "iterations": MAX_ITERATIONS,
    })

    return state


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    state = run_loop()
    print(f"\nRun complete. Log: {state.log_path}")
    if state.iterations:
        summary = state.iterations[-1]["evaluation"]
        print(f"Final scores: {summary['scores']} (avg: {summary['average']:.1f})")
