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
    API_PORT,
    ELEVENLABS_AGENT_ID,
    MAX_ITERATIONS,
    NGROK_AUTHTOKEN,
    PASS_THRESHOLD,
)
from elevenlabs_client.agent import create_agent, get_agent, update_agent_prompt
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


def _persist_agent_id(agent_id: str) -> None:
    """Write the new agent ID back to .env so subsequent runs use it."""
    import re
    from pathlib import Path
    env_path = Path(".env")
    if not env_path.exists():
        return
    content = env_path.read_text()
    if "ELEVENLABS_AGENT_ID" in content:
        content = re.sub(
            r"^ELEVENLABS_AGENT_ID=.*$",
            f"ELEVENLABS_AGENT_ID={agent_id}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content += f"\nELEVENLABS_AGENT_ID={agent_id}\n"
    env_path.write_text(content)


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

    # Start a public tunnel so ElevenLabs servers can reach our local webhook API.
    # pyngrok is used in preference to localtunnel: it is a Python library (no npx
    # required), returns the public URL synchronously, and does not inject a
    # "click to proceed" landing page that blocks automated POST requests.
    ngrok_tunnel = None
    public_base_url = None
    try:
        from pyngrok import conf, ngrok

        if NGROK_AUTHTOKEN:
            conf.get_default().auth_token = NGROK_AUTHTOKEN

        # Kill any stale ngrok process left by a previous run before opening a new tunnel.
        ngrok.kill()

        ngrok_tunnel = ngrok.connect(API_PORT, "http")
        public_base_url = ngrok_tunnel.public_url.rstrip("/")
        # ngrok may return an http:// URL on the free tier — upgrade to https
        public_base_url = public_base_url.replace("http://", "https://", 1)
        logger.info("[TUNNEL] ngrok started: %s → localhost:%s", public_base_url, API_PORT)
    except Exception as exc:
        logger.warning("[TUNNEL] Could not start ngrok tunnel: %s — webhooks will not be reachable", exc)
        raise RuntimeError(
            f"ngrok tunnel failed to start: {exc}\n"
            "Bookings require a public tunnel so ElevenLabs can reach your local API.\n"
            "Set NGROK_AUTHTOKEN in .env (free account at https://ngrok.com) and retry."
        ) from exc

    def emit(event_type: str, payload: Dict) -> None:
        if on_event:
            on_event(event_type, payload)
        logger.info("[%s] %s", event_type, payload.get("message", ""))

    # Fetch current prompt from ElevenLabs (source of truth) if the agent exists.
    # If it doesn't exist (deleted externally), fall back to the initial prompt.
    current_prompt = get_initial_prompt()
    if agent_id:
        try:
            agent_data = get_agent(agent_id)
            current_prompt = (
                agent_data.get("conversation_config", {})
                .get("agent", {})
                .get("prompt", {})
                .get("prompt", current_prompt)
            )
        except Exception:
            pass

    # ElevenLabs webhook tools are baked in at agent-creation time and cannot
    # be updated inline via PATCH.  Create a fresh agent with the tunnel URL
    # embedded in the tool definitions.  Persist the new ID back to .env so
    # subsequent runs (and the UI) use the correct agent.
    logger.info("[AGENT] Creating agent with tunnel webhook URLs → %s", public_base_url)
    agent_id = create_agent(current_prompt, base_url=public_base_url)
    logger.info("[AGENT] Agent created: %s", agent_id)
    _persist_agent_id(agent_id)

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
            emit("conversation_turn", {"message": f"[{role.upper()}] {content}", "role": role, "content": content, "iteration": iteration})

        try:
            transcript = simulate_conversation(agent_id, scenario, on_turn=on_turn)
        except Exception as exc:
            logger.error("[SIM] Simulation failed: %s", exc)
            emit("error", {"message": f"Simulation failed: {exc}", "iteration": iteration})
            state.finalize("simulation_error")
            if ngrok_tunnel:
                try:
                    from pyngrok import ngrok as _ngrok
                    _ngrok.disconnect(ngrok_tunnel.public_url)
                except Exception:
                    pass
            return state

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
            if ngrok_tunnel:
                try:
                    from pyngrok import ngrok as _ngrok
                    _ngrok.disconnect(ngrok_tunnel.public_url)
                except Exception:
                    pass
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

                try:
                    update_agent_prompt(agent_id, new_prompt)
                    emit("prompt_updated", {
                        "message": f"System prompt updated on agent {agent_id}",
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

    if ngrok_tunnel:
        try:
            from pyngrok import ngrok as _ngrok
            _ngrok.disconnect(ngrok_tunnel.public_url)
        except Exception:
            pass

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
