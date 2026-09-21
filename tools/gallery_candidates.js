// Embedded in the studio boot scope; v2 candidates stay local and journal-only.
const V2_BUCKETS = ["普通人物", "新角色设计", "无法确定"];
let v2FocusedCandidate = null;
let v2LastMarkFaceId = null;
let v2MemoryDocument = null;

function v2Numeric(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function v2Evidence(face) {
  return face && face.candidate_evidence && typeof face.candidate_evidence === "object"
    ? face.candidate_evidence : null;
}

function v2CandidateName(candidate) {
  return String(candidate?.display || candidate?.name || candidate?.character || "").trim();
}

function v2CandidateSource(candidate) {
  const source = String(candidate?.source || "");
  return source === "anchor" || source === "model" ? "model" : source;
}

function v2CandidateScore(candidate, source) {
  const value = source === "memory" ? candidate?.score_memory : candidate?.score_model;
  return v2Numeric(value) ?? v2Numeric(candidate?.score);
}

function v2SourceLine(source) {
  if (!source) return "来源未提供";
  if (typeof source === "string") return source;
  const name = String(source.name || source.model || source.path || "来源未提供");
  const licence = source.license || source.licence;
  const closed = source.closed_set ?? source.closed_set_size;
  const parts = [name];
  if (licence) parts.push(`许可 ${licence}`);
  if (v2Numeric(closed) !== null) parts.push(`封闭集 ${v2Numeric(closed).toLocaleString("zh-CN")}`);
  return parts.join(" · ");
}

function v2ShowToast(text) {
  let toast = document.getElementById("studio-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "studio-toast";
    toast.className = "studio-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.append(toast);
  }
  toast.textContent = text;
  toast.classList.add("is-visible");
  window.clearTimeout(Number(toast.dataset.timer || 0));
  toast.dataset.timer = String(window.setTimeout(() => toast.classList.remove("is-visible"), 1800));
}

function v2MakeButton(action, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "face-quick-action candidate-choice";
  button.dataset.faceQuick = action;
  button.dataset.candidateChoice = "true";
  button.textContent = label;
  return button;
}

function v2RenderAttributes(attributes) {
  const block = document.createElement("div");
  block.className = "candidate-attributes";
  const title = document.createElement("strong");
  title.textContent = "属性证据 · WD tags";
  block.append(title);
  if (!attributes || typeof attributes !== "object") {
    const unavailable = document.createElement("span");
    unavailable.className = "attribute-unavailable";
    unavailable.textContent = "不可用";
    block.append(unavailable);
    return block;
  }
  const grid = document.createElement("div");
  grid.className = "attribute-grid";
  [["发色", attributes.hair_color], ["发型", attributes.hair_style]].forEach(([label, value]) => {
    const item = document.createElement("span");
    item.className = "attribute-item";
    item.textContent = `${label}：${String(value || "—")}`;
    grid.append(item);
  });
  const tags = Array.isArray(attributes.tags) ? attributes.tags : [];
  const tagItem = document.createElement("span");
  tagItem.className = "attribute-item attribute-tags";
  tagItem.textContent = `主要标签：${tags.length ? tags.slice(0, 8).map((tag) => {
    const name = String(tag?.tag || "");
    return v2Numeric(tag?.score) === null ? name : `${name} ${v2Numeric(tag.score).toFixed(2)}`;
  }).filter(Boolean).join(" · ") : "—"}`;
  grid.append(tagItem);
  block.append(grid);
  return block;
}

function v2CandidateButton(candidate, shortcut) {
  const source = v2CandidateSource(candidate);
  const button = v2MakeButton("candidate", `${shortcut ? `${shortcut}  ` : ""}${v2CandidateName(candidate) || "未命名"}`);
  button.dataset.character = v2CandidateName(candidate);
  button.dataset.candidateSource = source;
  const metric = document.createElement("span");
  metric.className = "candidate-metric";
  const score = v2CandidateScore(candidate, source);
  const margin = v2Numeric(candidate?.margin_vs_runner_up ?? candidate?.margin);
  metric.textContent = score === null ? "分数 —" : `${source === "memory" ? "相似度" : "分数"} ${Number(score).toFixed(3)}`;
  if (margin !== null) metric.textContent += ` · 间隔 ${margin >= 0 ? "+" : ""}${margin.toFixed(3)}`;
  button.append(metric);
  if (shortcut) {
    button.dataset.candidateIndex = String(shortcut - 1);
    button.setAttribute("aria-keyshortcuts", String(shortcut));
  }
  button.addEventListener("focus", () => {
    v2FocusedCandidate = { character: button.dataset.character || "", source };
  });
  return button;
}

function v2CandidateSection(title, source, candidates, sourceMeta, shortcutStart) {
  const section = document.createElement("section");
  section.className = "candidate-section";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const provenance = document.createElement("span");
  provenance.className = "candidate-provenance";
  provenance.textContent = v2SourceLine(sourceMeta);
  heading.append(provenance);
  section.append(heading);
  const list = document.createElement("div");
  list.className = "candidate-list";
  candidates.forEach((candidate, index) => list.append(v2CandidateButton(candidate, index + shortcutStart)));
  if (!candidates.length) {
    const empty = document.createElement("p");
    empty.className = "candidate-unavailable";
    empty.textContent = "暂无可用候选";
    list.append(empty);
  }
  section.append(list);
  return section;
}

function renderFaceQuickActions(face) {
  const popover = els("face-popover");
  let quick = popover.querySelector(".face-quick-actions");
  if (!quick) {
    quick = document.createElement("div");
    quick.className = "face-quick-actions";
    popover.insertBefore(quick, els("face-character-select"));
  }
  const fullNodes = [popover.querySelector('label[for="face-character-select"]'), els("face-character-select"),
    popover.querySelector(".select-hint"), popover.querySelector('label[for="face-character-name"]'),
    els("face-character-name"), popover.querySelector(".face-popover-actions")].filter(Boolean);
  fullNodes.forEach((node) => { node.dataset.faceFull = "true"; node.hidden = true; });
  quick.replaceChildren();
  quick.hidden = false;
  v2FocusedCandidate = null;
  const make = (action, label) => v2MakeButton(action, label);
  const evidence = v2Evidence(face);
  const candidates = Array.isArray(evidence?.candidates) ? evidence.candidates : [];
  const model = candidates.filter((candidate) => ["model", "anchor", ""].includes(v2CandidateSource(candidate)));
  const memory = candidates.filter((candidate) => v2CandidateSource(candidate) === "memory");
  quick.append(renderSuggestionTiers(evidence));
  quick.append(v2CandidateSection("模型枚举", "model", model, evidence?.sources?.model, 1));
  quick.append(v2CandidateSection("我的命名", "memory", memory, evidence?.sources?.memory, model.length + 1));
  quick.append(v2RenderAttributes(evidence?.attributes));
  const other = make("other", "其他");
  other.classList.add("candidate-group-heading");
  other.disabled = true;
  quick.append(other);
  const bucket = document.createElement("div");
  bucket.className = "candidate-bucket-list";
  V2_BUCKETS.forEach((name) => {
    const button = v2MakeButton("bucket", name);
    button.dataset.character = name;
    bucket.append(button);
  });
  quick.append(bucket);
  quick.append(make("full", "新建角色"));
  const marks = document.createElement("div");
  marks.className = "candidate-mark-actions";
  const baseline = v2MakeButton("mark", "标为基准参考形象");
  baseline.dataset.faceMark = "baseline";
  baseline.setAttribute("aria-keyshortcuts", "B");
  const variant = v2MakeButton("mark", "标为变体参考");
  variant.dataset.faceMark = "variant";
  variant.setAttribute("aria-keyshortcuts", "V");
  marks.append(baseline, variant);
  quick.append(marks);
  const actions = document.createElement("div");
  actions.className = "candidate-secondary";
  const reject = make("ignore", "不是");
  reject.title = "忽略此人脸，保留原有排除语义；不是针对某个角色的负参考";
  actions.append(reject, make("skip", "跳过"));
  quick.append(actions);
  const map = document.createElement("p");
  map.className = "candidate-note candidate-shortcuts";
  map.textContent = "1–5 选择 · B 基准 · V 变体 · 方向键 + Enter";
  quick.append(map);
}

function showFullFacePicker() {
  const popover = els("face-popover");
  popover.querySelectorAll("[data-face-full]").forEach((node) => { node.hidden = false; });
  els("face-character-select").value = "";
  v2FocusedCandidate = null;
  els("face-character-name").focus();
  positionFacePopover(els("preview-canvas"));
}

function v2MarkNote(mark) {
  if (mark !== "variant") return "";
  const answer = window.prompt("变体参考备注（可留空）", "");
  return answer === null ? null : answer.trim().slice(0, 160);
}

function recordV2Mark(face, mark) {
  const candidate = v2FocusedCandidate;
  if (!face || !candidate?.character) {
    setText("face-popover-status", "请先聚焦模型枚举或我的命名中的角色候选");
    return false;
  }
  const note = v2MarkNote(mark);
  if (note === null) return false;
  const previous = journal.faceLabels[face.face_id] || null;
  const next = { face_id: face.face_id, image_sha16: String(face.image_sha16 || ""), character: candidate.character, action: "confirm", mark };
  journal.faceLabels[face.face_id] = next;
  journal.faceHistory.push({ face_id: face.face_id, previous, next, mark, note, undone: false });
  journal.entries.push({ kind: "face", face_id: face.face_id, image_sha16: next.image_sha16, character: next.character, action: "confirm", mark, note, filename: rowForFace(face)?.filename || "", timestamp: new Date().toISOString() });
  knownNames.add(candidate.character);
  v2LastMarkFaceId = face.face_id;
  saveJournal();
  renderFaceOverlay();
  renderCharacterPanel();
  renderJournalPreview();
  renderJournalExport();
  updateCharacterSummary();
  v2ShowToast(mark === "baseline" ? "已标为基准参考形象" : "已标为变体参考");
  return true;
}

function v2UndoLastMark() {
  for (let index = journal.faceHistory.length - 1; index >= 0; index -= 1) {
    const entry = journal.faceHistory[index];
    if (!entry.undone && entry.mark && undoFaceLabel(entry.face_id)) {
      v2LastMarkFaceId = null;
      v2ShowToast("已撤销参考形象标记");
      return true;
    }
  }
  return false;
}

function handleFaceQuickClick(event) {
  const target = event.target instanceof Element ? event.target.closest("[data-face-quick]") : null;
  const face = activeFace();
  if (!target || !face) return;
  const action = target.dataset.faceQuick;
  if (action === "full") { showFullFacePicker(); return; }
  if (action === "mark") {
    if (recordV2Mark(face, target.dataset.faceMark || "baseline")) {
      const faceId = face.face_id;
      closeFacePopover();
      advanceToNextUnlabeledFace(faceId);
    }
    return;
  }
  const faceId = face.face_id;
  if (action === "skip") {
    state.candidateSkipped ??= new Set();
    state.candidateSkipped.add(faceId);
  } else if (action === "candidate" || action === "bucket" || action === "other") {
    const character = target.dataset.character || (action === "other" ? "其他" : "");
    if (!character) return;
    recordFaceLabel(face, "confirm", character);
  } else if (action === "ignore") {
    recordFaceLabel(face, "ignore", "");
  } else return;
  closeFacePopover();
  advanceToNextUnlabeledFace(faceId);
}

function handleCandidateKey(event) {
  const popover = els("face-popover");
  if (!popover || popover.hidden) return false;
  if (event.key === "Escape") { event.preventDefault(); closeFacePopover(); return true; }
  if (event.isComposing || event.ctrlKey || event.altKey || event.metaKey) return true;
  const target = event.target;
  if (target instanceof Element && (target.matches("input,textarea,select") || target.isContentEditable)) {
    if (event.key === "Enter" && target.id === "face-character-name") { event.preventDefault(); facePopoverAction("new"); }
    return true;
  }
  if (event.key.toLowerCase() === "b" || event.key.toLowerCase() === "v") {
    event.preventDefault();
    const face = activeFace();
    const mark = event.key.toLowerCase() === "b" ? "baseline" : "variant";
    if (face && recordV2Mark(face, mark)) {
      const faceId = face.face_id;
      closeFacePopover();
      advanceToNextUnlabeledFace(faceId);
    }
    return true;
  }
  if (/^[1-5]$/.test(event.key)) {
    event.preventDefault();
    popover.querySelector(`[data-candidate-index="${Number(event.key) - 1}"]`)?.click();
    return true;
  }
  const choices = [...popover.querySelectorAll("[data-candidate-choice]")];
  if (["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(event.key)) {
    event.preventDefault();
    const direction = ["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1;
    const index = choices.indexOf(document.activeElement);
    choices[(index + direction + choices.length) % choices.length]?.focus();
  }
  return true;
}

function v2NormalizeMemory(value) {
  if (!value || typeof value !== "object") return null;
  const documentValue = { ...value };
  documentValue.characters = Array.isArray(value.characters) ? value.characters.map((raw) => ({
    ...raw,
    name: String(raw?.name || "").trim(),
    origin: String(raw?.origin || "unknown"),
    aliases: Array.isArray(raw?.aliases) ? raw.aliases.map(String) : [],
    baseline_faces: Array.isArray(raw?.baseline_faces) ? raw.baseline_faces.map(String) : [],
    variant_faces: Array.isArray(raw?.variant_faces) ? raw.variant_faces.map((item) => ({ ...item, face_id: String(item?.face_id || ""), note: String(item?.note || "") })) : [],
    assigned_faces: Array.isArray(raw?.assigned_faces) ? raw.assigned_faces.map(String) : [],
    attribute_profile: raw?.attribute_profile && typeof raw.attribute_profile === "object" ? { ...raw.attribute_profile } : {},
    updated_at: String(raw?.updated_at || ""),
  })).filter((item) => item.name) : [];
  return documentValue;
}

function v2MergeCharacters(target, source) {
  target.aliases = [...new Set([...(target.aliases || []), ...(source.aliases || []), source.name])].filter(Boolean);
  target.baseline_faces = [...new Set([...(target.baseline_faces || []), ...(source.baseline_faces || [])])];
  const variants = [...(target.variant_faces || []), ...(source.variant_faces || [])];
  target.variant_faces = [...new Map(variants.map((item) => [item.face_id, item])).values()];
  target.assigned_faces = [...new Set([...(target.assigned_faces || []), ...(source.assigned_faces || [])])];
  return target;
}

function v2MemoryCharacters() {
  const entries = new Map();
  const add = (raw, origin = "model") => {
    const name = String(raw?.name || raw || "").trim();
    if (!name) return;
    if (!entries.has(name)) entries.set(name, { name, origin, aliases: [], baseline_faces: [], variant_faces: [], assigned_faces: [], attribute_profile: {}, updated_at: "" });
    if (raw && typeof raw === "object") v2MergeCharacters(entries.get(name), v2NormalizeMemory({ characters: [raw] }).characters[0]);
  };
  v2MemoryDocument?.characters?.forEach((item) => add(item, item.origin || "memory"));
  knownNames.forEach((name) => add(name, "model"));
  identityFaces.forEach((face) => (Array.isArray(v2Evidence(face)?.candidates) ? v2Evidence(face).candidates : []).forEach((candidate) => {
    if (["model", "memory", "anchor"].includes(v2CandidateSource(candidate))) add(v2CandidateName(candidate), v2CandidateSource(candidate));
  }));
  Object.values(journal.faceLabels).forEach((label) => { if (label?.character) add(label.character, label.action === "new" ? "user" : "memory"); });
  journal.entries.filter((entry) => entry.kind === "memory").forEach((entry) => {
    const from = String(entry.from || "");
    const to = String(entry.to || "");
    if (entry.action === "import" && entry.memory) {
      entries.clear();
      v2NormalizeMemory(entry.memory)?.characters?.forEach((item) => add(item, item.origin || "memory"));
    } else if (entry.action === "rename" && from && to && entries.has(from)) {
      const item = entries.get(from); entries.delete(from); item.name = to; add(item, item.origin);
    } else if (entry.action === "merge" && from && to && entries.has(from)) {
      const source = entries.get(from); entries.delete(from); add(to, "memory"); v2MergeCharacters(entries.get(to), source);
    } else if (entry.action === "delete" && from) entries.delete(from);
  });
  Object.values(journal.faceLabels).forEach((label) => {
    const item = entries.get(label?.character);
    if (!item) return;
    if (label.mark === "baseline") item.baseline_faces = [...new Set([...item.baseline_faces, label.face_id])];
    if (label.mark === "variant" && !item.variant_faces.some((variant) => variant.face_id === label.face_id)) item.variant_faces.push({ face_id: label.face_id, note: "" });
    if (label.action === "confirm" || label.action === "new") item.assigned_faces = [...new Set([...item.assigned_faces, label.face_id])];
  });
  return [...entries.values()].sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));
}

function v2MemoryDocumentForExport() {
  const documentValue = v2MemoryDocument ? { ...v2MemoryDocument } : { version: 1 };
  documentValue.characters = v2MemoryCharacters().map((item) => ({ ...item, aliases: [...(item.aliases || [])].filter((alias) => alias !== item.name) }));
  return documentValue;
}

function v2RenderMemoryPanel() {
  const list = els("character-memory-list");
  if (!list) return;
  const fragment = document.createDocumentFragment();
  const characters = v2MemoryCharacters();
  characters.forEach((character) => {
    const card = document.createElement("article"); card.className = "memory-character-card";
    const heading = document.createElement("div"); heading.className = "memory-character-heading";
    const name = document.createElement("h3"); name.textContent = character.name;
    const origin = document.createElement("span"); origin.className = "memory-origin"; origin.textContent = ["user", "memory"].includes(character.origin) ? "我的命名" : "模型已知";
    heading.append(name, origin); card.append(heading);
    const counts = document.createElement("p"); counts.className = "memory-counts";
    counts.textContent = `基准 ${character.baseline_faces.length} · 变体 ${character.variant_faces.length} · 指派 ${character.assigned_faces.length}`;
    card.append(counts);
    const actions = document.createElement("div"); actions.className = "memory-card-actions";
    [["rename", "重命名"], ["merge", "合并到…"], ["delete", "删除"]].forEach(([action, label]) => {
      const button = document.createElement("button"); button.type = "button"; button.className = "memory-action"; button.dataset.memoryAction = action; button.dataset.memoryName = character.name; button.textContent = label; actions.append(button);
    });
    card.append(actions); fragment.append(card);
  });
  if (!characters.length) { const empty = document.createElement("p"); empty.className = "memory-empty"; empty.textContent = "暂无人物记忆"; fragment.append(empty); }
  list.replaceChildren(fragment);
  setText("character-memory-summary", `${characters.length} 个角色 · 操作只写入本地日志`);
}

function v2RecordMemoryOperation(operation) {
  journal.entries.push({ kind: "memory", ...operation, timestamp: new Date().toISOString() });
  saveJournal(); v2RenderMemoryPanel(); renderJournalPreview(); renderJournalExport();
}

function v2MemoryExport() {
  download("character-memory.json", JSON.stringify(v2MemoryDocumentForExport(), null, 2), "application/json");
  download("character-memory-journal.json", JSON.stringify({ version: 1, source: "review-studio", corpus_fingerprint: fingerprint, entries: journal.entries }, null, 2), "application/json");
  setText("character-memory-status", "已导出 character-memory.json 与动作日志");
}

function v2MemoryImport(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || ""));
      const memory = parsed?.characters ? parsed : parsed?.memory;
      const normalized = v2NormalizeMemory(memory);
      if (!normalized) throw new Error("文件不是 character-memory.json v1");
      v2MemoryDocument = normalized;
      v2RecordMemoryOperation({ action: "import", memory: normalized });
      setText("character-memory-status", "已导入人物记忆；历史动作仍由管线应用");
      v2ShowToast("人物记忆已导入");
    } catch (error) { setText("character-memory-status", error instanceof Error ? error.message : "人物记忆无法读取"); }
  };
  reader.onerror = () => setText("character-memory-status", "人物记忆无法读取");
  reader.readAsText(file, "utf-8");
}

