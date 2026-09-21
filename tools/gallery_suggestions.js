// Presentation only: no suggestion ever writes the human decision journal.
function renderSuggestionTiers(evidence) {
  const container = document.createElement("div");
  container.className = "suggestion-tiers";
  const verified = evidence?.suggested_verified ?? evidence?.suggested;
  const model = evidence?.suggested_model;
  const demoted = Boolean(evidence?.model_demoted || evidence?.disagreements?.length);
  const badge = (tier, text) => {
    const node = document.createElement("p");
    node.className = `candidate-note suggestion-badge suggestion-${tier}`;
    node.textContent = text;
    return node;
  };
  const verifiedName = typeof verified === "string" ? verified : v2CandidateName(verified);
  if (verifiedName) {
    container.append(badge("verified", `已核实建议：${verifiedName} · 参考/记忆门禁通过，仍需人工确认`));
  } else if (!model || demoted) {
    container.append(badge("empty", demoted ? "证据冲突 · 暂不推荐模型结果，请人工选择" : "暂无建议 · 仍可人工选择"));
  }
  if (model) {
    const score = Number(model.score).toFixed(3);
    const margin = Number(model.margin_vs_runner_up).toFixed(3);
    const bound = model.margin_basis === "runner-up-upper-bound-0.35" ? "≥" : "";
    const modelBadge = badge("model", `模型建议（未核实）：${v2CandidateName(model)} · 分数 ${score} · 间隔 ${bound}+${margin}`);
    modelBadge.dataset.primary = String(!verifiedName && !demoted);
    if (demoted) {
      const details = document.createElement("details");
      details.className = "suggestion-conflict";
      const summary = document.createElement("summary");
      summary.textContent = "模型建议已降级 · 与参考/记忆证据不一致";
      details.append(summary, modelBadge);
      for (const conflict of evidence.disagreements || []) {
        const line = document.createElement("p");
        line.className = "candidate-note";
        line.textContent = `${conflict.source} → ${conflict.evidence_name} · 证据分数 ${Number(conflict.score).toFixed(3)}`;
        details.append(line);
      }
      container.append(details);
    } else {
      container.append(modelBadge);
    }
  }
  const honesty = document.createElement("p");
  honesty.className = "candidate-note candidate-honesty";
  honesty.textContent = "模型建议来自 WD 分数与间隔，未经核实、可能认错；已核实建议仅表示参考/记忆门禁通过，不等于人工确认。间隔 ≥ 为保守下界。模型枚举不限于已建档角色。";
  container.append(honesty);
  return container;
}
