// Embedded in the studio boot scope; no network or independent journal schema.
function renderFaceQuickActions(face) {
  const popover = els("face-popover");
  let quick = popover.querySelector(".face-quick-actions");
  if (!quick) {
    quick = document.createElement("div");
    quick.className = "face-quick-actions";
    popover.insertBefore(quick, els("face-character-select"));
  }
  const fullNodes = [popover.querySelector('label[for="face-character-select"]'),
    els("face-character-select"), popover.querySelector(".select-hint"),
    popover.querySelector('label[for="face-character-name"]'),
    els("face-character-name"), popover.querySelector(".face-popover-actions")].filter(Boolean);
  fullNodes.forEach(node => { node.dataset.faceFull = "true"; node.hidden = true; });
  quick.replaceChildren();
  quick.hidden = false;
  const evidence = face.candidate_evidence;
  const candidates = Array.isArray(evidence?.candidates) ? evidence.candidates.slice(0, 5) : [];
  const heading = document.createElement("p");
  heading.className = "candidate-note";
  heading.textContent = evidence ? (evidence.suggested ? `门禁建议：${evidence.suggested} · 仍由你选择` : "模型弃权 · 仍可人工选择") : "候选证据未提供 · 可手动命名";
  const honesty = document.createElement("p");
  honesty.className = "candidate-note";
  honesty.textContent = "候选仅含已建档角色；其他角色需先建立参考";
  const units = document.createElement("p");
  units.className = "candidate-note";
  units.textContent = "余弦 / 与最强其他角色的间隔（非概率） · 1–5 选择 · 方向键 + Enter";
  quick.append(heading, honesty, units);
  const make = (action, label) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "face-quick-action candidate-choice";
    button.dataset.faceQuick = action;
    button.dataset.candidateChoice = "true";
    button.textContent = label;
    return button;
  };
  candidates.forEach((candidate, index) => {
    const button = make("candidate", `${index + 1}  ${candidate.character}`);
    button.dataset.character = candidate.character;
    button.dataset.candidateIndex = String(index);
    button.setAttribute("aria-keyshortcuts", String(index + 1));
    const metric = document.createElement("span");
    metric.className = "candidate-metric";
    const gap = candidate.margin_vs_runner_up;
    metric.textContent = `${numberText(candidate.score)} / ${finite(gap) && gap > 0 ? "+" : ""}${numberText(gap)}`;
    button.append(metric);
    quick.append(button);
  });
  quick.append(make("other", "其他"), make("full", "新建角色"));
  const actions = document.createElement("div");
  actions.className = "candidate-secondary";
  const reject = make("ignore", "不是");
  reject.title = "忽略此人脸，保留原有排除语义；不是针对某个角色的负参考";
  actions.append(reject, make("skip", "跳过"));
  quick.append(actions);
}

function showFullFacePicker() {
  const popover = els("face-popover");
  popover.querySelectorAll("[data-face-full]").forEach(node => { node.hidden = false; });
  els("face-character-select").value = "";
  els("face-character-name").focus();
  positionFacePopover(els("preview-canvas"));
}

function handleFaceQuickClick(event) {
  const target = event.target instanceof Element ? event.target.closest("[data-face-quick]") : null;
  const face = activeFace();
  if (!target || !face) return;
  const action = target.dataset.faceQuick;
  if (action === "full") { showFullFacePicker(); return; }
  const faceId = face.face_id;
  if (action === "skip") {
    state.candidateSkipped ??= new Set();
    state.candidateSkipped.add(faceId);
  } else if (action === "candidate" || action === "other") {
    recordFaceLabel(face, "confirm", action === "other" ? "其他" : target.dataset.character);
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
    if (event.key === "Enter" && target.id === "face-character-name") {
      event.preventDefault(); facePopoverAction("new");
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
  // Enter/Space/Tab keep native button behavior; never leak into image shortcuts.
  return true;
}
