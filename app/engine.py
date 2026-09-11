from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .schemas import Recipe, RunStatus, SemanticPlan, SourceSpan, SummaryResult, ToolProposal


TOOL_SCHEMAS: dict[str, dict[str, type]] = {
    "create_note_draft": {"title": str, "body": str},
    "create_reminder_draft": {"title": str, "due_date": str, "hour": int, "meridiem": str},
    "add_list_items": {"list_name": str, "items": list},
    "revise_draft": {"draft_id": str, "patch": dict},
    "cancel_draft": {"draft_id": str},
    "request_clarification": {"question": str, "missing_fields": list},
}


def span_for(text: str, fragment: str | None = None) -> SourceSpan:
    fragment = fragment or text
    start = text.find(fragment)
    if start < 0:
        start, fragment = 0, text[: min(len(text), 300)]
    return SourceSpan(start=start, end=start + len(fragment), text=fragment)


def recipe_hash(recipe: Recipe) -> str:
    body = recipe.model_dump(mode="json")
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


ARABIC_HOURS = {
    "واحدة": 1, "واحد": 1, "اثنين": 2, "اثنينه": 2, "ثلاثة": 3, "اربعة": 4,
    "أربعة": 4, "خمسة": 5, "ستة": 6, "سبعة": 7, "ثمانية": 8, "تسعة": 9,
    "عشرة": 10, "احدعش": 11, "إحدعش": 11, "اثنعش": 12,
}


def _all_hours(text: str) -> list[int]:
    candidates: list[tuple[int, int]] = []
    for word, hour in ARABIC_HOURS.items():
        for match in re.finditer(re.escape(word), text, flags=re.I):
            candidates.append((match.start(), hour))
    for match in re.finditer(r"(?:الساعة\s*)?([1-9]|1[0-2])\b", text):
        candidates.append((match.start(), int(match.group(1))))
    return [hour for _, hour in sorted(candidates)]


def _meridiem(text: str) -> str | None:
    normalized = text.lower()
    if any(word in normalized for word in ("صباح", "am", "a.m")):
        return "AM"
    if any(word in normalized for word in ("مساء", "ليل", "pm", "p.m")):
        return "PM"
    return None


def _reference_date(reference_timestamp: str, text: str) -> str | None:
    try:
        reference = datetime.fromisoformat(reference_timestamp)
    except ValueError:
        return None
    if any(word in text.lower() for word in ("بكرة", "بكرا", "غدا", "tomorrow")):
        return (reference + timedelta(days=1)).date().isoformat()
    return None


def _split_items(raw: str) -> list[str]:
    raw = re.sub(r"\s+و", ",", raw, flags=re.I)
    raw = re.sub(r"\s+and\s+", ",", raw, flags=re.I)
    raw = raw.replace("،", ",")
    candidates = [part.strip(" .،,") for part in raw.split(",")]
    return [part for part in candidates if part and len(part) <= 80]


