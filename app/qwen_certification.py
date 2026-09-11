"""Certification plan and runner for the first semantic/action GGUF.

The suite is deliberately runnable only against a server-discovered, verified
local binding.  Until then it returns an explicit waiting state and never
substitutes DEMO_RULES output for Qwen evidence.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .schemas import RoleBinding


QWEN_CERTIFICATION_ROLES = ("summarize", "actionize", "function_call", "verify")

QWEN_CERTIFICATION_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "saudi_correction",
        "text": "ذكرني الساعة سبعة... لا، ثمانية مساءً.",
        "focus": ["correction", "number", "meridiem"],
    },
    {
        "id": "saudi_negation",
        "text": "جهّز لي رسالة لأحمد بس لا ترسلها.",
        "focus": ["negation", "draft_only", "no_external_send"],
    },
    {
        "id": "saudi_code_switching",
        "text": "حط milk وبيض وprotein bars في المقاضي.",
        "focus": ["arabic_english_code_switching", "list_items"],
    },
    {
        "id": "saudi_summary_only",
        "text": "لا تسوي تذكير، بس لخّص اللي قلته عن اجتماع الفريق.",
        "focus": ["summary_only", "no_action"],
    },
    {
        "id": "saudi_ambiguity",
        "text": "أضفها للقائمة الثانية.",
        "focus": ["unresolved_reference", "clarification"],
    },
    {
        "id": "saudi_revision",
        "text": "أنشئ مسودة تذكير غداً الساعة ثمانية، وصححها إلى تسعة مساءً.",
        "focus": ["draft_revision", "correction", "final_argument"],
    },
    {
        "id": "saudi_cancellation",
        "text": "ألغِ مسودة التذكير التي أنشأناها قبل قليل.",
        "focus": ["draft_cancellation", "no_new_action"],
    },
)


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
    return {**plan, "status": "COMPLETED", "evidence_type": "REAL_LOCAL_MODEL", "results": results}
