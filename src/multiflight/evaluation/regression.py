"""Champion/challenger non-regression gate."""

from __future__ import annotations

from typing import Any


class RegressionGate:
    def compare(
        self,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        protected_hash_matches: bool,
    ) -> dict[str, Any]:
        baseline_failures = set(baseline.get("failure_labels", []))
        candidate_failures = set(candidate.get("failure_labels", []))
        baseline_score = float(baseline.get("metrics", {}).get("score", 0.0))
        candidate_score = float(candidate.get("metrics", {}).get("score", 0.0))

        checks = {
            "protected_content_unchanged": protected_hash_matches,
            "candidate_hard_gates_pass": bool(candidate.get("passed")),
            "no_new_failure_labels": candidate_failures.issubset(baseline_failures),
            "score_not_lower": candidate_score >= baseline_score - 0.001,
        }
        passed = all(checks.values())
        improved = passed and candidate_score > baseline_score + 0.5
        return {
            "passed": passed,
            "improved": improved,
            "checks": checks,
            "baseline": {
                "prompt_version": baseline.get("prompt_version"),
                "passed": baseline.get("passed"),
                "score": baseline_score,
                "failure_labels": sorted(baseline_failures),
            },
            "candidate": {
                "prompt_version": candidate.get("prompt_version"),
                "passed": candidate.get("passed"),
                "score": candidate_score,
                "failure_labels": sorted(candidate_failures),
            },
            "decision": (
                "recommend_publish"
                if improved
                else "non_regression_only"
                if passed
                else "reject"
            ),
        }