function v2OpenMemoryPanel() {
  const panel = els("character-memory-panel"); const backdrop = els("character-memory-backdrop");
  if (!panel || !backdrop) return;
  window.clearTimeout(Number(panel.dataset.closeTimer || 0));
  panel.inert = false;
  panel.hidden = false; backdrop.hidden = false; panel.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => panel.classList.add("is-open")); v2RenderMemoryPanel(); els("character-memory-close")?.focus();
}

function v2CloseMemoryPanel() {
  const panel = els("character-memory-panel"); const backdrop = els("character-memory-backdrop");
  if (!panel || panel.hidden) return;
  els("character-memory-open")?.focus();
  panel.classList.remove("is-open"); panel.setAttribute("aria-hidden", "true"); panel.inert = true;
  panel.dataset.closeTimer = String(window.setTimeout(() => {
    if (panel.getAttribute("aria-hidden") === "true") { panel.hidden = true; backdrop.hidden = true; }
  }, 220));
}

function v2HandleMemoryClick(event) {
  const target = event.target instanceof Element ? event.target.closest("[data-memory-action]") : null;
  if (!target) return;
  const action = target.dataset.memoryAction; const name = target.dataset.memoryName || "";
  if (action === "export") { v2MemoryExport(); return; }
  if (action === "import") { els("character-memory-file")?.click(); return; }
  if (action === "rename") {
    const next = window.prompt("重命名人物", name)?.trim();
    if (next && next !== name) { v2RecordMemoryOperation({ action: "rename", from: name, to: next }); v2ShowToast("人物已记录重命名"); }
  } else if (action === "merge") {
    const targetName = window.prompt("合并到哪个人物？", "")?.trim();
    if (targetName && targetName !== name && window.confirm("合并会重新归属视觉记忆与历史指派，确定继续？")) { v2RecordMemoryOperation({ action: "merge", from: name, to: targetName, warning: "visual-memory-and-history-re-attribution" }); v2ShowToast("已记录合并操作"); }
  } else if (action === "delete" && window.confirm("删除只写入本地操作日志，管线稍后应用。确定删除？")) { v2RecordMemoryOperation({ action: "delete", from: name }); v2ShowToast("已记录删除操作"); }
}

