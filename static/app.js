(() => {
  const state = { catalog: [], recipes: [], currentRecord: null, planned: null, tournamentId: null, locale: "ar", recordingId: null, recorder: null, chunks: [], stageCapabilities: [], scenarios: [] };
  const $ = (id) => document.getElementById(id);
  const roles = { transcribe: "bindingTranscribe", summarize: "bindingSummarize", actionize: "bindingActionize", function_call: "bindingFunction" };
  const UI_COPY = {
    status: {
      ZERO_SPEND_LOCAL: ["محليًا دون تكلفة", "Local · zero spend"],
      LOCAL_MODEL_AVAILABLE: ["نموذج محلي متاح", "Local model available"],
      LOCAL_MODEL_BLOCKED: ["النموذج المحلي غير متاح", "Local model blocked"],
      DEMO_RULES: ["قواعد تجريبية", "Demo rules"],
      AUTHORED_SMOKE_FIXTURE: ["اختبار حدود مُعدّ", "Authored boundary test"],
      SEED_HUMAN_EVAL: ["تقييم بشري أولي", "Seed human evaluation"],
      RUNNING: ["جارٍ التنفيذ", "Running"],
      COMPLETED: ["اكتمل", "Completed"],
      CANCELLED: ["أُلغي", "Cancelled"],
      CANCEL_REQUESTED: ["طُلب الإلغاء", "Cancellation requested"],
      DELETED: ["حُذف", "Deleted"],
    },
    outcome: {
      READY_TO_START: ["جاهز للبدء", "Ready to start"],
      AWAITING_EXPLICIT_START: ["بانتظار بدء صريح", "Awaiting explicit start"],
      NO_COMPARABLE_HUMAN_EVIDENCE: ["لا توجد أدلة بشرية قابلة للمقارنة", "No comparable human evidence"],
      INSUFFICIENT_HUMAN_EVIDENCE: ["الأدلة البشرية غير كافية", "Insufficient human evidence"],
      MONETARY_TIE: ["تعادل في التكلفة المالية", "Monetary cost tie"],
      MANUAL: ["اختيار يدوي", "Manual selection"],
      RECOMMENDED: ["موصى به ضمن الأدلة المتاحة", "Recommended within available evidence"],
      TIE: ["تعادل", "Tie"],
      NO_ELIGIBLE_ROUTE: ["لا يوجد مسار مؤهل", "No eligible route"],
      NO_HUMAN_SEED_CASES: ["لا توجد حالات بشرية أولية", "No human seed cases"],
      CALL_CAP_EXCEEDED: ["تجاوز حد الاستدعاءات", "Call cap exceeded"],
      NO_ROUTE_MEETS_FLOOR: ["لا يحقق أي مسار الحد المطلوب", "No route meets the floor"],
      NO_ELIGIBLE_CANDIDATE: ["لا يوجد مرشح مؤهل", "No eligible candidate"],
    },
    state: {
      READY: ["جاهز", "Ready"],
      FAILED: ["فشل", "Failed"],
      MODEL_FAILURE: ["فشل النموذج", "Model failure"],
      UNAVAILABLE_LOCAL_MODEL: ["النموذج المحلي غير متاح", "Local model unavailable"],
      NOT_INSTALLED: ["غير مثبت", "Not installed"],
      ARTIFACT_PRESENT: ["الملف موجود", "Artifact present"],
      INTEGRITY_VERIFIED: ["تم التحقق من سلامة الملف", "Integrity verified"],
      RUNTIME_PENDING: ["وقت التشغيل بانتظار التحقق", "Runtime pending"],
      RUNTIME_LOAD_VERIFIED: ["تم التحقق من تحميل وقت التشغيل", "Runtime load verified"],
      CAPABILITY_PENDING: ["القدرة بانتظار التحقق", "Capability pending"],
      CAPABILITY_CERTIFIED: ["تم اعتماد القدرة", "Capability certified"],
    },
    stage: {
      Transcript: ["التفريغ", "Transcript"],
      Summary: ["الملخص", "Summary"],
      "Semantic plan": ["الخطة الدلالية", "Semantic plan"],
      "Function proposal": ["اقتراح الدالة", "Function proposal"],
      "Stage-route evidence": ["دليل مسار المراحل", "Stage-route evidence"],
    },
    stageKey: { vad: ["كشف النشاط الصوتي", "VAD"], turn_detection: ["كشف نهاية الدور", "Turn detection"], diarization: ["تمييز المتحدثين", "Diarization"], transcribe: ["تفريغ الصوت", "Transcribe"], summarize: ["تلخيص", "Summarize"], actionize: ["فهم الإجراء", "Actionize"], function_call: ["اقتراح الدالة", "Function call"], verify: ["تحقق", "Verify"], synthesize: ["تحويل النص إلى صوت", "Synthesize"] },
    mode: { Cost: ["التكلفة", "Cost"], Speed: ["السرعة", "Speed"], Performance: ["الأداء", "Performance"], Manual: ["يدوي", "Manual"] },
    evidence: { REAL_LOCAL_MODEL: ["نموذج محلي حقيقي", "Real local model"], DEMO_RULES: ["قواعد تجريبية", "Demo rules"], HUMAN_REVIEWED: ["مُراجع بشريًا", "Human reviewed"], AUTHORED_SMOKE_FIXTURE: ["اختبار حدود مُعدّ", "Authored boundary test"], UNREVIEWED_LOCAL_RECORDING: ["تسجيل محلي غير مُراجع", "Unreviewed local recording"] },
    execution: { LOCAL: ["محلي", "Local"], DEMO_RULES: ["قواعد تجريبية", "Demo rules"] },
    tool: { NATIVE_TOOL_CALL: ["استدعاء أدوات أصلي", "Native tool call"], STRUCTURED_TOOL_EMULATION: ["محاكاة أدوات منظمة", "Structured tool emulation"] },
    review: { RECORDED: ["مسجل", "Recorded"], MODEL_TRANSCRIBED: ["فُرّغ بالنموذج", "Model transcribed"], HUMAN_TRANSCRIPT_REVIEWED: ["رُوجع النص بشريًا", "Human transcript reviewed"], SEMANTIC_REFERENCE_REVIEWED: ["رُوجع المرجع الدلالي", "Semantic reference reviewed"] },
    labelState: { CANDIDATE: ["مرشح", "Candidate"], SILVER: ["مراجعة أولية", "Silver"], GOLD: ["مرجع ذهبي", "Gold"], REJECTED: ["مرفوض", "Rejected"] },
  };
  const SCENARIO_COPY = {
    correction_time: ["تذكير مع تصحيح شفهي", ["الوقت النهائي الثامنة", "التصحيح يتغلب على السابعة"]],
    negated_send: ["مسودة رسالة دون إرسال", ["مسودة فقط، لا إرسال"]],
    code_switch_list: ["إضافة مقاضي بلغات مختلطة", ["milk، بيض، protein bars"]],
    relative_evening: ["تذكير بوقت نسبي", ["غدًا، بعد المغرب، دون اختراع وقت محدد"]],
    ambiguous_list: ["مرجع غامض في القائمة", ["يلزم التوضيح دون سياق"]],
    spoken_three_half: ["ملاحظة تتضمن رقمًا عشريًا", ["3.5"]],
    spoken_twenty_five: ["كمية برقم منطوق", ["25"]],
    decimal_english: ["تسجيل رقم عشري بالإنجليزية", ["3.5"]],
    phone_like_digits: ["الحفاظ على أرقام تشبه المعرّف", ["تسلسل الأرقام محفوظ"]],
    name_arabic: ["مسودة رسالة باسم عربي", ["المستلم محمد، مسودة فقط"]],
    name_english: ["مسودة رسالة باسم إنجليزي", ["المستلم Sarah، مسودة فقط"]],
    list_three_items: ["إضافة ثلاثة أصناف عربية", ["ثلاثة أصناف في القائمة"]],
    remove_list_item: ["إزالة صنف من قائمة", ["إزالة البيض"]],
    reminder_morning: ["تذكير صباحي", ["التاسعة صباحًا، إرسال الفاتورة"]],
    reminder_evening: ["تذكير مسائي", ["الثامنة مساءً، مراجعة العقد"]],
    date_explicit: ["تذكير بتاريخ محدد", ["15 أكتوبر، مراجعة التأمين"]],
    hesitation: ["ملاحظة بعد تردد", ["ملاحظة، تأجيل الاجتماع"]],
    summary_only: ["تلخيص دون إجراء", ["تلخيص فقط، لا أداة"]],
    action_mention_not_request: ["ذكر إجراء دون طلب تنفيذه", ["لا تعديل على القائمة"]],
    clarify_recipient: ["رسالة بلا مستلم", ["يلزم التوضيح"]],
    clarify_time: ["تذكير بلا وقت", ["يلزم التوضيح"]],
    mixed_command: ["تذكير بالعربية والإنجليزية", ["المزج اللغوي محفوظ"]],
    mixed_note: ["ملاحظة بالعربية والإنجليزية", ["ملاحظة، نجاح deployment"]],
    negative_list: ["عدم إضافة صنف", ["لا إجراء إضافة"]],
    correction_item: ["تصحيح صنف في القائمة", ["القهوة فقط"]],
    relative_noon: ["تاريخ وفترة نسبيان", ["يومان، دون اختراع دقيقة"]],
    longer_context: ["ملاحظة بسياق محادثة", ["ملاحظة، العميل يرسل العقد غدًا"]],
    background_noise: ["تذكير قصير في بيئة صاخبة", ["السادسة، الدواء"]],
    english_numbers: ["رقم إنجليزي داخل العربية", ["25"]],
    not_a_request: ["عبارة بلا إجراء", ["لا إجراء"]],
  };
  const OUTCOME_COPY = {
    "Create a reminder draft only when all required fields are known.": "إنشاء مسودة تذكير فقط عند معرفة كل الحقول المطلوبة.",
    "Create a local draft only; never send externally.": "إنشاء مسودة محلية فقط؛ لا إرسال خارجي.",
    "Preserve the stated facts and avoid unsupported action.": "الحفاظ على الوقائع المذكورة وتجنب إجراء غير مدعوم.",
    "Ask for clarification before taking action.": "طلب التوضيح قبل اتخاذ الإجراء.",
    "Create a local note draft preserving the stated facts.": "إنشاء مسودة ملاحظة محلية مع الحفاظ على الوقائع المذكورة.",
    "Remove only the explicitly named list item.": "إزالة صنف القائمة المذكور صراحة فقط.",
    "Summary only; no sandbox action.": "تلخيص فقط؛ لا إجراء في الصندوق المحلي.",
    "No action; preserve the statement or negation.": "لا إجراء؛ الحفاظ على العبارة أو النفي.",
    "Apply the explicitly requested list operation.": "تنفيذ عملية القائمة المطلوبة صراحة.",
  };

  async function api(path, options = {}) {
    const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
    const response = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = (await response.json()).detail || detail; } catch (_) { /* plain response */ }
      throw new Error(detail);
    }
    const type = response.headers.get("content-type") || "";
    return type.includes("application/json") ? response.json() : response.text();
  }

  function copy(code, group = "status") {
    const entry = UI_COPY[group]?.[code];
    return entry ? entry[state.locale === "ar" ? 0 : 1] : code;
  }

  function friendlyError(message) {
    const errors = {
      "No eligible local binding for every required stage.": "لا يوجد نموذج محلي متحقق منه لكل مرحلة مطلوبة.",
      "Record or upload an audio clip in Workbench first.": "سجّل مقطع صوتي أو ارفعه من مساحة العمل أولًا.",
      "Expected arguments and critical spans must be valid JSON.": "يجب أن تكون الوسائط والمقاطع الحرجة بصيغة JSON صحيحة.",
      "Could not read audio duration.": "تعذّر قراءة مدة الملف الصوتي.",
    };
    return state.locale === "ar" ? (errors[message] || message) : message;
  }

  function toast(message) {
    const node = $("toast"); node.textContent = friendlyError(String(message)); node.classList.add("show");
    window.setTimeout(() => node.classList.remove("show"), 3600);
  }

  function pretty(value) { return JSON.stringify(value, null, 2); }
  function label(ar, en) { return state.locale === "ar" ? ar : en; }

  function setLocale(locale) {
    state.locale = locale;
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    document.querySelectorAll("[data-ar][data-en]").forEach((node) => { node.textContent = node.dataset[locale]; });
    document.querySelectorAll("[data-ar-placeholder][data-en-placeholder]").forEach((node) => { node.placeholder = node.dataset[`${locale}Placeholder`]; });
    document.querySelectorAll("[data-ar-label][data-en-label]").forEach((node) => { node.setAttribute("aria-label", node.dataset[`${locale}Label`]); });
    document.querySelectorAll("#recipeSelect option").forEach((node) => { const recipe = state.recipes.find((entry) => entry.id === node.value); if (recipe) node.textContent = localizedRecipeName(recipe.name); });
    $("localeToggle").textContent = locale === "ar" ? "English" : "العربية";
    document.querySelectorAll("[data-status-code]").forEach((node) => setStatus(node, node.dataset.statusCode, node.dataset.statusTone || "green"));
    if (state.scenarios.length) renderScenarioQueue(state.scenarios);
  }

  function setStatus(node, code, tone = "green") {
    if (!node) return;
    node.dataset.statusCode = code;
    node.dataset.statusTone = tone;
    node.className = `status ${tone}`;
    const dot = document.createElement("i");
    const visible = document.createElement("span"); visible.className = "status-label"; visible.textContent = copy(code);
    const technical = document.createElement("span"); technical.className = "status-code mono"; technical.textContent = code;
    node.replaceChildren(dot, visible, technical);
  }

  function localizedRecipeName(name) {
    const names = {
      "Demo Rules · direct function proposal": "قواعد تجريبية · اقتراح دالة مباشر",
      "Demo Rules · semantic plan then proposal": "قواعد تجريبية · خطة دلالية ثم اقتراح",
    };
    return state.locale === "ar" ? (names[name] || name) : name;
  }

  function addOption(select, binding) {
    const option = document.createElement("option");
    option.value = binding.id;
    option.textContent = `${binding.model_id} · ${copy(binding.execution_mode, "execution")} · ${copy(binding.tool_mode, "tool")}`;
    option.disabled = !binding.available;
    option.title = binding.unavailable_reason || "";
    select.append(option);
  }

  function populateBindings() {
    Object.entries(roles).forEach(([role, id]) => {
      const select = $(id); const old = select.value; select.replaceChildren();
      const matches = state.catalog.filter((binding) => binding.role === role);
      matches.forEach((binding) => addOption(select, binding));
      if (old && [...select.options].some((option) => option.value === old)) select.value = old;
      select.disabled = !matches.some((binding) => binding.available);
    });
  }

  function populateRecipes() {
    const select = $("recipeSelect"); const old = select.value; select.replaceChildren();
    state.recipes.forEach((recipe) => {
      const option = document.createElement("option"); option.value = recipe.id; option.textContent = localizedRecipeName(recipe.name); select.append(option);
    });
    select.value = old && state.recipes.some((recipe) => recipe.id === old) ? old : "demo_direct_v1";
    loadRecipeIntoBuilder(select.value);
  }

  function loadRecipeIntoBuilder(recipeId) {
    const recipe = state.recipes.find((entry) => entry.id === recipeId);
    if (!recipe) return;
    $("recipeName").value = localizedRecipeName(recipe.name);
    $("twoStage").checked = recipe.action_mode === "TWO_STAGE";
    $("summaryBranch").checked = recipe.summary_branch;
    $("stageGraph").textContent = (recipe.graph || []).join(" → ");
    Object.entries(roles).forEach(([role, id]) => {
      const binding = recipe.bindings[role];
      if (binding && [...$(id).options].some((option) => option.value === binding.id)) $(id).value = binding.id;
      $("lock" + id.replace("binding", "")).checked = recipe.locked_roles.includes(role);
    });
  }

  function activeRecipeIds(datasetId = $("datasetSelect")?.value) {
    const candidates = datasetId === "SEED_HUMAN_EVAL"
      ? state.recipes.filter((recipe) => recipe.bindings.transcribe && Object.values(recipe.bindings).some((binding) => binding.execution_mode === "LOCAL"))
      : state.recipes.filter((recipe) => Object.values(recipe.bindings).every((binding) => binding.execution_mode === "DEMO_RULES"));
    return candidates.slice(0, 6).map((recipe) => recipe.id);
  }

  async function loadInitial() {
    const [catalog, recipes, sandbox] = await Promise.all([api("/api/catalog"), api("/api/recipes"), api("/api/sandbox")]);
    state.catalog = catalog.bindings; state.stageCapabilities = catalog.stage_capabilities?.stages || []; state.recipes = recipes;
    populateBindings(); populateRecipes(); renderSandbox(sandbox);
    const hasLocal = state.catalog.some((binding) => binding.execution_mode === "LOCAL" && binding.available);
    setStatus($("runtimeStatus"), hasLocal ? "LOCAL_MODEL_AVAILABLE" : "LOCAL_MODEL_BLOCKED", hasLocal ? "green" : "amber");
  }

  async function saveRecipe() {
    const bindingFor = (role) => state.catalog.find((binding) => binding.id === $(roles[role]).value);
    const actionMode = $("twoStage").checked ? "TWO_STAGE" : "DIRECT";
    const bindings = { function_call: bindingFor("function_call") };
    if ($("summaryBranch").checked) bindings.summarize = bindingFor("summarize");
    if (actionMode === "TWO_STAGE") bindings.actionize = bindingFor("actionize");
    const transcribe = bindingFor("transcribe");
    if (transcribe?.available) bindings.transcribe = transcribe;
    if (Object.values(bindings).some((binding) => !binding)) throw new Error("No eligible local binding for every required stage.");
    const locks = Object.entries(roles).filter(([role, id]) => $("lock" + id.replace("binding", "")).checked && bindings[role]).map(([role]) => role);
    const recipe = {
      id: `local_recipe_${Date.now()}`, name: $("recipeName").value.trim() || "Untitled local recipe", version: "1",
      bindings, action_mode: actionMode, summary_branch: $("summaryBranch").checked, locked_roles: locks,
      required_outputs: $("summaryBranch").checked ? ["summary", "proposal"] : ["proposal"], graph: [...(transcribe?.available ? ["transcribe"] : []), ...($("summaryBranch").checked ? ["summarize"] : []), ...(actionMode === "TWO_STAGE" ? ["actionize"] : []), "function_call"], created_by: "local-user"
    };
    $("stageGraph").textContent = recipe.graph.join(" → ");
    const saved = await api("/api/recipes", { method: "POST", body: JSON.stringify(recipe) });
    state.recipes.push(saved.recipe); $("recipeSelect").value = saved.recipe.id; populateRecipes(); $("recipeSelect").value = saved.recipe.id;
    toast(label("تم حفظ الوصفة المحلية.", "Local recipe saved."));
  }

  function renderSandbox(sandbox) { $("sandboxOutput").textContent = pretty(sandbox); }

  function stageNode(title, body, timing) {
    const node = document.createElement("article"); node.className = "stage";
    const heading = document.createElement("h4"); heading.textContent = title + (timing != null ? ` · ${timing.toFixed(2)} ms` : "");
    const detail = document.createElement(typeof body === "string" ? "p" : "pre");
    if (typeof body !== "string") detail.className = "mono";
    detail.textContent = typeof body === "string" ? body : pretty(body);
    node.append(heading, detail); return node;
  }

  function renderRun(record) {
    state.currentRecord = record;
    const output = $("runOutput"); output.replaceChildren();
    const outputs = record.outputs;
    $("runBadge").textContent = outputs.evidence_type || "—";
     if (outputs.transcription) output.append(stageNode(copy("Transcript", "stage"), outputs.transcription, outputs.transcription.latency_ms));
    if (outputs.summary) output.append(stageNode(label("الملخص", "Summary"), outputs.summary, outputs.stage_durations_ms?.summarize));
    if (outputs.semantic_plan) output.append(stageNode(label("الخطة الدلالية", "Semantic plan"), outputs.semantic_plan, outputs.stage_durations_ms?.actionize));
    if (outputs.proposal) output.append(stageNode(label("اقتراح الدالة", "Function proposal"), outputs.proposal, outputs.stage_durations_ms?.function_call));
     if (outputs.route) output.append(stageNode(copy("Stage-route evidence", "stage"), outputs.route));
    if (!outputs.summary && !outputs.proposal && !outputs.transcription && !outputs.route) output.textContent = label("لا توجد مخرجات بعد.", "No outputs yet.");
    const proposal = outputs.proposal;
    $("applyProposal").disabled = !(proposal && proposal.status === "READY" && !outputs.stale);
  }

  async function runWorkbench() {
    const body = {
      text: $("sourceText").value, recipe_id: $("recipeSelect").value, recording_id: state.recordingId,
      manual_transcript: $("manualTranscript").checked, reference_timestamp: $("referenceTime").value, timezone: "Asia/Riyadh"
    };
    const result = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    renderRun(result.record); renderSandbox(await api("/api/sandbox"));
    toast(label("اكتمل التشغيل محلياً.", "Local run completed."));
  }

  async function applyProposal() {
    const proposal = state.currentRecord?.outputs?.proposal;
    if (!proposal) return;
    const result = await api(`/api/records/${state.currentRecord.id}/apply`, { method: "POST", body: JSON.stringify({ proposal_id: proposal.id }) });
    renderSandbox(result.sandbox); toast(result.status);
  }

  function renderPreflight(plan) {
    state.planned = plan;
     const lines = [
       `${copy(plan.outcome, "outcome")} · ${copy(plan.mode, "mode")}`,
      `${label("المرشحون", "Candidates")}: ${plan.candidates.map((candidate) => candidate.name).join(" | ") || "—"}`,
       `${plan.dataset?.dataset_id || "—"} · ${plan.dataset?.evidence_type === "AUTHORED_SMOKE_FIXTURE" ? copy("AUTHORED_SMOKE_FIXTURE") : plan.dataset?.evidence_type || "—"}`,
       `${label("الحالات", "Cases")}: ${plan.case_count} · ${label("الحد الأعلى للاستدعاءات", "Upper-bound calls")}: ${plan.upper_bound_calls}/${plan.call_cap} · ${label("عن بعد", "remote")}: 0`,
      `${label("المستبعدون", "Excluded")}: ${plan.excluded_candidates.map((entry) => entry.reason).join(", ") || "—"}`
    ];
    $("preflight").textContent = lines.join("\n");
    $("startTournament").disabled = ["NO_ELIGIBLE_ROUTE", "NO_HUMAN_SEED_CASES", "CALL_CAP_EXCEEDED"].includes(plan.outcome);
  }

  async function preflight(mode) {
    document.querySelectorAll(".mode-buttons button").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
    const dataset_id = $("datasetSelect").value;
    const plan = await api("/api/tournaments/preflight", { method: "POST", body: JSON.stringify({ mode, recipe_ids: activeRecipeIds(dataset_id), dataset_id, case_limit: dataset_id === "SEED_HUMAN_EVAL" ? 30 : 12, total_call_cap: 240, quality_floor: .7, confirmed: false }) });
    renderPreflight(plan);
  }

  function reportTable(report) {
    const fragment = document.createDocumentFragment();
    const summary = document.createElement("p");
    const recommended = report.routes.find((route) => route.recipe_id === report.selection?.recommendation);
     summary.textContent = `${copy(report.status)} · ${copy(report.selection?.outcome || "—", "outcome")}${recommended ? ` · ${label("الوصفة الموصى بها", "Recommended recipe")}: ${recommended.name}` : ""} · ${report.selection?.reason || ""}`;
    fragment.append(summary);
    const table = document.createElement("table");
    const head = document.createElement("thead"), headRow = document.createElement("tr");
     ["الوصفة", "الدليل", "الجودة", "التغطية", "الإخفاقات", "متوسط المللي ثانية"].map((ar, index) => [ar, ["Recipe", "Evidence", "Quality", "Coverage", "Failures", "Mean ms"][index]]).forEach(([ar, en]) => { const cell = document.createElement("th"); cell.textContent = label(ar, en); headRow.append(cell); });
    head.append(headRow); table.append(head);
    const body = document.createElement("tbody");
     report.routes.forEach((route) => { const row = document.createElement("tr"); [route.name, copy(route.evidence_type, "evidence"), route.task_quality, route.completion_coverage, route.failures, route.mean_end_to_end_latency_ms?.toFixed(3)].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value == null ? "—" : String(value); row.append(cell); }); body.append(row); });
    table.append(body); fragment.append(table);
    if (report.status === "COMPLETED") {
      const links = document.createElement("p");
      const json = document.createElement("a"); json.href = `/api/tournaments/${report.id}/export.json`; json.textContent = "JSON";
      const csv = document.createElement("a"); csv.href = `/api/tournaments/${report.id}/export.csv`; csv.textContent = "CSV"; csv.style.marginInlineStart = "1rem";
      links.append(label("تصدير: ", "Export: "), json, csv); fragment.append(links);
    }
    return fragment;
  }

  async function startTournament() {
    if (!state.planned) return;
    const dataset_id = state.planned.dataset?.dataset_id || $("datasetSelect").value;
    const started = await api("/api/tournaments/start", { method: "POST", body: JSON.stringify({ mode: state.planned.mode, recipe_ids: activeRecipeIds(dataset_id), dataset_id, case_limit: dataset_id === "SEED_HUMAN_EVAL" ? 30 : 12, total_call_cap: 240, quality_floor: .7, confirmed: true }) });
     if (!started.id) { renderPreflight(started); return; }
     state.tournamentId = started.id; $("cancelTournament").disabled = false; $("tournamentOutput").textContent = `${copy("RUNNING")}…`;
    document.querySelector('[data-view="tournaments"]').click();
    pollTournament();
  }

  async function pollTournament() {
    if (!state.tournamentId) return;
    try {
      const job = await api(`/api/tournaments/${state.tournamentId}`);
      const target = $("tournamentOutput"); target.replaceChildren();
       if (job.report) target.append(reportTable(job.report)); else target.textContent = `${copy(job.status)} · ${label("المقارنة محكومة بحد ثابت ولا توجد استدعاءات عن بعد.", "Comparison is bounded; remote calls remain zero.")}`;
      if (["COMPLETED", "CANCELLED"].includes(job.status)) { $("cancelTournament").disabled = true; return; }
      window.setTimeout(pollTournament, 450);
    } catch (error) { toast(error.message); }
  }

  async function uploadAudio(file, duration) {
    const form = new FormData(); form.append("file", file); if (duration != null) form.append("duration_seconds", String(duration));
    const result = await api("/api/recordings", { method: "POST", body: form });
    state.recordingId = result.recording_id;
    $("audioState").textContent = `${label("محلي", "Local")} · ${label("جاهز للتفريغ", "Ready for transcription")}`;
    const seedState = $("seedRecordingState"); if (seedState) seedState.textContent = `${label("تسجيل", "Recording")} ${result.recording_id.slice(0, 8)} · ${result.duration_seconds.toFixed(1)} ${label("ثانية", "s")}`;
    toast(label("تم حفظ التسجيل محلياً؛ لا يوجد إرسال إلى خدمة تفريغ." , "Recording stored locally; no transcription service was contacted."));
  }

  function mediaDuration(file) {
    return new Promise((resolve, reject) => {
      const audio = document.createElement("audio"); const url = URL.createObjectURL(file);
      audio.preload = "metadata";
      audio.onloadedmetadata = () => { const duration = audio.duration; URL.revokeObjectURL(url); resolve(Number.isFinite(duration) ? duration : null); };
      audio.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Could not read audio duration.")); };
      audio.src = url;
    });
  }

  async function handleFile(file) {
    if (!file) return;
    const duration = await mediaDuration(file);
    $("audioPreview").src = URL.createObjectURL(file); $("audioPreview").hidden = false;
    await uploadAudio(file, duration);
  }

  async function toggleRecord() {
    if (state.recorder && state.recorder.state === "recording") { state.recorder.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream); state.recorder = recorder; state.chunks = []; const started = performance.now();
      recorder.ondataavailable = (event) => { if (event.data.size) state.chunks.push(event.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop()); $("recordButton").textContent = label("تسجيل", "Record");
        const blob = new Blob(state.chunks, { type: recorder.mimeType || "audio/webm" }); const file = new File([blob], "recording.webm", { type: blob.type || "audio/webm" });
        $("audioPreview").src = URL.createObjectURL(blob); $("audioPreview").hidden = false;
        try { await uploadAudio(file, (performance.now() - started) / 1000); } catch (error) { toast(error.message); }
      };
      recorder.start(); $("recordButton").textContent = label("إيقاف التسجيل", "Stop recording"); $("audioState").textContent = label("جارٍ التسجيل محلياً…", "Recording locally…");
    } catch (error) { toast(label("تعذر الوصول إلى الميكروفون: ", "Microphone unavailable: ") + error.message); }
  }

  function recordElement(record) {
    const details = document.createElement("details"); details.className = "record";
    const summary = document.createElement("summary"); summary.textContent = `${record.id.slice(0, 8)} · r${record.revision} · ${copy(record.review_state || "RECORDED", "review")} · ${copy(record.label_state, "labelState")} · ${copy(record.outputs.evidence_type || "—", "evidence")}`;
    const meta = document.createElement("p"); meta.className = "meta"; meta.textContent = `${record.created_at} · ${record.recording_name ? label("صوت مرفق", "audio attached") : label("نص فقط", "text only")}`;
    const text = document.createElement("textarea"); text.value = record.text;
    const expected = document.createElement("input"); expected.type = "hidden"; expected.value = record.revision;
    const reviewer = document.createElement("input"); reviewer.placeholder = label("معرّف المراجع البشري", "Human reviewer ID");
    const labelState = document.createElement("select"); ["CANDIDATE", "SILVER", "GOLD", "REJECTED"].forEach((value) => { const option = document.createElement("option"); option.value = value; option.textContent = copy(value, "labelState"); option.selected = value === record.label_state; labelState.append(option); });
    const actions = document.createElement("div"); actions.className = "record-actions";
    const save = document.createElement("button"); save.textContent = label("حفظ تعديل النص", "Save transcript edit"); save.onclick = async () => { try { const updated = await api(`/api/records/${record.id}/transcript`, { method: "PATCH", body: JSON.stringify({ text: text.value, expected_revision: Number(expected.value) }) }); expected.value = updated.revision; toast("STALE: rerun required"); await refreshRecords(); } catch (error) { toast(error.message); } };
    const review = document.createElement("button"); review.className = "secondary"; review.textContent = label("تسجيل مراجعة بشرية", "Record human review"); review.onclick = async () => { try { await api(`/api/records/${record.id}/review`, { method: "PATCH", body: JSON.stringify({ label_state: labelState.value, reviewer_type: "human", reviewer_identity: reviewer.value || null, promotion_reason: "Explicit local human review" }) }); toast(label("تم حفظ المراجعة.", "Review saved.")); await refreshRecords(); } catch (error) { toast(error.message); } };
    const remove = document.createElement("button"); remove.className = "danger"; remove.textContent = label("حذف محلي", "Delete local record"); remove.onclick = async () => { if (!window.confirm(label("حذف هذا السجل محلياً؟", "Delete this local record?"))) return; try { await api(`/api/records/${record.id}`, { method: "DELETE" }); await refreshRecords(); toast("DELETED"); } catch (error) { toast(error.message); } };
    actions.append(save, labelState, reviewer, review, remove); details.append(summary, meta, text, expected, actions); return details;
  }

  async function refreshRecords() {
    const records = await api("/api/records"); const target = $("recordsOutput"); target.replaceChildren();
    if (!records.length) { target.textContent = label("لا توجد سجلات محفوظة بعد.", "No saved records yet."); return; }
    records.forEach((record) => target.append(recordElement(record)));
  }

  async function refreshSeedCases() {
    const seed = await api("/api/seed-human-eval");
    $("seedCasesOutput").textContent = pretty({ dataset_id: seed.dataset_id, evidence_type: seed.evidence_type, case_count: seed.case_count, target_case_count: seed.target_case_count, cases: seed.cases.map((entry) => ({ id: entry.id, recording_id: entry.recording_id, review_state: entry.review_state, reviewed_transcript: entry.reviewed_transcript, expected: entry.expected, provenance: entry.provenance })) });
  }

  function renderScenarioQueue(scenarios) {
    const target = $("scenarioQueue"); target.replaceChildren();
    scenarios.forEach((scenario, index) => {
      const localized = SCENARIO_COPY[scenario.id] || [scenario.intent, scenario.facts || []];
      const intent = state.locale === "ar" ? localized[0] : scenario.intent;
      const facts = state.locale === "ar" ? localized[1] : (scenario.semantic_facts || scenario.facts || []);
      const expected = state.locale === "ar" ? (OUTCOME_COPY[scenario.expected_broad_outcome] || scenario.expected_broad_outcome) : scenario.expected_broad_outcome;
      const card = document.createElement("article"); card.className = "scenario-card";
      const button = document.createElement("button"); button.type = "button"; button.className = "secondary";
       button.textContent = `${index + 1}. ${intent}`;
       button.onclick = () => { $("seedPrompt").textContent = `${intent}: ${label("تحدث بطبيعتك؛ المثال اختياري.", "Speak naturally; the example is optional.")}`; $("seedTranscript").value = ""; };
      const details = document.createElement("p"); details.className = "small muted";
       details.textContent = `${label("الوقائع", "Facts")}: ${facts.join(", ")} · ${label("النتيجة المتوقعة", "Expected")}: ${expected || label("تتطلب مراجعة بشرية", "human review required")} · ${label("قد يلزم التوضيح", "Clarification may be required")}: ${scenario.clarification_may_be_required ? label("نعم", "yes") : label("لا", "no")} · ${label("مثال اختياري", "Optional example")}: ${scenario.example || "—"}`;
      card.append(button, details); target.append(card);
    });
  }

  async function refreshSeedScenarios() {
    const payload = await api("/api/seed-scenarios");
    state.scenarios = payload.scenarios || [];
    renderScenarioQueue(state.scenarios);
  }

  function renderSttCompare(report) {
    const target = $("sttCompareOutput"); target.replaceChildren();
     const note = document.createElement("p"); note.textContent = `${copy(report.selection?.outcome || "—", "outcome")} · ${copy(report.selection?.quality_ranking || "—", "outcome")} · ${copy(report.evidence_type, "evidence")} · ${label("المجموعة", "dataset")}: ${report.human_reference ? copy("SEED_HUMAN_EVAL") : label("تسجيل محلي غير مُراجع", "UNREVIEWED_LOCAL_RECORDING")} · ${label("الاستدعاءات عن بعد", "remote calls")}: ${report.remote_calls}`; target.append(note);
     const columns = [label("مرجع بشري", "Human reference"), ...report.candidates.map((candidate) => candidate.model_id)];
    const table = document.createElement("table"); const head = document.createElement("tr");
     [label("الدليل", "Evidence"), ...columns].forEach((text) => { const cell = document.createElement("th"); cell.textContent = text; head.append(cell); });
    const thead = document.createElement("thead"); thead.append(head); table.append(thead);
    const rows = [
       [label("التفريغ", "Transcript"), report.human_reference || "—", ...report.candidates.map((candidate) => candidate.transcript || candidate.error || "—")],
       ["WER", "—", ...report.candidates.map((candidate) => candidate.wer == null ? "—" : candidate.wer.toFixed(3))],
       ["CER", "—", ...report.candidates.map((candidate) => candidate.cer == null ? "—" : candidate.cer.toFixed(3))],
       [label("الزمن", "Latency"), "—", ...report.candidates.map((candidate) => candidate.latency_ms == null ? "—" : `${candidate.latency_ms.toFixed(1)} ${label("مللي ثانية", "ms")}`)],
       [label("المصدر", "Provenance"), "—", ...report.candidates.map((candidate) => `${candidate.provider} · ${candidate.revision_or_digest || "—"} · ${candidate.runtime || "—"}`)],
       [label("أخطاء الكلام", "Speech errors"), label("موسومة بشريًا", "human-labelled"), ...report.candidates.map((candidate) => (candidate.speech_errors || []).join(", ") || "—")],
        [label("الحالة", "Status"), label("مرجعية عند إدخالها فقط", "authoritative only when entered"), ...report.candidates.map((candidate) => copy(candidate.status, "state"))],
    ];
    const body = document.createElement("tbody");
    rows.forEach((values) => { const row = document.createElement("tr"); values.forEach((value) => { const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell); }); body.append(row); });
    table.append(body); target.append(table);
    const aggregate = document.createElement("pre"); aggregate.className = "small mono"; aggregate.textContent = pretty({ aggregates: report.aggregates, disagreement: report.disagreement }); target.append(aggregate);
  }

  async function compareRecording() {
    if (!state.recordingId) throw new Error("Record or upload an audio clip in Workbench first.");
    renderSttCompare(await api(`/api/recordings/${state.recordingId}/stt-compare`));
  }

  async function refreshModels() {
    const payload = await api("/api/models");
    const target = $("modelsOutput"); target.replaceChildren();
    const table = document.createElement("table");
    const head = document.createElement("thead"); const row = document.createElement("tr");
     ["النموذج", "المرحلة", "الدقة", "حالة الملف", "وقت التشغيل", "بوابة الترخيص"].map((ar, index) => [ar, ["Model", "Stage", "Precision", "Artifact state", "Runtime", "License gate"][index]]).forEach(([ar, en]) => { const cell = document.createElement("th"); cell.textContent = label(ar, en); row.append(cell); });
     head.append(row); table.append(head);
    const body = document.createElement("tbody");
     payload.models.forEach((model) => { const tr = document.createElement("tr"); [model.id, (model.stage || []).map((stage) => copy(stage, "stageKey")).join(", "), model.precision || label("غير معروف", "UNKNOWN"), copy(model.artifact_state || "—", "state"), model.runtime || "—", `${model.license_id || label("غير معروف", "UNKNOWN")} · ${label("الوضع التجاري", "commercial")} ${model.commercial_status || label("غير معروف", "UNKNOWN")}`].forEach((value) => { const td = document.createElement("td"); td.textContent = value == null ? "—" : String(value); tr.append(td); }); body.append(tr); });
    table.append(body); target.append(table);
    const capTarget = $("capabilitiesOutput"); capTarget.replaceChildren();
    const capTable = document.createElement("table"); const capHead = document.createElement("tr");
     ["Stage", "Artifact", "Runtime", "Capability", "Reason"].map((en, index) => [["المرحلة", "الملف", "وقت التشغيل", "القدرة", "السبب"][index], en]).forEach(([ar, en]) => { const cell = document.createElement("th"); cell.textContent = label(ar, en); capHead.append(cell); });
    const capBody = document.createElement("tbody");
      state.stageCapabilities.forEach((item) => { const tr = document.createElement("tr"); [copy(item.stage, "stageKey"), copy(item.artifact_state, "state"), copy(item.runtime_state, "state"), copy(item.capability_state, "state"), item.reason || "—"].forEach((value) => { const td = document.createElement("td"); td.textContent = String(value); tr.append(td); }); capBody.append(tr); });
    capTable.append(capHead, capBody); capTarget.append(capTable);
     const qwen = await api("/api/qwen-certification"); const qwenNote = document.createElement("p"); qwenNote.className = "small mono"; qwenNote.textContent = `${label("جاهزية اعتماد Qwen", "Qwen certification readiness")}: ${qwen.status} · ${label("الأدوار", "roles")}: ${(qwen.roles || []).join(", ")} · ${label("الحالات", "cases")}: ${(qwen.cases || []).length}`; capTarget.append(qwenNote);
  }

  async function saveSeedCase() {
    if (!state.recordingId) throw new Error("Record or upload an audio clip in Workbench first.");
    let expected_arguments, critical_spans;
    try { expected_arguments = JSON.parse($("seedArguments").value || "{}"); critical_spans = JSON.parse($("seedCriticalSpans").value || "[]"); } catch (_) { throw new Error("Expected arguments and critical spans must be valid JSON."); }
    const body = {
      recording_id: state.recordingId, reviewed_transcript: $("seedTranscript").value.trim(), expected_status: $("seedStatus").value,
      expected_tool_name: $("seedTool").value || null, expected_arguments, requires_clarification: $("seedClarification").checked,
      critical_spans, reviewer_identity: $("seedReviewer").value || null, recording_session_id: $("seedSession").value || null, notes: $("seedNotes").value || null,
      semantic_reference_reviewed: $("seedSemanticReviewed").checked
    };
    const result = await api("/api/seed-human-eval", { method: "POST", body: JSON.stringify(body) });
    toast(label("تم حفظ المرجع البشري محلياً.", "Human reference saved locally."));
    await refreshSeedCases();
    return result;
  }

  function bindEvents() {
    $("localeToggle").onclick = () => setLocale(state.locale === "ar" ? "en" : "ar");
    document.querySelectorAll(".nav").forEach((button) => button.onclick = () => { document.querySelectorAll(".nav,.view").forEach((node) => node.classList.remove("active")); button.classList.add("active"); $(button.dataset.view).classList.add("active"); if (button.dataset.view === "review") refreshRecords().catch((error) => toast(error.message)); if (button.dataset.view === "seed") refreshSeedCases().catch((error) => toast(error.message)); if (button.dataset.view === "models") refreshModels().catch((error) => toast(error.message)); });
    document.querySelectorAll("[data-sample]").forEach((button) => button.onclick = () => { $("sourceText").value = button.dataset.sample; });
    $("recipeSelect").onchange = (event) => loadRecipeIntoBuilder(event.target.value);
    $("saveRecipe").onclick = () => saveRecipe().catch((error) => toast(error.message));
    $("runWorkbench").onclick = () => runWorkbench().catch((error) => toast(error.message));
    $("applyProposal").onclick = () => applyProposal().catch((error) => toast(error.message));
    document.querySelectorAll(".mode-buttons button").forEach((button) => button.onclick = () => preflight(button.dataset.mode).catch((error) => toast(error.message)));
    $("startTournament").onclick = () => startTournament().catch((error) => toast(error.message));
    $("cancelTournament").onclick = () => state.tournamentId && api(`/api/tournaments/${state.tournamentId}/cancel`, { method: "POST", body: "{}" }).then(pollTournament).catch((error) => toast(error.message));
    $("audioFile").onchange = (event) => handleFile(event.target.files?.[0]).catch((error) => toast(error.message));
    $("recordButton").onclick = () => toggleRecord();
    document.querySelectorAll("[data-seed-prompt]").forEach((button) => button.onclick = () => { $("seedPrompt").textContent = button.dataset.seedPrompt; $("seedTranscript").value = button.dataset.seedPrompt; });
    $("saveSeedCase").onclick = () => saveSeedCase().catch((error) => toast(error.message));
    $("compareRecording").onclick = () => compareRecording().catch((error) => toast(error.message));
    $("refreshSeedScenarios").onclick = () => refreshSeedScenarios().catch((error) => toast(error.message));
    $("refreshSeedCases").onclick = () => refreshSeedCases().catch((error) => toast(error.message));
    $("refreshRecords").onclick = () => refreshRecords().catch((error) => toast(error.message));
    $("refreshModels").onclick = () => refreshModels().catch((error) => toast(error.message));
    $("manifestButton").onclick = () => api("/api/training-manifest").then((manifest) => { $("manifestOutput").textContent = pretty(manifest); }).catch((error) => toast(error.message));
  }

  bindEvents(); setLocale("ar"); loadInitial().then(() => refreshSeedScenarios()).catch((error) => toast(error.message));
})();
