// PLAYWRIGHT_MODULE may point to an existing installation; no runtime dependency is shipped.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const run = require("./qa_gallery_negotiation.js");
(async () => {
  const browser = await chromium.launch({channel: "chrome", headless: true});
  try {
    const page = await browser.newPage({acceptDownloads: true});
    page.setDefaultTimeout(10000);
    console.log(JSON.stringify(await run(page), null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
