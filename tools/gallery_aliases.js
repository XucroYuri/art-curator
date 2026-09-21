// Human-only alias journal. No draft changes the embedded model suggestions.
function installAliasReview() {
  const evidence = columnar.y?.alias_reconciliation;
  if (!evidence || evidence.version !== 1 || !Array.isArray(evidence.banks)) return;
  const key = `artcurator-alias-v1:${evidence.corpus_fingerprint}:${evidence.semantic_profile}`;
  const pairs = evidence.banks.flatMap((bank) => bank.candidates.map((candidate) => ({ bank, candidate })));
  const pairKey = (pair) => JSON.stringify([pair.bank.reference_name, pair.candidate.wd_tag]);
  const drafts = new Map();
  let storageError = "";
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "[]");
    if (!Array.isArray(saved)) throw new Error("别名草稿格式无效");
    for (const pair of pairs) {
      const draft = saved.find((item) => item?.key === pairKey(pair));
      if (draft && ["confirmed", "rejected"].includes(draft.decision)
          && draft.base === pair.candidate.decision) drafts.set(draft.key, draft);
    }
  } catch (error) {
    storageError = error instanceof Error ? `无法读取别名草稿：${error.message}` : "无法读取别名草稿";
  }
  const trigger = document.createElement("button");
  trigger.type = "button"; trigger.id = "alias-review-open"; trigger.className = "control-button";
  trigger.textContent = `别名核对 (${pairs.length})`;
  els("character-memory-open")?.after(trigger);
  if (!trigger.isConnected) els("journal-open")?.after(trigger);
  const dialog = document.createElement("dialog");
  dialog.id = "alias-review-dialog"; dialog.className = "alias-review-dialog";
  dialog.setAttribute("aria-labelledby", "alias-review-title");
  dialog.innerHTML = '<header class="memory-header"><div><p class="panel-kicker">命名空间 · 人工核对</p><h2 id="alias-review-title">参考名 ↔ WD 标签</h2></div><button type="button" class="close-button" data-alias-close>关闭</button></header><div class="memory-toolbar"><p class="candidate-note">共现不等于同一角色。确认只建立别名，不核实每张图片；拒绝不会推广建议。</p><p class="candidate-note">决定暂存本浏览器。请导出 alias-decisions.json，再由本地 API 应用到人物记忆并重建图库；当前建议不会即时改变。</p><button type="button" class="journal-button" id="alias-decisions-export">导出别名决定</button><p id="alias-review-status" class="memory-status" role="status" aria-live="polite"></p></div><div class="alias-review-body"></div>';
  document.body.append(dialog);
  const body = dialog.querySelector(".alias-review-body");
  const status = dialog.querySelector("#alias-review-status");
  const controls = new Map();
  const stateText = (pair) => {
    const draft = drafts.get(pairKey(pair));
    const value = draft?.decision || pair.candidate.decision;
    const label = { unconfirmed: "未确认", confirmed: "已确认别名", rejected: "已拒绝别名" }[value];
    return `${label} · ${draft ? "浏览器待应用" : value === "unconfirmed" ? "仅提案" : "人物记忆已保存"}`;
  };
  const metric = (support) => {
    const values = [support.minimum, support.p25, support.median, support.p75, support.maximum];
    return values.map((value) => typeof value === "number" ? value.toFixed(3) : "—").join(" / ");
  };
  const renderState = (pair) => {
    const entry = controls.get(pairKey(pair));
    const value = drafts.get(pairKey(pair))?.decision || pair.candidate.decision;
    entry.state.textContent = stateText(pair);
    entry.card.dataset.aliasState = value;
    entry.buttons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.aliasDecision === value)));
  };
  for (const bank of evidence.banks) {
    const section = document.createElement("section"); section.className = "alias-bank";
    const heading = document.createElement("h3"); heading.textContent = bank.reference_name;
    const note = document.createElement("p"); note.className = "candidate-note";
    note.textContent = `直接参考 ${bank.reference_images} 图（有 WD ${bank.tagged_reference_images}） · 弱检索队列 ${bank.cohort_images} 图（有 WD ${bank.tagged_cohort_images}）`;
    section.append(heading, note);
    if (!bank.candidates.length) {
      const empty = document.createElement("p"); empty.className = "memory-empty";
      empty.textContent = "暂无可观察的 WD 共现；不猜测别名。"; section.append(empty);
    }
    for (const candidate of bank.candidates) {
      const pair = { bank, candidate };
      const card = document.createElement("article"); card.className = "memory-character-card alias-card";
      const title = document.createElement("h4"); title.textContent = `#${candidate.rank} ${candidate.wd_tag}`;
      const state = document.createElement("p"); state.className = "alias-state";
      const direct = document.createElement("p"); direct.className = "candidate-note";
      direct.textContent = `直接共现 ${candidate.direct.images}/${bank.tagged_reference_images} 图 · top-1 ${candidate.direct.top1_images} 图 · min / P25 / 中位 / P75 / max：${metric(candidate.direct)}`;
      const cohort = document.createElement("p"); cohort.className = "candidate-note";
      cohort.textContent = `弱队列共现 ${candidate.cohort.images}/${bank.tagged_cohort_images} 图 · top-1 ${candidate.cohort.top1_images} 图 · 分布：${metric(candidate.cohort)}`;
      const warning = document.createElement("p"); warning.className = "candidate-note alias-warning";
      warning.textContent = candidate.strength === "relatively-strong"
        ? "相对较强：≥3 直接图、共现≥80%、中位≥.85；仍需人工核对，不代表准确率。"
        : "弱证据：直接样本不足或不集中。检索队列并非参考原图，可能跨角色混淆。";
      const censor = document.createElement("p"); censor.className = "candidate-note";
      censor.textContent = "按图片去重，每图取最高 crop 分数；仅观察 WD 保留的 >.35 标签，缺失不表示零分。";
      const actions = document.createElement("div"); actions.className = "memory-card-actions";
      const buttons = [];
      for (const [value, label] of [["confirmed", "确认同一角色"], ["rejected", "拒绝此别名"]]) {
        const button = document.createElement("button"); button.type = "button"; button.className = "memory-action";
        button.dataset.aliasDecision = value; button.textContent = label;
        button.setAttribute("aria-label", `${label}：${bank.reference_name} ↔ ${candidate.wd_tag}`);
        button.addEventListener("click", () => {
          drafts.set(pairKey(pair), { key: pairKey(pair), base: candidate.decision, decision: value,
            reference_name: bank.reference_name, wd_tag: candidate.wd_tag });
          try {
            localStorage.setItem(key, JSON.stringify([...drafts.values()]));
            status.textContent = `${bank.reference_name} ↔ ${candidate.wd_tag}：${label}，已暂存；请导出并应用。`;
          } catch (error) {
            status.textContent = error instanceof Error ? `未持久保存，请立即导出：${error.message}` : "未持久保存，请立即导出";
          }
          renderState(pair);
        });
        buttons.push(button); actions.append(button);
      }
      card.append(title, state, direct, cohort, warning, censor, actions); section.append(card);
      controls.set(pairKey(pair), { card, state, buttons }); renderState(pair);
    }
    body.append(section);
  }
  if (!evidence.banks.length) body.textContent = "没有可核对的参考库；无需创建别名。";
  status.textContent = storageError || `${drafts.size} 个浏览器决定待应用；提案不会自动成为别名。`;
  const close = () => { dialog.close(); trigger.focus(); };
  dialog.querySelector("[data-alias-close]").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  trigger.addEventListener("click", () => { dialog.showModal(); dialog.querySelector("[data-alias-close]").focus(); });
  window.addEventListener("keydown", (event) => {
    if (!dialog.open) return;
    // Stop gallery capture handlers too, without preventing native Tab/button defaults.
    event.stopImmediatePropagation();
    if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (!["Tab", "Enter", " "].includes(event.key)) event.preventDefault();
  }, true);
  dialog.querySelector("#alias-decisions-export").addEventListener("click", () => {
    const decisions = [...drafts.values()].map(({ reference_name, wd_tag, decision }) =>
      ({ reference_name, wd_tag, decision }));
    download("alias-decisions.json", JSON.stringify({ version: 1, source: "review-studio",
      corpus_fingerprint: evidence.corpus_fingerprint, semantic_profile: evidence.semantic_profile, decisions }, null, 2), "application/json");
    status.textContent = `已导出 ${decisions.length} 对；尚未应用到磁盘人物记忆。`;
  });
}
installAliasReview();
