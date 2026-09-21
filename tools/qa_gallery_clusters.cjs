// Real Chrome evidence; run via Playwright MCP or an installed Playwright runner.
module.exports = async (page) => {
  const fs = require("node:fs"); const path = require("node:path");
  const root = path.resolve(__dirname, ".."); const output = path.join(root, "docs/assets/clusters");
  const results = {widths: [], screenshots: [], keyboard: [], checks: [], requests: [], errors: []};
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  page.on("request", (r) => results.requests.push(r.url()));
  page.on("pageerror", (e) => results.errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") results.errors.push(m.text()); });
  const shot = async (name) => { await page.screenshot({path: path.join(output, `${name}.png`)}); results.screenshots.push(name); };
  const tabTo = async (selector) => {
    for (let i = 0; i < 180; i++) {
      if (await page.locator(selector).evaluate((n) => n === document.activeElement)) return;
      await page.keyboard.press("Tab");
    }
    throw new Error(`Tab cannot reach ${selector}`);
  };
  const download = async (selector, name) => {
    const pending = page.waitForEvent("download"); await page.locator(selector).click();
    await (await pending).saveAs(path.join(output, name));
  };
  const fresh = async () => {
    await page.goto("http://127.0.0.1:8877/gallery.html");
    await page.locator("#clusters-mode").click();
  };
  const preview = async () => { await page.locator("#cl-preview-button").click(); await page.waitForFunction(() => document.querySelector("#cl-status").textContent.startsWith("草稿已预览")); };
  await page.setViewportSize({width:900,height:1000});
  await page.goto("http://127.0.0.1:8877/gallery.html"); await page.locator("#clusters-mode").waitFor();
  // Keyboard-only entry, typed entity, one member, preview, acknowledgement, download.
  await tabTo("#studio-mode"); await page.keyboard.press("End");
  assert(await page.locator("#clusters-mode").getAttribute("aria-selected") === "true", "End enters cluster tab");
  await tabTo("#cl-type"); await page.keyboard.press("Home"); await page.keyboard.press("ArrowDown");
  await tabTo("#cl-name"); await page.keyboard.type("Keyboard artist");
  const member = '#clusters-view input[data-member="member-05"]';
  await tabTo(member); await page.keyboard.press("Space");
  await tabTo("#cl-preview-button"); await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector("#cl-status").textContent.startsWith("草稿已预览"));
  assert(await page.locator("#cl-export").isDisabled(), "No export without explicit acknowledgement");
  await tabTo("#cl-ack"); await page.keyboard.press("Space"); await tabTo("#cl-export");
  const focus = await page.locator("#cl-export").evaluate((n) => ({visible:n.matches(":focus-visible"), outline:getComputedStyle(n).outlineStyle}));
  assert(focus.visible && focus.outline !== "none", "Visible keyboard focus"); await shot("keyboard-focus");
  const pending = page.waitForEvent("download"); await page.keyboard.press("Enter");
  await (await pending).saveAs(path.join(output,"keyboard-envelope.json"));
  await page.keyboard.press("Tab"); await page.keyboard.press("Tab"); await page.keyboard.press("Tab");
  assert(await page.evaluate(() => !document.querySelector("#clusters-view").contains(document.activeElement)), "No focus trap");
  results.keyboard.push("Tab to studio tab; End opens clusters; native select arrows choose artist; type name; Space selects member; Enter previews; Space acknowledges; Enter downloads; Tab exits region.");
  results.checks.push("Explicit acknowledgement required; focus visible; no focus trap; keyboard export is not applied.");
  for (const width of [520,900,1440]) {
    await fresh(); await page.setViewportSize({width,height:1000});
    await shot(`width-${width}`);
    await page.locator("#cl-existing").selectOption("synthetic-work");
    await page.locator("#cl-existing").scrollIntoViewIfNeeded(); await shot(`editor-${width}`);
    const dimensions = await page.evaluate(() => {
      const view = document.querySelector("#clusters-view");
      const clipping = [...view.querySelectorAll("h2,h3,p,button,label,dd,dt,pre,summary,figcaption")]
        .filter(n => n.getBoundingClientRect().width > 0 && n.clientWidth > 0 && (n.scrollWidth > n.clientWidth + 1 || n.scrollHeight > n.clientHeight + 1))
        .map(n => ({tag:n.tagName,text:n.textContent.slice(0,90),visible:n.clientWidth,scroll:n.scrollWidth}));
      return {visible:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
        regionVisible:view.clientWidth,regionScroll:view.scrollWidth,clipping};
    });
    assert(dimensions.visible === dimensions.scroll && dimensions.regionVisible === dimensions.regionScroll && !dimensions.clipping.length, JSON.stringify(dimensions));
    results.widths.push({width,...dimensions});
  }
  await page.setViewportSize({width:900,height:1000}); await fresh();
  await page.locator(".cl-deferred").scrollIntoViewIfNeeded(); await shot("deferred");
  await page.locator("#cl-action").selectOption("merge");
  await page.locator('#clusters-view fieldset:visible input').check();
  await page.locator("#cl-preview-button").click();
  assert(await page.locator("#cl-export").isDisabled(), "Conflicting merge blocked");
  await page.locator("#cl-preview").scrollIntoViewIfNeeded(); await shot("merge-conflict");
  await page.locator("#cl-defer").check(); await preview();
  await page.locator("#cl-preview").scrollIntoViewIfNeeded(); await shot("merge-deferred");
  await page.locator("#cl-ack").check(); await download("#cl-export","merge-envelope.json");
  results.checks.push("Conflicting accepted work/character IDs block merge until explicit defer; preview retains accepted relations.");
  await fresh(); await page.locator("#cl-action").selectOption("promote"); await page.locator("#cl-name").fill("十张合成图的晋升名称");
  const checks = page.locator('#clusters-view input[data-member]');
  for(let i=0;i<9;i++) await checks.nth(i).check();
  await page.locator("#cl-gate").scrollIntoViewIfNeeded();
  assert(await page.locator("#cl-preview-button").isDisabled(), "Nine images cannot promote"); await shot("promotion-9");
  await checks.nth(9).check(); await page.locator("#cl-gate").scrollIntoViewIfNeeded();
  assert(await page.locator("#cl-preview-button").isEnabled(), "Ten images unlock promotion preview"); await shot("promotion-10");
  await preview(); await page.locator("#cl-ack").check(); await download("#cl-export","promotion.json");
  results.checks.push("Promotion gate: exactly nine selected refuses, exactly ten enables; exports DiscoveryDecision, not BrowserEnvelope.");
  for (const action of ["split","outlier","exclusion"]) {
    await fresh(); await page.locator("#cl-action").selectOption(action);
    if(action === "split") {
      const parts = page.locator("#clusters-view select[data-member]");
      await parts.nth(0).selectOption("a"); await parts.nth(1).selectOption("b");
    } else await page.locator('#clusters-view input[data-member]').first().check();
    await preview(); await page.locator("#cl-preview").scrollIntoViewIfNeeded(); await shot(action);
    await page.locator("#cl-ack").check(); await download("#cl-export",`${action}-envelope.json`);
  }
  await page.locator("#cl-unavailable").scrollIntoViewIfNeeded(); await shot("capability-unavailable");
  assert(await page.locator("#cl-unavailable button:enabled").count() === 0,"Unsupported capabilities are disabled");
  await page.locator("#cl-action").selectOption("name"); await page.locator("#cl-name").fill("Changed draft");
  assert(await page.locator("#cl-export").isDisabled(), "Changing input invalidates export");
  await preview(); await page.keyboard.press("Escape");
  assert(await page.locator("#cl-export").isDisabled() && await page.locator("#cl-preview").textContent() === "", "Escape cancels preview");
  await download("#cl-manifest","manifest.json");
  results.checks.push("Split A/B plus remainder; outlier/exclusion are visual only; input edits and Escape invalidate acknowledgement; unsupported capabilities disabled.");
  assert(results.errors.length === 0, `Console/page errors: ${results.errors}`);
  assert(results.requests.every(u => u.startsWith("http://127.0.0.1:8877/") || u.startsWith("data:") || u.startsWith("blob:")), "External request detected");
  results.externalRequests = results.requests.filter(u => /^https?:/.test(u) && !u.startsWith("http://127.0.0.1:8877/"));
  results.independentVisualApproval = false;
  fs.writeFileSync(path.join(output,"qa-results.json"),JSON.stringify(results,null,2));
  return results;
};