function v2EnsureMemoryPanel() {
  const hasMemory = Boolean(v2MemoryDocument || identityEnabled || knownNames.size);
  if (!hasMemory) return;
  let button = els("character-memory-open");
  if (!button) {
    button = document.createElement("button"); button.type = "button"; button.id = "character-memory-open"; button.className = "control-button"; button.textContent = "人物记忆";
    els("journal-open")?.after(button);
  }
  button.hidden = false; button.addEventListener("click", v2OpenMemoryPanel);
  if (!els("character-memory-panel")) {
    const backdrop = document.createElement("div"); backdrop.id = "character-memory-backdrop"; backdrop.className = "drawer-backdrop"; backdrop.hidden = true;
    const panel = document.createElement("aside"); panel.id = "character-memory-panel"; panel.className = "character-memory-panel"; panel.hidden = true; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-modal", "true"); panel.setAttribute("aria-labelledby", "character-memory-title"); panel.setAttribute("aria-hidden", "true");
    panel.innerHTML = '<div class="memory-header"><div><p class="panel-kicker">人物关系 · 本地日志</p><h2 id="character-memory-title">人物记忆</h2><p>模型已知和我的命名都可维护；管线负责应用这些操作。</p></div><button class="close-button" id="character-memory-close" type="button">关闭</button></div><div class="memory-toolbar"><span id="character-memory-summary">—</span><button class="journal-button" data-memory-action="export" type="button">导出</button><button class="journal-button" data-memory-action="import" type="button">导入</button><input class="import-input" id="character-memory-file" type="file" accept="application/json,.json" aria-label="导入人物记忆 JSON 文件"><p id="character-memory-status" class="memory-status" aria-live="polite"></p></div><div id="character-memory-list" class="character-memory-list"></div>';
    document.body.append(backdrop, panel); backdrop.addEventListener("click", v2CloseMemoryPanel); panel.addEventListener("click", v2HandleMemoryClick); els("character-memory-close").addEventListener("click", v2CloseMemoryPanel); els("character-memory-file").addEventListener("change", (event) => { v2MemoryImport(event.target.files?.[0] || null); event.target.value = ""; });
  }
  v2RenderMemoryPanel();
}