class DemoRules:
    """Deterministic reference path. It is deliberately not presented as ML inference."""

    evidence_type = "DEMO_RULES"

    def summarize(self, text: str) -> SummaryResult:
        compact = re.sub(r"\s+", " ", text).strip()
        excerpt = compact[: min(len(compact), 240)]
        return SummaryResult(
            status=RunStatus.READY,
            summary=f"معاينة استخراجية تجريبية: {excerpt}",
            supporting_spans=[span_for(text, excerpt)] if excerpt else [],
            evidence_type=self.evidence_type,
        )

    def actionize(self, text: str, reference_timestamp: str) -> SemanticPlan:
        lowered = text.lower()
        correction_words = []
        if re.search(r"(?:لا[،,]?\s*(?:خليها|خلها)|بدل|مو)", lowered):
            correction_words.append("A correction marker was preserved; the final explicit value is used.")

        if any(phrase in lowered for phrase in ("لا تسوي تذكير", "بدون تذكير", "ما أبي أي تذكير", "ما ابي اي تذكير", "don't remind")):
            return SemanticPlan(
                status=RunStatus.NO_ACTION, intent="SUMMARY_ONLY", corrections=correction_words,
                supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
            )

        if any(word in lowered for word in ("قائمة", "المقاضي", "shopping list", "grocery")) and any(
            word in lowered for word in ("حط", "اضف", "أضف", "ضيف", "add", "put")
        ):
            before_list = re.split(r"(?:في\s+)?(?:قائمة|المقاضي|shopping list)", text, maxsplit=1, flags=re.I)[0]
            before_list = re.sub(r"^.*?(?:حط|اضف|أضف|ضيف|add|put)\s+", "", before_list, flags=re.I).strip()
            before_list = re.sub(r"(?:\s+(?:في|in))?\s*$", "", before_list, flags=re.I)
            items = _split_items(before_list)
            list_name = "المقاضي" if "المقاضي" in lowered else "shopping"
            return SemanticPlan(
                status=RunStatus.READY, intent="ADD_LIST_ITEMS",
                entities={"list_name": list_name, "items": items}, corrections=correction_words,
                supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
            )

        if any(word in lowered for word in ("ذكرني", "ذكّرني", "تذكير", "remind")):
            hours = _all_hours(text)
            hour = hours[-1] if hours else None
            meridiem = _meridiem(text)
            due_date = _reference_date(reference_timestamp, text)
            missing = []
            if not due_date:
                missing.append("date")
            if hour is None:
                missing.append("hour")
            if hour is not None and not meridiem:
                missing.append("AM/PM")
            return SemanticPlan(
                status=RunStatus.NEEDS_CLARIFICATION if missing else RunStatus.READY,
                intent="CREATE_REMINDER_DRAFT",
                entities={"title": "تذكير", "due_date": due_date, "hour": hour, "meridiem": meridiem},
                corrections=correction_words, missing_fields=missing,
                supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
            )

        if any(word in lowered for word in ("ارسل", "أرسل", "send it", "send message")):
            return SemanticPlan(
                status=RunStatus.UNSUPPORTED, intent="EXTERNAL_SEND_NOT_AVAILABLE", corrections=correction_words,
                supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
            )

        if any(word in lowered for word in ("اكتب رسالة", "رسالة ل", "write a message", "message ")):
            recipient = None
            recipient_match = re.search(r"(?:رسالة\s+ل|message\s+to\s+|to\s+)([\w\u0621-\u064A]+)", text, flags=re.I)
            if recipient_match:
                recipient = recipient_match.group(1)
            body_match = re.search(r"(?:إني|اني|that\s+i[' ]?ll|that i will)\s+(.+?)(?:[.،]|$)", text, flags=re.I)
            body = body_match.group(0).strip() if body_match else text.strip()
            title = f"مسودة رسالة{(' لـ' + recipient) if recipient else ''}"
            return SemanticPlan(
                status=RunStatus.READY, intent="CREATE_NOTE_DRAFT",
                entities={"title": title, "body": body, "send": False}, corrections=correction_words,
                supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
            )

        if any(word in lowered for word in ("ملاحظة", "note", "اكتب")):
            cleaned = re.sub(r"^.*?(?:اكتب|write)\s+(?:ملاحظة|note)?\s*", "", text, flags=re.I).strip()
            return SemanticPlan(
                status=RunStatus.READY, intent="CREATE_NOTE_DRAFT",
                entities={"title": "ملاحظة", "body": cleaned or text.strip()}, corrections=correction_words,
                supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
            )

        return SemanticPlan(
            status=RunStatus.NO_ACTION, intent="NO_ACTION", corrections=correction_words,
            supporting_spans=[span_for(text)], evidence_type=self.evidence_type,
        )

    def function_call(self, text: str, plan: SemanticPlan, source_revision: int) -> ToolProposal:
        proposal_id = str(uuid.uuid4())
        span = plan.supporting_spans
        if plan.status == RunStatus.NEEDS_CLARIFICATION:
            question = "Please clarify: " + ", ".join(plan.missing_fields)
            return ToolProposal(
                id=proposal_id, status=RunStatus.NEEDS_CLARIFICATION, tool_name="request_clarification",
                arguments={"question": question, "missing_fields": plan.missing_fields}, source_revision=source_revision,
                supporting_spans=span, tool_mode="JSON_EMULATION", evidence_type=self.evidence_type,
                explanation="No date, time, or AM/PM value was invented.",
            )
        if plan.status == RunStatus.UNSUPPORTED:
            return ToolProposal(
                id=proposal_id, status=RunStatus.UNSUPPORTED, source_revision=source_revision,
                supporting_spans=span, tool_mode="JSON_EMULATION", evidence_type=self.evidence_type,
                explanation="The local sandbox never sends external messages.",
            )
        if plan.intent == "ADD_LIST_ITEMS":
            return ToolProposal(
                id=proposal_id, status=RunStatus.READY, tool_name="add_list_items",
                arguments={"list_name": plan.entities["list_name"], "items": plan.entities["items"]},
                source_revision=source_revision, supporting_spans=span, tool_mode="JSON_EMULATION", evidence_type=self.evidence_type,
            )
        if plan.intent == "CREATE_REMINDER_DRAFT":
            args = {key: plan.entities[key] for key in ("title", "due_date", "hour", "meridiem")}
            return ToolProposal(
                id=proposal_id, status=RunStatus.READY, tool_name="create_reminder_draft", arguments=args,
                source_revision=source_revision, supporting_spans=span, tool_mode="JSON_EMULATION", evidence_type=self.evidence_type,
            )
        if plan.intent == "CREATE_NOTE_DRAFT":
            return ToolProposal(
                id=proposal_id, status=RunStatus.READY, tool_name="create_note_draft",
                arguments={"title": plan.entities["title"], "body": plan.entities["body"]},
                source_revision=source_revision, supporting_spans=span, tool_mode="JSON_EMULATION", evidence_type=self.evidence_type,
                explanation="Draft only: this tool has no send capability.",
            )
        return ToolProposal(
            id=proposal_id, status=RunStatus.NO_ACTION, source_revision=source_revision, supporting_spans=span,
            tool_mode="JSON_EMULATION", evidence_type=self.evidence_type,
            explanation="No safe sandbox action was requested.",
        )

    def direct_function_call(self, text: str, reference_timestamp: str, source_revision: int) -> ToolProposal:
        # Direct route intentionally records one function-call stage, not a hidden actionize invocation.
        return self.function_call(text, self.actionize(text, reference_timestamp), source_revision)


