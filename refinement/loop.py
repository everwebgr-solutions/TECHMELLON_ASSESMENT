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
import subprocess
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
from elevenlabs_client.agent import get_agent, update_agent_prompt, update_agent_tools
from refinement.code_patcher import build_patch_requests_from_failures, generate_and_apply_patch, rollback_applied_patch
from refinement.evaluator import (
    EvaluationResult,
    average_score,
    evaluate_transcript,
    get_code_failures,
    get_prompt_failures,
    scores_dict,
)
from refinement.prompt_fixer import compute_diff, rewrite_prompt
from refinement.scenarios import get_scenario, get_scenario_for_run
from refinement.simulator import simulate_conversation
from refinement.state import LoopState
from refinement.system_prompt import get_initial_prompt

logger = logging.getLogger("loop")

EventCallback = Callable[[str, Dict], None]


def run_loop(
    agent_id: Optional[str] = None,
    on_event: Optional[EventCallback] = None,
    scenario_id: Optional[str] = None,
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

    # Emit immediately so the UI shows feedback while setup runs.
    # on_event may not exist yet (emit() is defined below), so call directly.
    if on_event:
        on_event("initializing", {"message": "Setting up tunnel and agent…"})

    try:
        from pyngrok import conf, ngrok

        if NGROK_AUTHTOKEN:
            conf.get_default().auth_token = NGROK_AUTHTOKEN

        # Reuse the existing tunnel if it's already alive (same process, consecutive
        # runs). Only tear down and restart when no live tunnel exists — saves ~4s.
        existing = []
        try:
            existing = ngrok.get_tunnels()
        except Exception:
            pass

        alive_tunnel = next(
            (t for t in existing if str(API_PORT) in t.config.get("addr", "")),
            None,
        )

        if alive_tunnel:
            public_base_url = alive_tunnel.public_url.rstrip("/")
            public_base_url = public_base_url.replace("http://", "https://", 1)
            ngrok_tunnel = alive_tunnel
            logger.info("[TUNNEL] Reusing existing ngrok tunnel: %s", public_base_url)
        else:
            # Kill stale ngrok in two passes:
            # 1. Via pyngrok (cleans up tunnels it knows about in this session).
            # 2. Via OS-level pkill (catches orphaned ngrok processes left by a
            #    previous Python session that was killed mid-run — pyngrok has no
            #    knowledge of those and ngrok.kill() silently does nothing for them).
            try:
                for tunnel in existing:
                    ngrok.disconnect(tunnel.public_url)
            except Exception:
                pass
            try:
                ngrok.kill()
            except Exception:
                pass
            subprocess.run(["pkill", "-9", "-f", "ngrok"], capture_output=True)
            time.sleep(0.5)  # let the OS reclaim the port before we re-bind

            ngrok_tunnel = ngrok.connect(API_PORT, "http")
            public_base_url = ngrok_tunnel.public_url.rstrip("/")
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

    def _push_prompt(base_prompt: str) -> None:
        """Add today's date header and push the prompt to the existing agent."""
        from datetime import datetime as _dt
        today_str = _dt.utcnow().strftime("%Y-%m-%d")
        dated = f"Today's date is {today_str} (UTC). Use this to interpret relative dates like 'today', 'tomorrow', 'next week'.\n\n{base_prompt}"
        update_agent_prompt(agent_id, dated)

    # Fetch the current base prompt from ElevenLabs (source of truth).
    # Strip any previously injected date header so we don't accumulate them.
    import re as _re
    current_prompt = get_initial_prompt()
    try:
        agent_data = get_agent(agent_id)
        fetched = (
            agent_data.get("conversation_config", {})
            .get("agent", {})
            .get("prompt", {})
            .get("prompt", current_prompt)
        )
        # Remove injected date header from previous runs before storing as base prompt.
        current_prompt = _re.sub(
            r"^Today's date is \d{4}-\d{2}-\d{2} \(UTC\)\. Use this.*?\n\n",
            "",
            fetched,
            flags=_re.DOTALL,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch agent {agent_id} from ElevenLabs: {exc}\n"
            "Check that ELEVENLABS_AGENT_ID in .env is valid, or run 'make setup-agent' to create a new one."
        ) from exc

    # Ensure webhook tool URLs point at the new ngrok tunnel.
    # update_agent_tools may recreate the agent (returning a new id) if the
    # existing tool documents are stale — capture the result in all cases.
    logger.info("[AGENT] Updating webhook URLs on agent %s → %s", agent_id, public_base_url)
    agent_id = update_agent_tools(agent_id, public_base_url)
    _push_prompt(current_prompt)
    logger.info("[AGENT] Agent %s ready", agent_id)

    # Pick one scenario for the entire run.  If scenario_id is explicitly
    # provided (e.g. from the UI dropdown), use it directly without advancing
    # the round-robin index.  Otherwise use get_scenario_for_run() which
    # picks the next scenario in rotation and persists the updated index.
    if scenario_id:
        scenario = get_scenario(scenario_id)
    else:
        scenario = get_scenario_for_run()

    state = LoopState.new(initial_prompt=current_prompt, agent_id=agent_id)

    emit("loop_started", {
        "message": f"Loop started — run_id={state.run_id} — scenario: {scenario['id']}",
        "run_id": state.run_id,
        "max_iterations": MAX_ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "scenario_id": scenario["id"],
        "scenario_description": scenario["description"],
    })

    # Checkpoint: the prompt and list of successful PatchResults from the
    # previous iteration's fix batch.  Used to roll back if the next
    # iteration's evaluation is worse.
    checkpoint_prompt: str = current_prompt
    checkpoint_patches: list = []   # PatchResult objects (success=True only)
    checkpoint_score: Optional[float] = None  # score at the last checkpoint (before fixes)
    prev_average: Optional[float] = None

    for iteration in range(1, MAX_ITERATIONS + 1):
        emit("iteration_started", {
            "message": f"Iteration {iteration}/{MAX_ITERATIONS} — scenario: {scenario['id']}",
            "iteration": iteration,
            "scenario_id": scenario["id"],
            "scenario_description": scenario["description"],
        })

        # ── Step 1: Simulate conversation ─────────────────────────────────────
        logger.info("[SIM] Starting conversation simulation for '%s'", scenario["id"])
        # Clear the API server's tool call log so this simulation starts clean.
        # The log lives in the API server process; we reach it over HTTP.
        try:
            import httpx as _httpx
            _httpx.delete(f"http://localhost:{API_PORT}/api/v1/webhooks/tool-calls", timeout=5.0)
        except Exception:
            pass  # non-fatal — evaluator will just have an empty log

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
        # Fetch the tool call log from the API server process over HTTP.
        tool_calls = []
        try:
            import httpx as _httpx
            _resp = _httpx.get(f"http://localhost:{API_PORT}/api/v1/webhooks/tool-calls", timeout=5.0)
            tool_calls = _resp.json().get("tool_calls", [])
        except Exception:
            pass  # non-fatal — evaluator falls back to transcript-only mode

        try:
            evaluation: EvaluationResult = evaluate_transcript(scenario, transcript, tool_calls=tool_calls)
        except Exception as exc:
            logger.error("[EVAL] Evaluation failed: %s", exc)
            emit("error", {"message": f"Evaluation failed (skipping fixes for this iteration): {exc}", "iteration": iteration})
            state.record_iteration(
                iteration=iteration,
                scenario_id=scenario["id"],
                transcript=transcript,
                evaluation=None,
                prompt_diff="",
                code_patches=[],
                tool_calls=tool_calls,
            )
            emit("iteration_complete", {
                "message": f"Iteration {iteration} complete. Evaluation failed — no fixes applied.",
                "iteration": iteration,
            })
            if iteration < MAX_ITERATIONS:
                time.sleep(2)
            continue

        avg = average_score(evaluation)
        emit("evaluation_complete", {
            "message": f"Scores — avg: {avg:.1f} | {scores_dict(evaluation)} | pass: {evaluation.overall_pass}",
            "iteration": iteration,
            "scores": scores_dict(evaluation),
            "average": avg,
            "overall_pass": evaluation.overall_pass,
            "summary": evaluation.summary,
            "tool_calls": tool_calls,
        })

        # ── Regression check: roll back previous iteration's fixes ─────────────
        rolled_back = False
        if prev_average is not None and avg < prev_average:
            logger.warning(
                "[ROLLBACK] Score regressed %.1f → %.1f — reverting previous fixes",
                prev_average, avg,
            )
            # Restore prompt
            if current_prompt != checkpoint_prompt:
                current_prompt = checkpoint_prompt
                state.current_prompt = current_prompt
                try:
                    _push_prompt(current_prompt)
                except Exception as exc:
                    logger.error("[ROLLBACK] Failed to push rolled-back prompt: %s", exc)

            # Restore code patches (in reverse order)
            for patch_result in reversed(checkpoint_patches):
                ok = rollback_applied_patch(patch_result)
                logger.info(
                    "[ROLLBACK] Code patch %s::%s — %s",
                    patch_result.file_path, patch_result.function_name,
                    "restored" if ok else "restore failed",
                )

            rolled_back = True
            emit("rollback", {
                "message": f"Regression detected (avg {prev_average:.1f} → {avg:.1f}) — previous fixes rolled back",
                "iteration": iteration,
                "previous_average": prev_average,
                "current_average": avg,
            })

            # Reset baseline to the pre-fix score so the next iteration is compared
            # against the restored state, not the (now-invalid) improved score.
            prev_average = checkpoint_score
            checkpoint_patches = []  # patches already reversed — clear to avoid double-rollback

            state.record_iteration(
                iteration=iteration,
                scenario_id=scenario["id"],
                transcript=transcript,
                evaluation=evaluation,
                prompt_diff="",
                code_patches=[],
                rolled_back=True,
                tool_calls=tool_calls,
            )
            emit("iteration_complete", {
                "message": f"Iteration {iteration} complete. Rolled back.",
                "iteration": iteration,
            })
            if iteration < MAX_ITERATIONS:
                time.sleep(2)
            continue  # skip fix step; next iteration retries from restored state

        # Score held or improved — advance the checkpoint baseline
        prev_average = avg
        checkpoint_score = avg   # score at the checkpoint (before any fixes this round)
        checkpoint_prompt = current_prompt
        checkpoint_patches = []

        # ── Check early termination ────────────────────────────────────────────
        if evaluation.overall_pass:
            state.record_iteration(
                iteration=iteration,
                scenario_id=scenario["id"],
                transcript=transcript,
                evaluation=evaluation,
                prompt_diff="",
                code_patches=[],
                tool_calls=tool_calls,
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
                    _push_prompt(new_prompt)
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
                    "diff": result.diff,
                }
                applied_patches.append(patch_record)

                if result.success:
                    checkpoint_patches.append(result)

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
            tool_calls=tool_calls,
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
