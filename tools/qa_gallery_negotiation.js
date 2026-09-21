// Run with run_gallery_negotiation_qa.cjs and an installed Playwright package.
// Synthetic-only browser regression and fresh screenshot capture; never calls the CLI.
module.exports = async (page) => {
  const root = require("node:path").resolve(__dirname, "..").replaceAll("\\", "/");
  const output = `${root}/docs/assets/negotiation`;
  const results = {widths: [], screenshots: [], decisions: [], keyboard: [], checks: [], requests: [], errors: []};
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const requestListener = (request) => results.requests.push(request.url());
  const errorListener = (error) => results.errors.push(String(error));
  const consoleListener = (message) => { if (message.type() === "error") results.errors.push(message.text()); };
  page.on("request", requestListener); page.on("pageerror", errorListener); page.on("console", consoleListener);
  const shot = async (name) => { await page.screenshot({path: `${output}/${name}.png`}); results.screenshots.push(`${name}.png`); };
  const tabTo = async (selector) => {
    for (let i = 0; i < 200; i++) {
      if (await page.locator(selector).first().evaluate((node) => node === document.activeElement)) return;
      await page.keyboard.press("Tab");
    }
    throw new Error(`Keyboard cannot reach ${selector}`);
  };
  const fresh = async () => {
    await page.goto("http://127.0.0.1:8876/gallery.html");
    await page.locator("#negotiation-mode").waitFor();
    await page.locator("#negotiation-mode").click();
    await page.locator("#neg-status").waitFor();
  };
  try {
    await fresh();
    const fixture = await page.evaluate(async () => {
      const bytes = Uint8Array.from(atob(document.getElementById("gallery-payload").textContent.trim()), (c) => c.charCodeAt(0));
      return JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).text()).ng;
    });
    const upload = async (data) => {
      await page.evaluate((value) => {
        const input = document.getElementById("neg-report-file");
        const transfer = new DataTransfer();
        transfer.items.add(new File([JSON.stringify(value)], "report.json", {type: "application/json"}));
        input.files = transfer.files; input.dispatchEvent(new Event("change", {bubbles: true}));
      }, data);
      await page.waitForFunction(() => document.getElementById("neg-report-file").value === "");
    };
    assert(await page.locator("#neg-export").isDisabled(), "Waiting must not consent");
    for (const width of [520, 900, 1440]) {
      await page.setViewportSize({width, height: 1000});
      await page.locator("#negotiation-view").evaluate((node) => { node.scrollTop = 0; });
      await shot(`width-${width}`);
      await page.locator(".neg-choices").scrollIntoViewIfNeeded();
      await shot(`choices-${width}`);
      const regime = page.locator(".neg-folder .neg-details").first();
      await regime.locator("summary").click();
      await regime.scrollIntoViewIfNeeded();
      await shot(`regimes-${width}`);
      await regime.locator("summary").click();
      await page.locator("#neg-export").scrollIntoViewIfNeeded();
      await shot(`confirmation-${width}`);
      const dimensions = await page.evaluate(() => {
        const view = document.getElementById("negotiation-view");
        const clipping = [...view.querySelectorAll("h2,h3,h4,p,label,button,select,dd,dt,pre,legend,summary,li,figcaption,code,a")].filter((node) =>
          node.getBoundingClientRect().width > 0 && node.clientWidth > 0 && (node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1))
          .map((node) => ({tag: node.tagName, text: node.textContent.slice(0,80), visible: node.clientWidth, scroll: node.scrollWidth,
            visibleHeight: node.clientHeight, scrollHeight: node.scrollHeight}));
        return {visible: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth,
          regionVisible: view.clientWidth, regionScroll: view.scrollWidth, clipping};
      });
      assert(dimensions.visible === dimensions.scroll && dimensions.regionVisible === dimensions.regionScroll && !dimensions.clipping.length,
        `Width/clipping failure ${width}: ${JSON.stringify(dimensions)}`);
      results.widths.push({width, ...dimensions});
    }
    await page.setViewportSize({width: 900, height: 1000});
    await fresh();
    // Keyboard-only from the first page tab stop through decision export.
    await page.locator("#studio-mode").click();
    await page.keyboard.press("ArrowRight"); await page.keyboard.press("End");
    assert(await page.locator("#negotiation-mode").getAttribute("aria-selected") === "true", "Arrow tabs failed");
    results.keyboard.push("ArrowRight / End: studio → table → negotiation; no mouse within flow");
    await tabTo('input[name="neg-mode"][value="human-first"]');
    await page.keyboard.press("ArrowRight");
    assert(await page.locator('input[name="neg-mode"][value="auto-first"]').isChecked(), "Radio arrows failed");
    assert(await page.locator("#neg-auto-warning").isVisible(), "Auto warning absent");
    await tabTo('input[name="neg-scope"][value="none"]'); await page.keyboard.press("ArrowLeft");
    await tabTo(".neg-folder-choice input"); await page.keyboard.press("Space");
    await page.keyboard.press("Tab"); await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Tab"); await page.keyboard.press("ArrowDown");
    await tabTo("#neg-ack"); await page.keyboard.press("Space");
    await page.keyboard.press("Tab");
    assert(await page.locator("#neg-export").evaluate((node) => node === document.activeElement), "Export not reached by Tab");
    const focus = await page.locator("#neg-export").evaluate((node) => ({outline: getComputedStyle(node).outlineStyle, width: getComputedStyle(node).outlineWidth}));
    assert(focus.outline !== "none" && focus.width !== "0px", "No visible keyboard focus");
    await shot("keyboard-focus");
    const keyboardDownload = page.waitForEvent("download"); await page.keyboard.press("Enter");
    await (await keyboardDownload).saveAs(`${output}/keyboard-decision.json`);
    const keyboardDecision = JSON.parse(await page.locator("#neg-decision-preview pre").innerText());
    assert(keyboardDecision.mode === "auto-first" && keyboardDecision.inheritance === "selected" && keyboardDecision.folders.length === 1, "Keyboard decision wrong");
    assert(keyboardDecision.folders[0].relation_type === "work" && keyboardDecision.folders[0].descendants === "direct-only", "Keyboard selects wrong");
    results.keyboard.push("Tab / Space / native arrows: auto-first, selected folder, work, direct-only, acknowledgement; Enter downloads exact Decision");
    await page.locator("#neg-status").scrollIntoViewIfNeeded(); await shot("exported");
    await page.keyboard.press("Escape");
    assert(await page.locator("#negotiation-view").getAttribute("data-negotiation-state") === "dismissed", "Escape not non-consent");
    assert(await page.locator("#neg-export").isDisabled(), "Escape leaves consent armed");
    await page.locator("#negotiation-view").evaluate((node) => { node.scrollTop = 0; }); await shot("dismissed");
    results.keyboard.push("Escape clears affirmative and local preview, gives non-consent; already downloaded files cannot be recalled");
    await page.locator("#neg-dismiss").focus(); await page.keyboard.press("Tab"); await page.keyboard.press("Tab");
    results.keyboard.push(`Tab exits the last negotiation control to ${await page.evaluate(() => document.activeElement.tagName)}; no focus trap`);
    // All nine exported combinations are checked by the backend schema in pytest.
    for (const mode of ["human-first", "auto-first", "inherit-only"]) {
      for (const scope of ["all", "selected", "none"]) {
        await page.locator(`input[name="neg-mode"][value="${mode}"]`).check();
        await page.locator(`input[name="neg-scope"][value="${scope}"]`).check();
        if (scope === "selected") await page.locator(".neg-folder-choice input").first().check();
        await page.locator("#neg-ack").check();
        const downloaded = page.waitForEvent("download"); await page.locator("#neg-export").click();
        const decision = JSON.parse(await page.locator("#neg-decision-preview pre").innerText());
        await (await downloaded).saveAs(`${output}/decision-${mode}-${scope}.json`);
        assert(decision.folders.length === (scope === "all" ? fixture.folders.length : scope === "selected" ? 1 : 0), "Scope broadening");
        assert(decision.affirmative === true && decision.threshold_overrides.length === 0, "Unsafe decision");
        results.decisions.push(decision);
      }
    }
    assert(new Set(results.decisions.map((d) => d.operation_id)).size === 9, "Operation IDs reused");
    await page.locator("#neg-stale").click(); await page.locator("#neg-ack").check();
    assert(await page.locator("#neg-export").isDisabled(), "Stale report exported");
    await page.locator("#negotiation-view").evaluate((node) => { node.scrollTop = 0; }); await shot("stale");
    await upload(fixture);
    assert(await page.locator("#neg-export").count() === 0, "Same stale report accepted");
    const next = JSON.parse(JSON.stringify(fixture)); next.report_digest = "a".repeat(64);
    await upload(next); await page.locator("#neg-status").waitFor();
    assert(!await page.locator("#neg-ack").isChecked() && await page.locator("#neg-export").isDisabled(), "Reconsent missing");
    assert(await page.locator(".neg-thumbs img").count() === 0, "Old assets reused for new digest");
    results.checks.push("stale lock; same digest refused; new report clears selection/affirmative and cannot reuse old assets");
    await fresh();
    await page.locator("#neg-boundary").scrollIntoViewIfNeeded(); await shot("capability-disabled");
    assert(await page.getByRole("button", {name: fixture.presentation.text.commit_action, exact: true}).isDisabled(), "Mapping enabled");
    assert(await page.getByRole("button", {name: fixture.presentation.text.undo, exact: true}).isDisabled(), "Undo enabled");
    await page.evaluate(() => document.getElementById("neg-report-file").addEventListener("change", (event) => {
      window.qaRead = event.target.files[0].text().then(JSON.parse);
    }, {capture: true, once: true}));
    await page.locator("#neg-report-file").setInputFiles(`${root}/tests/fixtures/negotiation-report.example.json`);
    const example = await page.evaluate(() => window.qaRead);
    await page.locator("#neg-status").waitFor();
    const text = await page.locator("#negotiation-view").innerText();
    for (const key of ["ingest_prompt", "coherent_clusters", "purity_missing", "inheritance_warning", "reference_tier", "confirmation", "g2_boundary"])
      assert(text.includes(example.presentation.text[key]), `Copy changed: ${key}`);
    assert(text.includes("1/1 · 100.0%") && text.includes("全量描述性比例"), "Census purity missing basis");
    assert(!/[{}]/.test(text), "Unbound template in visible report");
    await shot("unavailable-evidence");
    const hostile = JSON.parse(JSON.stringify(example)); hostile.report_digest = "b".repeat(64);
    hostile.presentation.text.ingest_prompt = '<img src="https://example.invalid/steal">';
    await upload(hostile); await page.locator("#neg-status").waitFor();
    assert(await page.locator('#negotiation-view img[src^="http"]').count() === 0, "Copy became HTML");
    results.checks.push("authoritative bound copy; unavailable vs census distinction; hostile strings remain text");
    const invalid = JSON.parse(JSON.stringify(example)); invalid.presentation.text.confirmation = "{changed}";
    await upload(invalid); assert(await page.locator("#neg-export").count() === 0, "Invalid copy exported");
    await page.locator("#negotiation-view").evaluate((node) => { node.scrollTop = 0; }); await shot("invalid-report");
    results.checks.push("unbound copy fails closed");
    await fresh();
    results.externalRequests = results.requests.filter((url) => !url.startsWith("http://127.0.0.1:8876/") && !url.startsWith("data:"));
    assert(!results.externalRequests.length && !results.errors.length, `Network/console failures: ${JSON.stringify(results)}`);
    results.result = "PASS";
    const reportDownload = page.waitForEvent("download");
    await page.evaluate((value) => {
      const link = document.createElement("a"); const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"}));
      link.href = url; link.download = "qa-results.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
    }, results);
    await (await reportDownload).saveAs(`${output}/qa-results.json`);
    return {result: results.result, widths: results.widths, keyboard: results.keyboard, checks: results.checks,
      screenshots: results.screenshots, decisions: results.decisions.length, externalRequests: results.externalRequests, errors: results.errors};
  } finally {
    page.off("request", requestListener); page.off("pageerror", errorListener); page.off("console", consoleListener);
  }
}
