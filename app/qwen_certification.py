"""Certification plan and runner for the first semantic/action GGUF.

The suite is deliberately runnable only against a server-discovered, verified
local binding.  Until then it returns an explicit waiting state and never
substitutes DEMO_RULES output for Qwen evidence.
"""

from __future__ import annotations

import time
import json
from typing import Any, Callable

from .schemas import RoleBinding


QWEN_CERTIFICATION_ROLES = ("summarize", "actionize", "function_call", "verify")

QWEN_CERTIFICATION_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "saudi_correction",
        "text": "ذكرني بكرة الساعة ثمانية، لا خلها تسعة",
        "focus": ["correction", "number"],
        "expected": {"final_hour": 9, "preserve_correction": True},
    },
    {
        "id": "saudi_negation",
        "text": "اكتب رسالة لخالد إني بتأخر بس لا ترسلها",
        "focus": ["negation", "draft_only", "no_external_send"],
        "expected": {"draft_only": True, "forbid_tool_names": ["send_message", "send_email"]},
    },
    {
        "id": "saudi_code_switching",
        "text": "حط milk وبيض وprotein bars في قائمة المقاضي",
        "focus": ["arabic_english_code_switching", "list_items"],
        "expected": {"items": ["milk", "بيض", "protein bars"]},
    },
    {
        "id": "saudi_summary_only",
        "text": "لا تسوي تذكير، بس لخص اللي قلته",
        "focus": ["summary_only", "no_action"],
        "expected": {"no_reminder": True},
    },
    {
        "id": "saudi_ambiguity",
        "text": "حطها في القائمة الثانية",
        "focus": ["unresolved_reference", "clarification"],
        "expected": {"clarification": True},
    },
    {
        "id": "saudi_revision",
        "text": "أنشئ مسودة تذكير بكرة الساعة ثمانية، خلها تسعة",
        "focus": ["draft_revision", "correction", "final_argument"],
        "expected": {"final_hour": 9, "revision": True},
    },
    {
        "id": "saudi_cancellation",
        "text": "ألغِ مسودة التذكير التي أنشأناها قبل قليل",
        "focus": ["draft_cancellation", "no_new_action"],
        "expected": {"cancellation": True},
    },
)


def _output_text(output: dict[str, Any]) -> str:
    parts = [output.get("content", ""), output.get("tool_name", ""), output.get("arguments", {}), output.get("tool_calls", [])]
    return json.dumps(parts, ensure_ascii=False, sort_keys=True).lower()


def evaluate_qwen_output(case: dict[str, Any], role: str, output: dict[str, Any]) -> dict[str, Any]:
    """Evaluate only explicit, case-local invariants; never infer a quality score."""
    rendered = _output_text(output)
    expected = case.get("expected", {})
    checks: list[dict[str, Any]] = []
    if expected.get("final_hour") is not None:
        passed = ("hour" in rendered and "9" in rendered) or "تسعة" in rendered or '"9"' in rendered
        checks.append({"name": "final_correction_preserved", "passed": passed})
    if expected.get("items"):
        checks.append({"name": "all_code_switch_items_preserved", "passed": all(item.lower() in rendered for item in expected["items"])})
    if expected.get("draft_only"):
        forbidden = expected.get("forbid_tool_names", [])
        checks.append({"name": "negation_preserves_draft_only", "passed": not any(name.lower() in rendered for name in forbidden) and ("draft" in rendered or "مسودة" in rendered)})
    if expected.get("no_reminder"):
        checks.append({"name": "summary_only_has_no_reminder", "passed": "create_reminder_draft" not in rendered and "reminder" not in rendered and "تذكير" not in rendered})
    if expected.get("clarification"):
        checks.append({"name": "ambiguous_reference_requests_clarification", "passed": "request_clarification" in rendered or "clarif" in rendered or "توضيح" in rendered or "استفس" in rendered})
    if expected.get("revision"):
        checks.append({"name": "revision_keeps_final_argument", "passed": ("revise_draft" in rendered or "revision" in rendered or "تعديل" in rendered) and ("تسعة" in rendered or '"hour": 9' in rendered or '"hour":9' in rendered)})
    if expected.get("cancellation"):
        checks.append({"name": "cancellation_is_explicit", "passed": "cancel_draft" in rendered or "cancel" in rendered or "إلغاء" in rendered or "الغاء" in rendered})
    if role == "summarize":
        checks.append({"name": "summary_content_present", "passed": bool(str(output.get("content", "")).strip())})
    if role in {"actionize", "function_call", "verify"}:
        checks.append({"name": "structured_output_present", "passed": bool(output.get("tool_calls") or output.get("arguments") or output.get("content"))})
    return {"passed": all(check["passed"] for check in checks), "checks": checks, "calibrated_correctness": None}