function v2CharacterLabelsPayload() {
  return { version: 1, source: "review-studio", corpus_fingerprint: fingerprint, labels: Object.values(journal.faceLabels).filter((label) => label && LABEL_ACTIONS.has(label.action)).map((label) => {
    const output = { face_id: String(label.face_id || ""), image_sha16: String(label.image_sha16 || ""), character: String(label.character || ""), action: label.action };
    if (["baseline", "variant"].includes(label.mark)) output.mark = label.mark;
    return output;
  }) };
}

function v2ExportCharacterLabels(event) {
  event.stopImmediatePropagation();
  download("character_labels.json", JSON.stringify(v2CharacterLabelsPayload(), null, 2), "application/json");
  setText("journal-import-status", "人物标签已导出（含可选基准 / 变体标记）");
}

function v2ImportCharacterLabels(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || ""));
      if (!parsed || parsed.version !== 1 || parsed.source !== "review-studio" || String(parsed.corpus_fingerprint) !== fingerprint || !Array.isArray(parsed.labels)) throw new Error("标签文件与当前语料不匹配");
      let imported = 0;
      parsed.labels.forEach((raw) => {
        if (!raw || typeof raw !== "object" || !LABEL_ACTIONS.has(raw.action)) return;
        const face = faceById.get(String(raw.face_id || "")); if (!face) return;
        const label = { face_id: face.face_id, image_sha16: String(raw.image_sha16 || face.image_sha16 || ""), character: String(raw.character || ""), action: raw.action };
        if (["baseline", "variant"].includes(raw.mark)) label.mark = raw.mark;
        journal.faceLabels[face.face_id] = label; if (label.character) knownNames.add(label.character); imported += 1;
      });
      journal.entries.push({ kind: "face", action: "import", count: imported, timestamp: new Date().toISOString() }); saveJournal(); renderFaceOverlay(); renderCharacterPanel(); renderJournalPreview(); renderJournalExport(); v2RenderMemoryPanel(); setText("journal-import-status", `已导入 ${imported} 张人物标签`);
    } catch (error) { setText("journal-import-status", error instanceof Error ? error.message : "标签文件无法读取"); }
  };
  reader.onerror = () => setText("journal-import-status", "标签文件无法读取"); reader.readAsText(file, "utf-8");
}