def validate_tool_proposal(proposal: ToolProposal) -> None:
    if proposal.status not in {RunStatus.READY, RunStatus.NEEDS_CLARIFICATION}:
        return
    if not proposal.tool_name or proposal.tool_name not in TOOL_SCHEMAS:
        raise ValueError("UNKNOWN_TOOL")
    expected = TOOL_SCHEMAS[proposal.tool_name]
    actual = proposal.arguments
    if set(actual) != set(expected):
        raise ValueError("TOOL_ARGUMENTS_MUST_MATCH_SCHEMA_EXACTLY")
    for key, expected_type in expected.items():
        if not isinstance(actual[key], expected_type):
            raise ValueError(f"INVALID_TOOL_ARGUMENT_TYPE:{key}")
    if proposal.tool_name == "add_list_items" and (not actual["items"] or not all(isinstance(x, str) and x for x in actual["items"])):
        raise ValueError("INVALID_LIST_ITEMS")
    if proposal.tool_name == "create_reminder_draft" and actual["meridiem"] not in {"AM", "PM"}:
        raise ValueError("INVALID_MERIDIEM")


def apply_to_sandbox(state: dict[str, Any], proposal: ToolProposal) -> tuple[dict[str, Any], str]:
    validate_tool_proposal(proposal)
    if proposal.status != RunStatus.READY:
        raise ValueError("PROPOSAL_NOT_READY")
    applied = state.setdefault("applied_proposal_ids", [])
    if proposal.id in applied:
        return state, "ALREADY_APPLIED"
    args = proposal.arguments
    if proposal.tool_name == "create_note_draft":
        state.setdefault("notes", []).append({"proposal_id": proposal.id, **args, "status": "DRAFT"})
    elif proposal.tool_name == "create_reminder_draft":
        state.setdefault("reminders", []).append({"proposal_id": proposal.id, **args, "status": "DRAFT"})
    elif proposal.tool_name == "add_list_items":
        state.setdefault("lists", {}).setdefault(args["list_name"], []).extend(args["items"])
    elif proposal.tool_name in {"revise_draft", "cancel_draft"}:
        raise ValueError("DRAFT_IDENTIFIERS_NOT_IMPLEMENTED_IN_THIS_SLICE")
    else:
        raise ValueError("PROPOSAL_NOT_APPLICABLE")
    applied.append(proposal.id)
    return state, "APPLIED"


@dataclass
class EngineResult:
    outputs: dict[str, Any]
    invocation_counts: dict[str, int]
    stage_durations_ms: dict[str, float]


