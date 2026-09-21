// Export-only G2 surface. No receipt, mapping mutation or affirmative persistence.
function parseNegotiationReport(value) {
  const hash = /^[0-9a-f]{64}$/;
  if (!value || value.schema_version !== "album-negotiation-v1") throw new Error("报告版本不可用");
  for (const key of ["report_digest", "snapshot_digest", "profile_digest", "analysis_profile_digest", "seal_digest"])
    if (!hash.test(value[key])) throw new Error(`报告绑定不可用：${key}`);
  for (const key of ["folders", "clusters", "eligible_cluster_ids", "remaining_cluster_ids", "limitations", "members"])
    if (!Array.isArray(value[key])) throw new Error(`报告字段不可用：${key}`);
  const presentation = value.presentation;
  if (!presentation || presentation.affirmative_required !== true) throw new Error("报告缺少显式同意约束");
  for (const key of ["ingest_prompt", "coherent_clusters", "purity_missing", "inheritance_warning", "auto_warning",
    "model_tier", "reference_tier", "conflict", "confirmation", "commit_action", "dismiss", "undo", "g2_boundary"])
    if (typeof presentation.text?.[key] !== "string" || /[{}]/.test(presentation.text[key])) throw new Error(`文案未绑定：${key}`);
  for (const [key, ids] of [["modes", ["human-first", "auto-first", "inherit-only"]], ["scopes", ["all", "selected", "none"]]]) {
    if (presentation[key]?.length !== ids.length || !ids.every((id) => presentation[key].filter((v) => v.id === id).length === 1))
      throw new Error(`选项不可用：${key}`);
    if (!presentation[key].every((v) => typeof v.label === "string" && Array.isArray(v.consequences) && typeof v.available === "boolean"))
      throw new Error(`选项后果不可用：${key}`);
  }
  if (new Set(value.folders.map((f) => f.folder_id)).size !== value.folders.length) throw new Error("目录 ID 重复");
  for (const folder of value.folders)
    if (!hash.test(folder.folder_id) || typeof presentation.folder_text?.[folder.folder_id] !== "string"
        || /[{}]/.test(presentation.folder_text[folder.folder_id])) throw new Error("目录证据文案不可用");
  return value;
}
function installNegotiation() {
  const tab = negNode("button", "整理方式", "mode-button"); tab.id = "negotiation-mode"; tab.type = "button";
  tab.setAttribute("role", "tab"); tab.setAttribute("aria-selected", "false"); tab.setAttribute("aria-controls", "negotiation-view");
  document.querySelector(".mode-switch").append(tab);
  const view = negNode("section", undefined, "negotiation-view"); view.id = "negotiation-view"; view.hidden = true;
  view.setAttribute("role", "tabpanel"); view.setAttribute("aria-labelledby", tab.id); els("main-region").append(view);
  let report = null; let phase = "waiting"; let staleDigest = null;
  let form = null; let ack = null; let exportButton = null; let status = null; let preview = null;
  const selected = (name) => form?.querySelector(`input[name="${name}"]:checked`)?.value;
  const phaseText = {
    waiting: "等待明确决定 · 尚未同意。关闭、离开或超时都不会生成 Decision。",
    dismissed: "已退出本次决定 · 不代表同意；本次不生成新 Decision，也未提交 CLI。已下载文件不会被撤回。",
    stale: "报告已过期 · 导出已锁定。请加载新报告、重新审阅并明确同意；已有同意须先由 CLI 撤回。",
    exported: "Decision 已导出 · 尚未提交 CLI，不是同意回执；未建立映射。",
  };
  const folderRows = () => [...form.querySelectorAll(".neg-folder-choice")];
  function update() {
    if (!form) return;
    const scope = selected("neg-scope");
    for (const row of folderRows()) {
      const check = row.querySelector("input"); check.disabled = scope !== "selected";
      const active = scope === "all" || scope === "selected" && check.checked;
      row.querySelectorAll("select").forEach((control) => { control.disabled = !active; });
    }
    const hasFolders = scope === "none" || folderRows().some((row) => scope === "all" || row.querySelector("input").checked);
    exportButton.disabled = phase === "stale" || !ack.checked || !selected("neg-mode") || !scope || !hasFolders;
    status.textContent = phaseText[phase]; view.dataset.negotiationState = phase;
    els("neg-auto-warning").hidden = selected("neg-mode") !== "auto-first";
    els("neg-browse-only").hidden = selected("neg-mode") !== "inherit-only" || scope !== "none";
  }
  function dismiss() {
    if (!report || !form) return;
    if (phase !== "stale") phase = "dismissed";
    ack.checked = false; preview.replaceChildren(); update();
    status.focus();
  }
  function invalidate() {
    staleDigest = report?.report_digest; phase = "stale";
    if (ack) ack.checked = false;
    preview?.replaceChildren(); update();
  }
  const header = negNode("header", undefined, "neg-header");
  const heading = negNode("div"); heading.append(negNode("p", "G2 / 模式协商", "neg-kicker"), negNode("h2", "决定如何整理，而不是开始执行"));
  const importLabel = negNode("label", "加载本地报告 JSON ");
  const importer = negNode("input"); importer.type = "file"; importer.accept = ".json,application/json"; importer.id = "neg-report-file";
  importLabel.append(importer); header.append(heading, importLabel);
  const content = negNode("div"); view.append(header, content);
  const importStatus = negNode("p", "离线快照无法监测外部变更；CLI 将重新校验绑定。", "neg-warning");
  importStatus.setAttribute("role", "status"); header.append(importStatus);
  function choiceGroup(name, title, choices, defaultId) {
    const fieldset = negNode("fieldset"); fieldset.append(negNode("legend", title));
    for (const choice of choices) {
      const label = negNode("label", undefined, "neg-option");
      const input = negNode("input"); input.type = "radio"; input.name = name; input.value = choice.id;
      input.checked = choice.id === defaultId; input.disabled = !choice.available;
      label.append(input, negNode("span", choice.label), negList(choice.consequences)); fieldset.append(label);
    }
    return fieldset;
  }
  function folderChoice(folder) {
    const row = negNode("div", undefined, "neg-folder-choice"); row.dataset.folderId = folder.folder_id;
    const label = negNode("label"); const check = negNode("input"); check.type = "checkbox"; check.value = folder.folder_id;
    label.append(check, negNode("span", folder.path)); row.append(label);
    for (const [name, title, values] of [["relation_type", "关系类型", ["undetermined", "work", "artist", "original-series", "character", "ordinary-person"]],
      ["descendants", "后代范围", ["current-snapshot", "direct-only"]]]) {
      const wrapper = negNode("label", `${title} · ${folder.path}`); const select = negNode("select"); select.name = name;
      values.forEach((value) => { const option = negNode("option", value); option.value = value; select.append(option); });
      wrapper.append(select); row.append(wrapper);
    }
    return row;
  }
  function render() {
    form = null; content.replaceChildren();
    if (!report) { content.append(negNode("p", "报告不可用 · 尚未载入冻结测量。请加载 ingest-negotiate 输出；不会推断同意。", "neg-status")); return; }
    const p = report.presentation; const copy = p.text;
    content.append(negNode("p", copy.ingest_prompt, "neg-prompt"));
    status = negNode("p", "", "neg-status"); status.id = "neg-status"; status.tabIndex = -1; status.setAttribute("role", "status"); content.append(status);
    const layout = negNode("div", undefined, "neg-layout");
    const assets = report.report_digest === columnar.ng?.report_digest ? columnar.na || {} : {};
    layout.append(renderNegotiationReport(report, assets));
    form = negNode("form", undefined, "neg-choices"); form.addEventListener("submit", (event) => event.preventDefault());
    const choices = negNode("section", undefined, "neg-card"); choices.append(negNode("p", "03 / 选择与后果", "neg-kicker"), negNode("h3", "选择不会自动授权"));
    choices.append(choiceGroup("neg-mode", "工作方式", p.modes, p.default_mode));
    const auto = negNode("p", copy.auto_warning, "neg-warning"); auto.id = "neg-auto-warning"; choices.append(auto);
    choices.append(choiceGroup("neg-scope", "目录继承范围", p.scopes, p.default_scope), negNode("p", copy.inheritance_warning, "neg-warning"));
    const browse = negNode("p", "仅浏览源目录：不会成功分类，也不会创建继承关系。", "neg-warning"); browse.id = "neg-browse-only"; choices.append(browse);
    choices.append(negNode("p", "当前快照之外的未来文件不在范围内。关系类型未选定时保持 undetermined。"));
    report.folders.forEach((folder) => choices.append(folderChoice(folder))); form.append(choices);
    const confirm = negNode("section", undefined, "neg-card"); confirm.append(negNode("p", "04 / 审阅并导出", "neg-kicker"), negNode("h3", "只导出 Decision，不应用"));
    confirm.append(negNode("p", copy.confirmation), negNode("p", report.prediction.reason, "neg-warning"), negEvidence(report.prediction));
    confirm.append(negNode("h4", "必须知悉的限制"), negList(report.limitations));
    const actorLabel = negNode("label", "本地操作者 ID "); const actor = negNode("input"); actor.id = "neg-actor"; actor.value = "local:review-studio"; actor.required = true;
    actorLabel.append(actor); confirm.append(actorLabel);
    const ackLabel = negNode("label", undefined, "neg-option"); ack = negNode("input"); ack.type = "checkbox"; ack.id = "neg-ack";
    ackLabel.append(ack, negNode("span", "我已阅读全部限制及所选后果，明确同意导出本次选择。")); confirm.append(ackLabel);
    const actions = negNode("div", undefined, "neg-actions");
    exportButton = negNode("button", "明确同意并导出 Decision", "neg-export"); exportButton.type = "button"; exportButton.id = "neg-export";
    exportButton.addEventListener("click", () => {
      update(); if (exportButton.disabled || !actor.reportValidity() || !actor.value.trim()) return;
      const scope = selected("neg-scope");
      const folders = folderRows().filter((row) => scope === "all" || scope === "selected" && row.querySelector("input").checked)
        .map((row) => ({folder_id: row.dataset.folderId, relation_type: row.querySelector('[name="relation_type"]').value,
          descendants: row.querySelector('[name="descendants"]').value}));
      const decision = {actor: actor.value.trim(), operation_id: crypto.randomUUID(), affirmative: true,
        report_digest: report.report_digest, snapshot_digest: report.snapshot_digest, profile_digest: report.profile_digest,
        mode: selected("neg-mode"), inheritance: scope, folders, threshold_overrides: [], cost_ceiling_seconds: 0,
        acknowledged: [...report.limitations]};
      const json = JSON.stringify(decision, null, 2);
      download("decision.json", json, "application/json"); preview.replaceChildren(negNode("pre", json, "neg-json"));
      phase = "exported"; ack.checked = false; update();
    });
    const dismissButton = negNode("button", copy.dismiss); dismissButton.type = "button"; dismissButton.id = "neg-dismiss"; dismissButton.addEventListener("click", dismiss);
    const stale = negNode("button", "标记报告已过期"); stale.type = "button"; stale.id = "neg-stale"; stale.addEventListener("click", invalidate);
    actions.append(exportButton, dismissButton, stale); confirm.append(actions);
    const locked = negNode("div", undefined, "neg-actions");
    for (const key of ["commit_action", "undo"]) {
      const button = negNode("button", copy[key]); button.type = "button"; button.disabled = true; button.setAttribute("aria-describedby", "neg-boundary"); locked.append(button);
    }
    confirm.append(locked, negNode("p", `mapping_action_available = ${p.mapping_action_available} · ${p.mapping_action_available ? "本离线客户端仍不执行映射" : "映射不可用"} · G5 批次撤销未实现`, "neg-warning"));
    const boundary = negNode("p", copy.g2_boundary); boundary.id = "neg-boundary"; confirm.append(boundary);
    confirm.append(negNode("p", "导出不等于 CLI 已记录同意，也不授权目录上下文使用。成本上限记录为 0；G2 不执行、不估算成本。"),
      negNode("code", "ingest-confirm --corpus <corpus> --decision decision.json"));
    preview = negNode("div"); preview.id = "neg-decision-preview"; confirm.append(preview); form.append(confirm);
    form.addEventListener("change", (event) => {
      if (event.target !== ack) ack.checked = false;
      if (phase !== "stale") phase = "waiting";
      preview.replaceChildren(); update();
    });
    layout.append(form); content.append(layout); update();
  }
  function load(value) {
    const next = parseNegotiationReport(value);
    if (staleDigest === next.report_digest) throw new Error("仍是过期报告；需要不同 report_digest 的新报告");
    report = next; phase = "waiting"; render();
  }
  importer.addEventListener("change", async () => {
    const file = importer.files[0]; if (!file) return;
    if (report) invalidate();
    try { load(JSON.parse(await file.text())); importStatus.textContent = "新报告已加载；旧选择已清空，必须重新同意。CLI 仍会检查是否过期。"; }
    catch (error) { form = null; report = null; render(); importStatus.textContent = `导出已锁定：${error instanceof Error ? error.message : "报告不可用"}`; }
    importer.value = "";
  });
  tab.addEventListener("click", () => setMode("negotiation"));
  document.addEventListener("keydown", (event) => {
    if (state.mode === "negotiation" && event.key === "Escape") { event.preventDefault(); dismiss(); }
  });
  const tabs = document.querySelector(".mode-switch");
  tabs.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const buttons = [...tabs.querySelectorAll('[role="tab"]')].filter((button) => !button.hidden);
    const current = buttons.indexOf(document.activeElement); if (current < 0) return;
    event.preventDefault(); event.stopPropagation();
    const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
      : (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[index].focus(); buttons[index].click();
  });
  try { if (columnar.ng) load(columnar.ng); else render(); }
  catch (error) { report = null; render(); importStatus.textContent = `导出已锁定：${error instanceof Error ? error.message : "报告不可用"}`; }
}
installNegotiation();
