"""Scenario prompts for the human-reviewed seed recording queue.

These are prompts, not labels or gold transcripts.  The speaker is encouraged
to phrase each case naturally and the reference is entered only after review.
"""

SEED_SCENARIOS = [
    {"id": "correction_time", "intent": "reminder with spoken correction", "example": "ذكرني الساعة سبعة... لا، ثمانية.", "facts": ["final time is eight", "correction overrides seven"]},
    {"id": "negated_send", "intent": "draft a message without sending", "example": "جهّز لي رسالة لأحمد بس لا ترسلها.", "facts": ["draft only", "never send"]},
    {"id": "code_switch_list", "intent": "add mixed-language shopping items", "example": "حط milk وبيض وprotein bars في المقاضي.", "facts": ["milk", "بيض", "protein bars"]},
    {"id": "relative_evening", "intent": "relative-time reminder", "example": "ذكرني بكرة بعد المغرب.", "facts": ["tomorrow", "after maghrib", "no invented clock time"]},
    {"id": "ambiguous_list", "intent": "ambiguous list reference", "example": "أضفها للقائمة الثانية.", "facts": ["clarification required without context"]},
    {"id": "spoken_three_half", "intent": "note with decimal", "example": "سجل ثلاثة ونص في الملاحظة.", "facts": ["3.5"]},
    {"id": "spoken_twenty_five", "intent": "quantity with spoken number", "example": "أضف خمسة وعشرين حبة.", "facts": ["25"]},
    {"id": "decimal_english", "intent": "record an English decimal", "example": "سجل 3.5 في الملاحظة.", "facts": ["3.5"]},
    {"id": "phone_like_digits", "intent": "preserve identifier-like digits", "example": "دوّن 0501234567 بدون تعديل.", "facts": ["digit sequence preserved"]},
    {"id": "name_arabic", "intent": "message draft with Arabic name", "example": "اكتب لمحمد إني بتأخر.", "facts": ["recipient محمد", "draft only"]},
    {"id": "name_english", "intent": "message draft with English name", "example": "جهز رسالة لـ Sarah، بوصّل بعد عشر دقايق.", "facts": ["recipient Sarah", "draft only"]},
    {"id": "list_three_items", "intent": "add three Arabic items", "example": "حط خبز وحليب وطماطم في المقاضي.", "facts": ["three list items"]},
    {"id": "remove_list_item", "intent": "remove an item from a list", "example": "شِل البيض من قائمة المقاضي.", "facts": ["remove eggs"]},
    {"id": "reminder_morning", "intent": "morning reminder", "example": "ذكرني الساعة تسعة الصباح أرسل الفاتورة.", "facts": ["nine AM", "send invoice"]},
    {"id": "reminder_evening", "intent": "evening reminder", "example": "ذكرني الساعة ثمانية الليل أراجع العقد.", "facts": ["eight PM", "review contract"]},
    {"id": "date_explicit", "intent": "dated reminder", "example": "ذكرني يوم 15 أكتوبر أراجع التأمين.", "facts": ["15 October", "review insurance"]},
    {"id": "hesitation", "intent": "note after hesitation", "example": "آه... اكتب ملاحظة إن الاجتماع اتأجل.", "facts": ["note", "meeting postponed"]},
    {"id": "summary_only", "intent": "summary without action", "example": "لا تسوي تذكير، بس لخص الكلام.", "facts": ["summary only", "no tool"]},
    {"id": "action_mention_not_request", "intent": "mention an action without requesting it", "example": "كنت أفكر أضيفها للقائمة، بس خلها الآن.", "facts": ["no list mutation"]},
    {"id": "clarify_recipient", "intent": "message missing recipient", "example": "اكتب له إني وصلت.", "facts": ["clarification required"]},
    {"id": "clarify_time", "intent": "reminder missing time", "example": "ذكرني أراجع العرض.", "facts": ["clarification required"]},
    {"id": "mixed_command", "intent": "Arabic-English reminder", "example": "remind me بكرة أراجع the budget.", "facts": ["code switch preserved"]},
    {"id": "mixed_note", "intent": "Arabic-English note", "example": "دوّن إن الـ deployment صار successful.", "facts": ["note", "deployment successful"]},
    {"id": "negative_list", "intent": "do not add item", "example": "لا تضيف السكر للمقاضي.", "facts": ["no add action"]},
    {"id": "correction_item", "intent": "correct a list item", "example": "حط شاي... لا، قهوة في المقاضي.", "facts": ["coffee only"]},
    {"id": "relative_noon", "intent": "relative date and period", "example": "ذكرني بعد يومين الظهر.", "facts": ["two days", "no invented minute"]},
    {"id": "longer_context", "intent": "note with conversational context", "example": "بعد مكالمة اليوم، سجل ملاحظة أن العميل بيرسل العقد بكرة.", "facts": ["note", "client sends contract tomorrow"]},
    {"id": "background_noise", "intent": "short reminder in noisy setting", "example": "ذكرني آخذ الدواء الساعة ستة.", "facts": ["six o'clock", "medication"]},
    {"id": "english_numbers", "intent": "English number embedded in Arabic", "example": "أضف twenty-five قطعة للقائمة.", "facts": ["25"]},
    {"id": "not_a_request", "intent": "statement only", "example": "أنا عادة أراجع المهام بعد المغرب.", "facts": ["no action"]},
]


def _expected_outcome(intent: str) -> str:
    lowered = intent.lower()
    if "clarif" in lowered or "ambiguous" in lowered or "missing" in lowered:
        return "Ask for clarification before taking action."
    if "summary" in lowered:
        return "Summary only; no sandbox action."
    if "remove" in lowered:
        return "Remove only the explicitly named list item."
    if "negative" in lowered or "not a request" in lowered or "mention" in lowered:
        return "No action; preserve the statement or negation."
    if "message" in lowered or "draft" in lowered:
        return "Create a local draft only; never send externally."
    if "reminder" in lowered:
        return "Create a reminder draft only when all required fields are known."
    if "list" in lowered:
        return "Apply the explicitly requested list operation."
    if "note" in lowered or "record" in lowered:
        return "Create a local note draft preserving the stated facts."
    return "Preserve the stated facts and avoid unsupported action."


for _scenario in SEED_SCENARIOS:
    _scenario["semantic_facts"] = list(_scenario["facts"])
    _scenario["expected_broad_outcome"] = _expected_outcome(_scenario["intent"])
    _scenario["clarification_may_be_required"] = any(
        marker in _scenario["intent"].lower()
        for marker in ("clarif", "ambiguous", "missing", "relative", "time")
    )
    _scenario["example_is_optional"] = True