function installV2CandidateContract() {
  v2MemoryDocument = v2NormalizeMemory(columnar.m);
  v2EnsureMemoryPanel();
  const shortcutList = document.querySelector("#help-modal .shortcut-list");
  if (shortcutList && !shortcutList.querySelector("[data-v2-shortcut]")) {
    [["标为基准参考形象", "B"], ["标为变体参考（弹出备注）", "V"]].forEach(([label, key]) => {
      const item = document.createElement("div"); item.className = "shortcut-item"; item.dataset.v2Shortcut = "true";
      const name = document.createElement("span"); name.textContent = label; const code = document.createElement("kbd"); code.textContent = key;
      item.append(name, code); shortcutList.append(item);
    });
  }
  els("export-character-labels")?.addEventListener("click", v2ExportCharacterLabels, true);
  els("character-labels-file")?.addEventListener("change", (event) => { event.stopImmediatePropagation(); v2ImportCharacterLabels(event.target.files?.[0] || null); event.target.value = ""; }, true);
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = event.isComposing || target instanceof Element && (target.matches("input,textarea,select") || target.isContentEditable);
    if (!typing && event.key === "Escape" && !els("character-memory-panel")?.hidden) { event.preventDefault(); event.stopImmediatePropagation(); v2CloseMemoryPanel(); return; }
    if (!typing && event.key.toLowerCase() === "u" && v2UndoLastMark()) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
}

installV2CandidateContract();
