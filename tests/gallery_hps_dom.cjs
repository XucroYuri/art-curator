// Synthetic DOM unit harness; no browser, server, image, or network access.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const html = fs.readFileSync(process.argv[2], "utf8");
const payload = JSON.parse(require("node:zlib").gunzipSync(Buffer.from(
  html.match(/<script id="gallery-payload"[^>]*>(.*?)<\/script>/s)[1], "base64")));
const line = (prefix) => html.split("\n").find((item) => item.trim().startsWith(prefix));
class Element {
  children = []; dataset = {}; hidden = true; textContent = "";
  classList = {add() {}};
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this[key] = value; }
  focus() {}
  before(node) { headers.push(node); }
}
const headers = [];
const elements = new Map();
const document = {
  activeElement: null,
  createElement: () => new Element(),
  createDocumentFragment: () => new Element(),
  querySelector: () => new Element(),
  getElementById: (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
};
const context = vm.createContext({compact: payload, document, requestAnimationFrame: (fn) => fn()});
const declarations = html.slice(html.indexOf("const tierLabels="), html.indexOf("const PREFETCH_K=Math"));
const detail = html.slice(html.indexOf("function openDetail("), html.indexOf("function closeFamily("));
const code = [
  "let lastFocus=null;const hasQrealign=compact.d.includes('qrealign');",
  line("const columnar="), line("const column="), line("const rows="),
  line("const els="), declarations, line("const assetCandidates="),
  'const setText=(id,text)=>{document.getElementById(id).textContent=text;};',
  line("function renderScoreGrid("), detail,
  "renderScoreGrid(rows[0]);openDetail(rows[0]);",
].join("\n");
vm.runInContext(code, context, {timeout: 3000});
assert.equal(elements.get("family-panel").hidden, false);
assert.deepEqual(headers.map((node) => node.dataset.sortColumn), ["hpsv3_mu", "hpsv3_sigma"]);
const section = elements.get("drawer-scroll").children.at(-1);
const fields = section.children[1].children;
assert.ok(section.children[0].textContent.includes(String(fields.length)));
for (const [label, raw] of [["HPSv3 μ", payload.c.hm[0]], ["HPSv3 σ", payload.c.hs[0]]]) {
  const field = fields.find((node) => node.children[0].textContent === label);
  assert.ok(field, label);
  assert.equal(field.children[1].textContent, raw === null ? "—" : raw.toFixed(3));
  if (raw !== null) assert.ok(field.children[1].title.includes(String(raw)));
  const card = elements.get("score-grid").children[0].children.find((node) => node.children[0].textContent === label);
  assert.equal(card.children[1].textContent, field.children[1].textContent);
}
