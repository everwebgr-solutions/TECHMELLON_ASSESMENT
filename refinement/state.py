"""
Loop state persistence — tracks iteration history and current prompt.
Saves to a JSON file after each iteration so the loop can resume on crash.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import LOGS_DIR


class LoopState:
    def __init__(self, run_id: str, initial_prompt: str, agent_id: str):
        self.run_id = run_id
        self.agent_id = agent_id
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.current_prompt = initial_prompt
        self.iterations: List[Dict[str, Any]] = []
        self.termination_reason: Optional[str] = None
        self._path = LOGS_DIR / f"run_{run_id}.json"

    def record_iteration(
        self,
        iteration: int,
        scenario_id: str,
        transcript: List[Dict],
        evaluation: Any,  # EvaluationResult
        prompt_diff: str,
        code_patches: List[Dict],
    ) -> None:
        from refinement.evaluator import average_score, scores_dict

        self.iterations.append({
            "iteration": iteration,
            "scenario_id": scenario_id,
            "transcript": transcript,
            "evaluation": {
                "scores": scores_dict(evaluation),
                "average": average_score(evaluation),
                "overall_pass": evaluation.overall_pass,
                "summary": evaluation.summary,
                "failures": [
                    {
                        "criterion": name,
                        "score": crit.score,
                        "root_cause": crit.root_cause,
                        "detail": crit.root_cause_detail,
                        "quotes": crit.failure_quotes,
                    }
                    for name, crit in [
                        ("understanding", evaluation.understanding),
                        ("api_correctness", evaluation.api_correctness),
                        ("outcome_confirmation", evaluation.outcome_confirmation),
                        ("naturalness", evaluation.naturalness),
                    ]
                    if crit.score < 8
                ],
            },
            "changes": {
                "prompt_changed": bool(prompt_diff),
                "prompt_diff": prompt_diff,
                "code_patches": code_patches,
            },
        })
        self._save()

    def _save(self) -> None:
        data = {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "termination_reason": self.termination_reason,
            "iterations": self.iterations,
            "performance_summary": self._performance_summary(),
        }
        self._path.write_text(json.dumps(data, indent=2, default=str))

    def _performance_summary(self) -> Dict[str, Any]:
        if not self.iterations:
            return {}
        first_avg = self.iterations[0]["evaluation"]["average"]
        last_avg = self.iterations[-1]["evaluation"]["average"]
        return {
            "first_iteration_average": round(first_avg, 2),
            "final_iteration_average": round(last_avg, 2),
            "improvement": round(last_avg - first_avg, 2),
            "total_iterations": len(self.iterations),
        }

    def finalize(self, reason: str) -> None:
        self.termination_reason = reason
        self._save()

    @classmethod
    def new(cls, initial_prompt: str, agent_id: str) -> "LoopState":
        run_id = uuid.uuid4().hex[:8]
        return cls(run_id=run_id, initial_prompt=initial_prompt, agent_id=agent_id)

    @property
    def log_path(self) -> Path:
        return self._path
