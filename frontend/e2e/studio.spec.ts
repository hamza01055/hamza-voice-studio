/**
 * End-to-end workflow with REAL speech generation (Kokoro via sherpa-onnx).
 * Requires: built frontend, Python venv, and HVS_E2E_MODELS_DIR pointing at a models
 * folder that contains an installed kokoro-multi-lang-v1_0. Skipped otherwise.
 */
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import path from "node:path";
import { Backend, TOKEN } from "./server";

const MODELS = process.env.HVS_E2E_MODELS_DIR;
const hasModel = !!MODELS && existsSync(path.join(MODELS, "kokoro-multi-lang-v1_0", "model.onnx"));

test.describe.configure({ mode: "serial" });

async function open(page: Page, b: Backend, hash = "#/projects") {
  await page.goto(`${b.url}/#token=${TOKEN}`);
  await page.evaluate((h) => (location.hash = h), hash);
}

function probe(file: string): { duration: number; format: string } {
  const out = execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration,format_name", "-of", "json", file]).toString();
  const f = JSON.parse(out).format;
  return { duration: Number(f.duration), format: f.format_name };
}

test("security: studio refuses to load without the session token", async ({ page }) => {
  const b = new Backend(18766);
  await b.start();
  try {
    await page.goto(`${b.url}/`);
    await expect(page.getByText("Open the studio from its launcher")).toBeVisible();
    const r = await page.request.get(`${b.url}/api/projects`);
    expect(r.status()).toBe(401);
  } finally {
    await b.stop();
  }
});