class Engine:
    def __init__(self, ollama_adapter: Any | None = None, local_text_adapter: Any | None = None) -> None:
        self.demo = DemoRules()
        self.ollama_adapter = ollama_adapter
        self.local_text_adapter = local_text_adapter
        self._runtime_metrics: list[dict[str, Any]] = []

    def validate_recipe(self, recipe: Recipe) -> None:
        required = {"function_call"}
        if recipe.summary_branch:
            required.add("summarize")
        if recipe.action_mode == "TWO_STAGE":
            required.add("actionize")
        missing = required - set(recipe.bindings)
        if missing:
            raise ValueError(f"RECIPE_MISSING_BINDINGS:{','.join(sorted(missing))}")
        for role, binding in recipe.bindings.items():
            if binding.role.value != role:
                raise ValueError(f"ROLE_BINDING_MISMATCH:{role}")
            if not binding.available:
                raise ValueError(f"UNAVAILABLE_BINDING:{role}:{binding.unavailable_reason or 'UNKNOWN'}")
            if binding.execution_mode.value == "DEMO_RULES" and binding.provider != "demo_rules":
                raise ValueError(f"INVALID_DEMO_BINDING:{role}")
            if binding.execution_mode.value == "LOCAL":
                valid_local_text = binding.provider in {"ollama_local", "llama_cpp_local"} and binding.capability_provenance.value == "VERIFIED_LOCAL"
                valid_local_speech = role == "transcribe" and binding.provider in {"faster_whisper_local", "transformers_whisper_local"} and binding.capability_provenance.value == "VERIFIED_LOCAL"
                if not (valid_local_text or valid_local_speech):
                    raise ValueError(f"NO_VERIFIED_LOCAL_BINDING:{role}")
            elif binding.execution_mode.value != "DEMO_RULES":
                raise ValueError(f"NO_ELIGIBLE_BINDING:{role}")
        if recipe.bindings["function_call"].execution_mode.value == "DEMO_RULES" and recipe.bindings["function_call"].tool_mode != "JSON_EMULATION":
            raise ValueError("DEMO_RULES_ONLY_SUPPORTS_JSON_EMULATION")

    def _local_json(self, binding: Any, prompt: str) -> dict[str, Any]:
        adapter = self.ollama_adapter if binding.provider == "ollama_local" else self.local_text_adapter if binding.provider == "llama_cpp_local" else None
        if not adapter:
            raise ValueError("UNAVAILABLE_LOCAL_MODEL: local adapter was not configured")
        raw = adapter.invoke(
            binding,
            [{"role": "system", "content": "Return only schema-valid JSON. Do not include reasoning."}, {"role": "user", "content": prompt}],
            json_schema={"type": "object"},
        )
        try:
            payload = self._parse_json(raw["content"])
            if raw.get("runtime_metrics"):
                self._runtime_metrics.append({"role": binding.role.value, **raw["runtime_metrics"]})
            return payload
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("INVALID_OUTPUT: local model did not return JSON") from exc

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """Accept a JSON object with harmless surrounding whitespace only, or isolate one emitted after a chat-template marker."""
        if not isinstance(content, str):
            raise json.JSONDecodeError("content must be text", "", 0)
        start = content.find("{")
        if start < 0:
            raise json.JSONDecodeError("JSON object missing", content, 0)
        payload, _ = json.JSONDecoder().raw_decode(content[start:])
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("JSON object required", content, start)
        return payload

    def _summarize(self, binding: Any, text: str) -> SummaryResult:
        if binding.execution_mode.value == "DEMO_RULES":
            return self.demo.summarize(text)
        payload = self._local_json(binding, f"""Return one JSON object with keys status, summary, supporting_spans. Summarize the Arabic or English source faithfully. Do not invent actions. status must be READY. supporting_spans is an array of objects with start, end, text drawn from the source. Source: {text}""")
        payload["evidence_type"] = "REAL_LOCAL_MODEL"
        payload["calibrated_correctness"] = None
        return SummaryResult.model_validate(payload)

    def _actionize(self, binding: Any, text: str, reference_timestamp: str) -> SemanticPlan:
        if binding.execution_mode.value == "DEMO_RULES":
            return self.demo.actionize(text, reference_timestamp)
        payload = self._local_json(binding, f"""Return one JSON object with status, intent, entities, corrections, missing_fields, supporting_spans. Extract a safe semantic action plan only. Preserve explicit corrections and negation. If a request is ambiguous, set status NEEDS_CLARIFICATION and list missing fields. Never invent a clock time for a relative time such as after sunset. Reference timestamp: {reference_timestamp}. Timezone: Asia/Riyadh. Source: {text}""")
        payload["evidence_type"] = "REAL_LOCAL_MODEL"
        return SemanticPlan.model_validate(payload)

    def _function_call(self, binding: Any, text: str, plan: SemanticPlan | None, reference_timestamp: str, source_revision: int) -> ToolProposal:
        if binding.execution_mode.value == "DEMO_RULES":
            return self.demo.function_call(text, plan, source_revision) if plan else self.demo.direct_function_call(text, reference_timestamp, source_revision)
        adapter = self.ollama_adapter if binding.provider == "ollama_local" else self.local_text_adapter if binding.provider == "llama_cpp_local" else None
        if not adapter:
            raise ValueError("UNAVAILABLE_LOCAL_MODEL: local adapter was not configured")
        raw = adapter.invoke(
            binding,
            [{"role": "system", "content": "Return one JSON object only. Produce a safe typed local sandbox proposal; never send a message or perform an external action. Allowed tools: create_note_draft(title,body), create_reminder_draft(title,due_date,hour,meridiem), add_list_items(list_name,items), request_clarification(question,missing_fields). Object keys: status, tool_name, arguments. Use NEEDS_CLARIFICATION and request_clarification for unresolved references or relative times without a defined interpretation. Honour explicit negation and corrections."}, {"role": "user", "content": json.dumps({"source_text": text, "semantic_plan": plan.model_dump(mode="json") if plan else None, "reference_timestamp": reference_timestamp}, ensure_ascii=False)}],
            json_schema={"type": "object"},
            tools=[{"type": "function", "function": {"name": name, "description": "Local sandbox operation", "parameters": {"type": "object"}}} for name in TOOL_SCHEMAS],
        )
        try:
            if binding.tool_mode == "NATIVE" and raw.get("tool_calls"):
                call = raw["tool_calls"][0].get("function", raw["tool_calls"][0])
                payload = {"status": "READY", "tool_name": call["name"], "arguments": json.loads(call.get("arguments", "{}"))}
            else:
                payload = self._parse_json(raw["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("INVALID_OUTPUT: invalid local tool proposal") from exc
        payload.update({
            "id": str(uuid.uuid4()), "source_revision": source_revision, "supporting_spans": [span_for(text)],
            "tool_mode": binding.tool_mode, "evidence_type": "REAL_LOCAL_MODEL",
        })
        if raw.get("runtime_metrics"):
            self._runtime_metrics.append({"role": binding.role.value, **raw["runtime_metrics"]})
        return ToolProposal.model_validate(payload)

    def run(self, recipe: Recipe, text: str, reference_timestamp: str, source_revision: int = 1) -> EngineResult:
        self.validate_recipe(recipe)
        self._runtime_metrics = []
        stage_durations: dict[str, float] = {}
        calls: dict[str, int] = {}
        execution_evidence = sorted({binding.execution_mode.value for binding in recipe.bindings.values()})
        outputs: dict[str, Any] = {
            "recipe_id": recipe.id,
            "recipe_hash": recipe_hash(recipe),
            "evidence_type": "DEMO_RULES" if execution_evidence == ["DEMO_RULES"] else "REAL_LOCAL_MODEL",
            "actual_models": [
                {"role": role, "provider": binding.provider, "model_id": binding.model_id, "digest": binding.revision_or_digest,
                 "execution_mode": binding.execution_mode.value, "tool_mode": binding.tool_mode}
                for role, binding in recipe.bindings.items()
            ],
            "reference_timestamp": reference_timestamp,
            "timezone": "Asia/Riyadh",
            "calibrated_correctness": None,
            "native_confidence": None,
            "stale": False,
        }
        if recipe.summary_branch:
            started = time.perf_counter()
            summary = self._summarize(recipe.bindings["summarize"], text)
            stage_durations["summarize"] = (time.perf_counter() - started) * 1000
            calls["summarize"] = 1
            outputs["summary"] = summary.model_dump(mode="json")
        else:
            outputs["summary"] = None
        if recipe.action_mode == "TWO_STAGE":
            started = time.perf_counter()
            plan = self._actionize(recipe.bindings["actionize"], text, reference_timestamp)
            stage_durations["actionize"] = (time.perf_counter() - started) * 1000
            calls["actionize"] = 1
            outputs["semantic_plan"] = plan.model_dump(mode="json")
            started = time.perf_counter()
            proposal = self._function_call(recipe.bindings["function_call"], text, plan, reference_timestamp, source_revision)
        else:
            started = time.perf_counter()
            proposal = self._function_call(recipe.bindings["function_call"], text, None, reference_timestamp, source_revision)
            outputs["semantic_plan"] = None
        stage_durations["function_call"] = (time.perf_counter() - started) * 1000
        calls["function_call"] = 1
        validate_tool_proposal(proposal)
        outputs["proposal"] = proposal.model_dump(mode="json")
        outputs["stage_durations_ms"] = stage_durations
        outputs["actual_invocation_counts"] = calls
        outputs["resource_measurements"] = self._runtime_metrics
        return EngineResult(outputs=outputs, invocation_counts=calls, stage_durations_ms=stage_durations)
