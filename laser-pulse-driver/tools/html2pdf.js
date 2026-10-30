// Print an HTML file to PDF (A4, page numbers in the footer) with Playwright's
// Chromium.  Used by make_review_pack.py.
//   node html2pdf.js in.html out.pdf "footer text"
//   node html2pdf.js in.html out.png --png      (first screen, for previews)
const { chromium } = require("playwright");

(async () => {
  const [inp, out, footer = ""] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto("file://" + inp, { waitUntil: "networkidle" });
  if (process.argv.includes("--png")) {
    await page.setViewportSize({ width: 820, height: 1160 });
    await page.screenshot({ path: out, fullPage: true });
  } else {
    await page.pdf({
      path: out, format: "A4", printBackground: true, preferCSSPageSize: true,
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate:
        `<div style="font: 7.5px Inter, sans-serif; color: #6b7280; width: 100%; margin: 0 16mm;
                     display: flex; justify-content: space-between;">
           <span>${footer}</span>
           <span>page <span class="pageNumber"></span></span>
         </div>`,
      margin: { top: "16mm", bottom: "16mm", left: "16mm", right: "16mm" },
    });
  }
  await browser.close();
})();