test("full workflow: create, generate (real), preview, regenerate, select take, export WAV+MP3, restart, reopen", async ({ page }, testInfo) => {
  test.skip(!hasModel, "Set HVS_E2E_MODELS_DIR to a folder with Kokoro installed");
  const b = new Backend(18765);
  await b.start();
  try {
    await open(page, b);
    await page.getByRole("button", { name: "New project" }).first().click();
    await page.getByLabel("Project name").fill("E2E Narration");
    await page
      .getByLabel("Script (optional)")
      .fill("Welcome to the end to end test.\n\nThe fee is Rs. 2,500 and the date is 15 October.");
    await page.getByRole("button", { name: "Create project" }).click();

    const seg1 = page.getByRole("article", { name: "Segment 1" });
    const seg2 = page.getByRole("article", { name: "Segment 2" });
    await expect(seg1).toBeVisible();
    await expect(seg2).toBeVisible();

    // spoken-text preview shows normalisation without changing the script
    await seg2.getByRole("button", { name: /Show spoken text/ }).click();
    await expect(seg2.getByText("two thousand five hundred rupees")).toBeVisible();
    await expect(seg2.getByLabel("Text of segment 2")).toHaveValue(/Rs\. 2,500/);

    // real generation of both segments
    await page.getByRole("button", { name: "Generate missing" }).click();
    await expect(seg1.getByText(/Take selected/)).toBeVisible({ timeout: 120_000 });
    await expect(seg2.getByText(/Take selected/)).toBeVisible({ timeout: 120_000 });

    // preview: the player loads and plays the take
    await seg1.getByRole("button", { name: "Play", exact: true }).click();
    await expect(page.getByRole("region", { name: "Audio player" }).getByText("Segment 1")).toBeVisible();

    // regenerate only segment 1
    await seg1.getByRole("button", { name: "New take" }).click();
    await expect(seg1.getByRole("button", { name: "Takes (2)" })).toBeVisible({ timeout: 120_000 });
    await expect(seg2.getByRole("button", { name: "Takes (1)" })).toBeVisible();

    // choose take 2 for export
    await expect(seg1.getByRole("list", { name: "Takes for segment 1" })).toBeVisible();
    const take2 = seg1.getByRole("listitem").filter({ hasText: "Take 2" });
    await take2.getByRole("button", { name: "Use this take in export" }).click();
    await expect(take2.getByRole("button", { name: /Used in export/ })).toBeVisible();

    // exports
    const files: Record<string, string> = {};
    for (const fmt of ["wav", "mp3"] as const) {
      await page.getByRole("button", { name: "Export", exact: true }).click();
      const dlg = page.getByRole("dialog", { name: "Export audio" });
      await dlg.getByLabel("Format").selectOption(fmt);
      await dlg.getByRole("button", { name: `Export ${fmt.toUpperCase()}` }).click();
      await expect(dlg.getByText("Export complete")).toBeVisible({ timeout: 60_000 });
      const link = dlg.getByRole("link", { name: "Download" }).first();
      const href = await link.getAttribute("href");
      const res = await page.request.get(`${b.url}${href}`);
      expect(res.status()).toBe(200);
      const f = testInfo.outputPath(`export.${fmt}`);
      writeFileSync(f, await res.body());
      files[fmt] = f;
      await dlg.getByRole("button", { name: "Close" }).first().click();
    }
    const wav = probe(files.wav);
    const mp3 = probe(files.mp3);
    expect(wav.format).toBe("wav");
    expect(mp3.format).toBe("mp3");
    expect(wav.duration).toBeGreaterThan(3);
    expect(Math.abs(wav.duration - mp3.duration)).toBeLessThan(0.2);

    // which take is selected, per the API, before restart
    const projects = await b.api<{ items: { id: string }[] }>("GET", "/projects");
    const pid = projects.items[0].id;
    const before = await b.api<{ chapters: { segments: { id: string; selected_take_id: string }[] }[] }>("GET", `/projects/${pid}`);
    const selectedBefore = before.chapters[0].segments.map((s) => s.selected_take_id);

    // edit text -> old take flagged as generated from older text
    await seg2.getByLabel("Text of segment 2").fill("The fee has changed.");
    await expect(seg2.getByText("Saved")).toBeVisible();
    await expect(seg2.getByText("Text changed since take")).toBeVisible();

    // restart the application (same data directory)
    await b.stop();
    await b.start();
    await open(page, b, `#/studio/${pid}`);
    await expect(page.getByRole("article", { name: "Segment 1" })).toBeVisible();
    await expect(page.getByRole("article", { name: "Segment 2" }).getByLabel("Text of segment 2")).toHaveValue("The fee has changed.");
    const after = await b.api<{ chapters: { segments: { id: string; selected_take_id: string }[] }[] }>("GET", `/projects/${pid}`);
    expect(after.chapters[0].segments.map((s) => s.selected_take_id)).toEqual(selectedBefore);
    const s1 = page.getByRole("article", { name: "Segment 1" });
    await s1.getByRole("button", { name: "Takes (2)" }).click();
    await expect(s1.getByRole("listitem").filter({ hasText: "Take 2" }).getByRole("button", { name: /Used in export/ })).toBeVisible();

    // exports still downloadable after restart
    const exps = await b.api<{ items: { id: string; status: string }[] }>("GET", `/projects/${pid}/exports`);
    expect(exps.items.filter((e) => e.status === "completed")).toHaveLength(2);
    for (const e of exps.items) {
      const r = await page.request.get(`${b.url}/api/exports/${e.id}/file?t=${TOKEN}`);
      expect(r.status()).toBe(200);
    }

    // delete the project and confirm its data is gone
    await page.evaluate(() => (location.hash = "#/projects"));
    await page.getByRole("button", { name: "Delete E2E Narration" }).click();
    await page.getByRole("button", { name: "Delete project" }).click();
    await expect(page.getByText("No projects yet")).toBeVisible();
    const gone = await page.request.get(`${b.url}/api/projects/${pid}?t=${TOKEN}`, { headers: { "X-HVS-Token": TOKEN } });
    expect(gone.status()).toBe(404);
  } finally {
    await b.stop();
  }
});

test("voice library: upload with consent, validation, delete", async ({ page }, testInfo) => {
  const b = new Backend(18767);
  await b.start();
  try {
    // 4 s synthetic test tone (not a person's voice) generated with ffmpeg
    const wav = testInfo.outputPath("ref.wav");
    execFileSync("ffmpeg", ["-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-af", "volume=0.4", wav]);
    await open(page, b, "#/voices");
    await expect(page.getByText("No voice-cloning engine is installed")).toBeVisible();
    await page.getByRole("button", { name: "Add voice" }).first().click();
    const dlg = page.getByRole("dialog", { name: "Add a voice" });
    await dlg.locator('input[type="file"]').setInputFiles(wav);
    await dlg.getByLabel("Name").fill("Test tone");
    const save = dlg.getByRole("button", { name: "Save voice" });
    await expect(save).toBeDisabled(); // consent not given yet
    await dlg.getByLabel("This is my own voice").check();
    await dlg.getByRole("checkbox").check();
    await save.click();
    await expect(page.getByRole("heading", { name: "Test tone" })).toBeVisible();
    await expect(page.getByText("No compatible engine installed")).toBeVisible();
    await page.getByRole("button", { name: "Delete Test tone" }).click();
    await page.getByRole("button", { name: "Delete voice" }).click();
    await expect(page.getByText("No voices yet")).toBeVisible();
  } finally {
    await b.stop();
  }
});
