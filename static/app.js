(() => {
  const state = { catalog: [], recipes: [], currentRecord: null, planned: null, tournamentId: null, locale: "ar", recordingId: null, recorder: null, chunks: [] };
  const $ = (id) => document.getElementById(id);
  const roles = { transcribe: "bindingTranscribe", summarize: "bindingSummarize", actionize: "bindingActionize", function_call: "bindingFunction" };

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

  function toast(message) {
    const node = $("toast"); node.textContent = message; node.classList.add("show");
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
    $("localeToggle").textContent = locale === "ar" ? "English" : "العربية";
  }

  function addOption(select, binding) {
    const option = document.createElement("option");
    option.value = binding.id;
    option.textContent = `${binding.model_id} · ${binding.execution_mode} · ${binding.tool_mode}`;
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
      const option = document.createElement("option"); option.value = recipe.id; option.textContent = recipe.name; select.append(option);
    });
    select.value = old && state.recipes.some((recipe) => recipe.id === old) ? old : "demo_direct_v1";
    loadRecipeIntoBuilder(select.value);
  }

  function loadRecipeIntoBuilder(recipeId) {
    const recipe = state.recipes.find((entry) => entry.id === recipeId);
    if (!recipe) return;
    $("recipeName").value = recipe.name;
    $("twoStage").checked = recipe.action_mode === "TWO_STAGE";
    $("summaryBranch").checked = recipe.summary_branch;
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
    state.catalog = catalog.bindings; state.recipes = recipes;
    populateBindings(); populateRecipes(); renderSandbox(sandbox);
    const hasLocal = state.catalog.some((binding) => binding.execution_mode === "LOCAL" && binding.available);
    $("runtimeStatus").className = "status " + (hasLocal ? "green" : "amber");
    $("runtimeStatus").textContent = hasLocal ? "LOCAL MODEL AVAILABLE" : "DEMO_RULES · local model blocked";
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
      required_outputs: $("summaryBranch").checked ? ["summary", "proposal"] : ["proposal"], created_by: "local-user"
    };
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
    if (outputs.transcription) output.append(stageNode("Transcript", outputs.transcription, outputs.transcription.latency_ms));
    if (outputs.summary) output.append(stageNode(label("الملخص", "Summary"), outputs.summary, outputs.stage_durations_ms?.summarize));
    if (outputs.semantic_plan) output.append(stageNode(label("الخطة الدلالية", "Semantic plan"), outputs.semantic_plan, outputs.stage_durations_ms?.actionize));
    if (outputs.proposal) output.append(stageNode(label("اقتراح الدالة", "Function proposal"), outputs.proposal, outputs.stage_durations_ms?.function_call));
    if (!outputs.summary && !outputs.proposal && !outputs.transcription) output.textContent = label("لا توجد مخرجات بعد.", "No outputs yet.");
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
      `${plan.outcome} · ${plan.mode}`,
      `${label("المرشحون", "Candidates")}: ${plan.candidates.map((candidate) => candidate.name).join(" | ") || "—"}`,
      `${plan.dataset?.dataset_id || "—"} · ${plan.dataset?.evidence_type || "—"}`,
      `${label("الحالات", "Cases")}: ${plan.case_count} · ${label("الحد الأعلى للاستدعاءات", "Upper-bound calls")}: ${plan.upper_bound_calls}/${plan.call_cap} · remote: 0`,
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
    summary.textContent = `${report.status} · ${report.selection?.outcome || "—"}${recommended ? ` · ${label("الوصفة الموصى بها", "Recommended recipe")}: ${recommended.name}` : ""} · ${report.selection?.reason || ""}`;
    fragment.append(summary);
    const table = document.createElement("table");
    const head = document.createElement("thead"), headRow = document.createElement("tr");
    ["Recipe", "Evidence", "Quality", "Coverage", "Failures", "Mean ms"].forEach((text) => { const cell = document.createElement("th"); cell.textContent = text; headRow.append(cell); });
    head.append(headRow); table.append(head);
    const body = document.createElement("tbody");
    report.routes.forEach((route) => { const row = document.createElement("tr"); [route.name, route.evidence_type, route.task_quality, route.completion_coverage, route.failures, route.mean_end_to_end_latency_ms?.toFixed(3)].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value == null ? "—" : String(value); row.append(cell); }); body.append(row); });
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
    state.tournamentId = started.id; $("cancelTournament").disabled = false; $("tournamentOutput").textContent = "RUNNING…";
    document.querySelector('[data-view="tournaments"]').click();
    pollTournament();
  }

  async function pollTournament() {
    if (!state.tournamentId) return;
    try {
      const job = await api(`/api/tournaments/${state.tournamentId}`);
      const target = $("tournamentOutput"); target.replaceChildren();
      if (job.report) target.append(reportTable(job.report)); else target.textContent = `${job.status} · ${label("المقارنة محكومة بحد ثابت ولا توجد استدعاءات عن بعد.", "Comparison is bounded; remote calls remain zero.")}`;
      if (["COMPLETED", "CANCELLED"].includes(job.status)) { $("cancelTournament").disabled = true; return; }
      window.setTimeout(pollTournament, 450);
    } catch (error) { toast(error.message); }
  }

  async function uploadAudio(file, duration) {
    const form = new FormData(); form.append("file", file); if (duration != null) form.append("duration_seconds", String(duration));
    const result = await api("/api/recordings", { method: "POST", body: form });
    state.recordingId = result.recording_id;
    $("audioState").textContent = `${result.duration_source} · ${result.asr_status}`;
    const seedState = $("seedRecordingState"); if (seedState) seedState.textContent = `Recording ${result.recording_id.slice(0, 8)} · ${result.duration_seconds.toFixed(1)}s`;
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
    const summary = document.createElement("summary"); summary.textContent = `${record.id.slice(0, 8)} · r${record.revision} · ${record.label_state} · ${record.outputs.evidence_type || "—"}`;
    const meta = document.createElement("p"); meta.className = "meta"; meta.textContent = `${record.created_at} · ${record.recording_name ? "audio attached" : "text only"}`;
    const text = document.createElement("textarea"); text.value = record.text;
    const expected = document.createElement("input"); expected.type = "hidden"; expected.value = record.revision;
    const reviewer = document.createElement("input"); reviewer.placeholder = label("معرّف المراجع البشري", "Human reviewer ID");
    const labelState = document.createElement("select"); ["CANDIDATE", "SILVER", "GOLD", "REJECTED"].forEach((value) => { const option = document.createElement("option"); option.value = value; option.textContent = value; option.selected = value === record.label_state; labelState.append(option); });
    const actions = document.createElement("div"); actions.className = "record-actions";
    const save = document.createElement("button"); save.textContent = label("حفظ تعديل النص", "Save transcript edit"); save.onclick = async () => { try { const updated = await api(`/api/records/${record.id}/transcript`, { method: "PATCH", body: JSON.stringify({ text: text.value, expected_revision: Number(expected.value) }) }); expected.value = updated.revision; toast("STALE: rerun required"); await refreshRecords(); } catch (error) { toast(error.message); } };
    const review = document.createElement("button"); review.className = "secondary"; review.textContent = label("تسجيل مراجعة بشرية", "Record human review"); review.onclick = async () => { try { await api(`/api/records/${record.id}/review`, { method: "PATCH", body: JSON.stringify({ label_state: labelState.value, reviewer_type: "human", reviewer_identity: reviewer.value || null, promotion_reason: "Explicit local human review" }) }); toast("Review saved"); await refreshRecords(); } catch (error) { toast(error.message); } };
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
    $("seedCasesOutput").textContent = pretty({ dataset_id: seed.dataset_id, evidence_type: seed.evidence_type, case_count: seed.case_count, target_case_count: seed.target_case_count, cases: seed.cases.map((entry) => ({ id: entry.id, recording_id: entry.recording_id, reviewed_transcript: entry.reviewed_transcript, expected: entry.expected, provenance: entry.provenance })) });
  }

  async function refreshModels() {
    const payload = await api("/api/models");
    const target = $("modelsOutput"); target.replaceChildren();
    const table = document.createElement("table");
    const head = document.createElement("thead"); const row = document.createElement("tr");
    ["Model", "Stage", "Precision", "Artifact state", "Runtime", "License gate"].forEach((labelText) => { const cell = document.createElement("th"); cell.textContent = labelText; row.append(cell); });
    head.append(row); table.append(head);
    const body = document.createElement("tbody");
    payload.models.forEach((model) => { const tr = document.createElement("tr"); [model.id, (model.stage || []).join(", "), model.precision || "UNKNOWN", model.artifact_state, model.runtime, `${model.license_id || "UNKNOWN"} · commercial ${model.commercial_status || "UNKNOWN"}`].forEach((value) => { const td = document.createElement("td"); td.textContent = value == null ? "—" : String(value); tr.append(td); }); body.append(tr); });
    table.append(body); target.append(table);
  }

  async function saveSeedCase() {
    if (!state.recordingId) throw new Error("Record or upload an audio clip in Workbench first.");
    let expected_arguments, critical_spans;
    try { expected_arguments = JSON.parse($("seedArguments").value || "{}"); critical_spans = JSON.parse($("seedCriticalSpans").value || "[]"); } catch (_) { throw new Error("Expected arguments and critical spans must be valid JSON."); }
    const body = {
      recording_id: state.recordingId, reviewed_transcript: $("seedTranscript").value.trim(), expected_status: $("seedStatus").value,
      expected_tool_name: $("seedTool").value || null, expected_arguments, requires_clarification: $("seedClarification").checked,
      critical_spans, reviewer_identity: $("seedReviewer").value || null, recording_session_id: $("seedSession").value || null, notes: $("seedNotes").value || null
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
    $("refreshSeedCases").onclick = () => refreshSeedCases().catch((error) => toast(error.message));
    $("refreshRecords").onclick = () => refreshRecords().catch((error) => toast(error.message));
    $("refreshModels").onclick = () => refreshModels().catch((error) => toast(error.message));
    $("manifestButton").onclick = () => api("/api/training-manifest").then((manifest) => { $("manifestOutput").textContent = pretty(manifest); }).catch((error) => toast(error.message));
  }

  bindEvents(); setLocale("ar"); loadInitial().catch((error) => toast(error.message));
})();