def qwen_certification_plan(binding: RoleBinding | None) -> dict[str, Any]:
    """Describe whether the actual Qwen binding is ready for certification."""
    if binding is None or not binding.available:
        return {
            "status": "WAITING_FOR_QWEN_ARTIFACT",
            "evidence_type": "NO_QWEN_EXECUTION",
            "roles": list(QWEN_CERTIFICATION_ROLES),
            "cases": [case["id"] for case in QWEN_CERTIFICATION_CASES],
            "binding": binding.model_dump(mode="json") if binding else None,
            "reason": "A verified local Qwen artifact and runtime binding are required before certification.",
        }
    return {
        "status": "READY_TO_CERTIFY",
        "evidence_type": "REAL_LOCAL_MODEL_PENDING_RUN",
        "roles": list(QWEN_CERTIFICATION_ROLES),
        "cases": [case["id"] for case in QWEN_CERTIFICATION_CASES],
        "binding": binding.model_dump(mode="json"),
    }


def run_qwen_certification(
    binding: RoleBinding | None,
    invoke: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    *,
    reference_timestamp: str = "2026-09-12T09:00:00+03:00",
) -> dict[str, Any]:
    """Run the matrix against the actual binding, retaining raw role evidence."""
    plan = qwen_certification_plan(binding)
    if plan["status"] != "READY_TO_CERTIFY" or invoke is None:
        return {**plan, "results": []}
    results: list[dict[str, Any]] = []
    for case in QWEN_CERTIFICATION_CASES:
        for role in QWEN_CERTIFICATION_ROLES:
            started = time.perf_counter()
            try:
                output = invoke(role, {**case, "reference_timestamp": reference_timestamp})
                results.append({"case_id": case["id"], "role": role, "status": "COMPLETED", "latency_ms": (time.perf_counter() - started) * 1000, "output": output})
            except Exception as exc:
                results.append({"case_id": case["id"], "role": role, "status": "FAILED", "latency_ms": (time.perf_counter() - started) * 1000, "error": f"{type(exc).__name__}:{str(exc)[:240]}"})
    for result in results:
        if result["status"] == "COMPLETED":
            case = next(case for case in QWEN_CERTIFICATION_CASES if case["id"] == result["case_id"])
            result["evaluation"] = evaluate_qwen_output(case, result["role"], result.get("output", {}))
    failed_roles = sorted({result["role"] for result in results if result["status"] != "COMPLETED" or not result.get("evaluation", {}).get("passed", False)})
    return {**plan, "status": "CAPABILITY_CERTIFIED" if not failed_roles and results else "ROLE_PROBE_FAILED", "evidence_type": "REAL_LOCAL_MODEL",
            "failed_roles": failed_roles, "results": results, "calibrated_correctness": None}


def qwen_route_experiment_plan() -> dict[str, Any]:
    """Stable recipes and scoring dimensions for the first Qwen route comparison."""
    return {
        "direct": ["transcribe", "function_call"],
        "staged": ["transcribe", "actionize", "function_call"],
        "summary_branch": {"source": "original_transcript", "branches": [["summarize"], ["actionize", "function_call"]]},
        "scores": ["correct_action", "correct_arguments", "invented_fields", "correction_preservation", "negation_preservation", "clarification", "latency", "failure_rate"],
        "evidence_rule": "Summary output is never the evidence source for function_call; calibrated_correctness remains null.",
    }
