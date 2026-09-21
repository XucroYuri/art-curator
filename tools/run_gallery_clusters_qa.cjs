// Use an installed Playwright; no dependency is shipped in the gallery.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const run = require("./qa_gallery_clusters.cjs");
(async () => {
  const browser = await chromium.launch({channel:"chrome",headless:true});
  try {
    const page = await browser.newPage({acceptDownloads:true});
    page.setDefaultTimeout(10000);
    console.log(JSON.stringify(await run(page),null,2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
