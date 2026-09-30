// Hamza Voice Studio desktop shell (Electron main process).
// Starts and supervises the local Python service, waits for a real health check,
// then loads the studio from http://127.0.0.1:<port>. The renderer has no Node access.
"use strict";

const { app, BrowserWindow, dialog, ipcMain, session, shell } = require("electron");
const { spawn, execFile } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const PRODUCT = "Hamza Voice Studio";
const isWin = process.platform === "win32";
const token = crypto.randomBytes(32).toString("base64url");
let backend = null;
let port = null;
let dataDir = null;
let mainWindow = null;
let splash = null;
let quitting = false;
const logLines = [];

function resourcesRoot() {
  // Packaged: extraResources are copied next to app.asar. Dev: repository root.
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, "..");
}

function pythonPath() {
  if (process.env.HVS_PYTHON) return process.env.HVS_PYTHON;
  const root = resourcesRoot();
  const candidates = app.isPackaged
    ? [path.join(root, "python", isWin ? "python.exe" : "bin/python3")]
    : [path.join(root, ".venv", isWin ? "Scripts/python.exe" : "bin/python")];
  return candidates.find((p) => fs.existsSync(p)) ?? null;
}

function showSplash(text) {
  const html = `<!doctype html><meta charset="utf-8"><title>${PRODUCT}</title>
  <body style="margin:0;font:14px system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#0f1115;color:#e8ebf0">
  <div style="text-align:center"><div style="font-size:18px;font-weight:600;margin-bottom:8px">${PRODUCT}</div>
  <div id="s">${text}</div></div></body>`;
  if (!splash) {
    splash = new BrowserWindow({
      width: 420,
      height: 200,
      frame: false,
      resizable: false,
      show: true,
      webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, javascript: false },
    });
  }
  splash.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const py = pythonPath();
    if (!py) {
      reject(new Error("The bundled Python runtime was not found. Reinstall the application, or set HVS_PYTHON for development."));
      return;
    }
    const cwd = path.join(resourcesRoot(), "backend");
    const env = {
      ...process.env,
      HVS_TOKEN: token,
      HVS_FRONTEND_DIST: path.join(resourcesRoot(), "frontend", "dist"),
      PYTHONUNBUFFERED: "1",
      PYTHONDONTWRITEBYTECODE: "1",
    };
    backend = spawn(py, ["-m", "app.run", "--print-json", "--no-browser", "--port", process.env.HVS_PORT || "8765"], {
      cwd,
      env,
      windowsHide: true,
    });
    const rl = readline.createInterface({ input: backend.stdout });
    rl.on("line", (line) => {
      logLines.push(line);
      if (port) return;
      try {
        const msg = JSON.parse(line);
        if (msg.port) {
          port = msg.port;
          resolve(port);
        }
      } catch {
        /* ordinary log line */
      }
    });
    backend.stderr.on("data", (d) => {
      for (const l of String(d).split(/\r?\n/)) if (l) logLines.push(l);
      if (logLines.length > 400) logLines.splice(0, logLines.length - 400);
    });
    backend.on("exit", (code) => {
      if (!port) reject(new Error(`The studio service exited during startup (code ${code}).`));
      else if (!quitting) onBackendCrash(code);
    });
    backend.on("error", (e) => reject(e));
  });
}

async function waitForHealth(timeoutMs = 90000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/health`);
      if (r.ok) {
        const h = await r.json();
        if (h.worker && h.worker.state === "running") return h;
      }
    } catch {
      /* not ready */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error("The studio service did not become ready in time.");
}

async function fetchCapabilities() {
  const r = await fetch(`http://127.0.0.1:${port}/api/system/capabilities`, { headers: { "X-HVS-Token": token } });
  return r.ok ? r.json() : null;
}

function onBackendCrash(code) {
  dialog.showErrorBox(
    `${PRODUCT} stopped`,
    `The local studio service stopped unexpectedly (code ${code}). Your saved work is safe. Restart the application.\n\n` +
      logLines.slice(-15).join("\n"),
  );
  app.quit();
}

function stopBackend() {
  return new Promise((resolve) => {
    if (!backend || backend.exitCode !== null) return resolve();
    const timer = setTimeout(() => {
      if (isWin) execFile("taskkill", ["/pid", String(backend.pid), "/T", "/F"], () => resolve());
      else {
        backend.kill("SIGKILL");
        resolve();
      }
    }, 10000);
    backend.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    if (isWin) {
      // No SIGTERM on Windows: kill the process tree (API + worker). The worker also
      // exits by itself when it notices its parent is gone.
      execFile("taskkill", ["/pid", String(backend.pid), "/T"], () => {});
      setTimeout(() => execFile("taskkill", ["/pid", String(backend.pid), "/T", "/F"], () => {}), 4000);
    } else backend.kill("SIGTERM");
  });
}

function hardenSession(origin) {
  session.defaultSession.setPermissionRequestHandler((wc, permission, cb, details) => {
    const ok = permission === "media" && (details.requestingUrl || "").startsWith(origin) && (details.mediaTypes || []).every((t) => t === "audio");
    cb(ok);
  });
  session.defaultSession.setPermissionCheckHandler((wc, permission, requestingOrigin) => permission === "media" && requestingOrigin === origin);
}

function createWindow(origin) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 680,
    title: PRODUCT,
    show: false,
    backgroundColor: "#0f1115",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      spellcheck: true,
    },
  });
  mainWindow.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(origin)) e.preventDefault();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    if (splash) {
      splash.destroy();
      splash = null;
    }
  });
  mainWindow.loadURL(`${origin}/#/projects`);
}

// ---- IPC (narrow, validated) ----
ipcMain.handle("hvs:token", (event) => {
  if (!port || !event.senderFrame.url.startsWith(`http://127.0.0.1:${port}/`)) return null;
  return token;
});
ipcMain.handle("hvs:reveal-export", (event, fileName) => {
  if (!port || !event.senderFrame.url.startsWith(`http://127.0.0.1:${port}/`)) return false;
  if (typeof fileName !== "string" || fileName.length > 255 || path.basename(fileName) !== fileName) return false;
  if (!dataDir) return false;
  const exportsDir = path.join(dataDir, "exports");
  const full = path.join(exportsDir, fileName);
  if (!full.startsWith(exportsDir + path.sep) || !fs.existsSync(full)) return false;
  shell.showItemInFolder(full);
  return true;
});

app.on("web-contents-created", (_e, contents) => {
  contents.on("will-attach-webview", (e) => e.preventDefault());
});

const single = app.requestSingleInstanceLock();
if (!single) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    showSplash("Starting the local studio service…");
    try {
      await startBackend();
      showSplash("Loading models and checking the worker…");
      await waitForHealth();
      const caps = await fetchCapabilities();
      dataDir = caps && caps.data_dir;
      if (caps && !caps.ffmpeg.ffmpeg) {
        await dialog.showMessageBox({
          type: "warning",
          title: "FFmpeg not found",
          message: "FFmpeg is required for importing audio and exporting MP3.",
          detail: "Install FFmpeg and make sure ffmpeg.exe and ffprobe.exe are on PATH, then restart. See docs/SETUP_WINDOWS.md.",
        });
      }
      const origin = `http://127.0.0.1:${port}`;
      hardenSession(origin);
      createWindow(origin);
      if (process.env.HVS_SMOKE_TEST) {
        // Automated smoke test: confirm the studio rendered, then quit.
        mainWindow.webContents.once("did-finish-load", () => {
          setTimeout(async () => {
            const ok = await mainWindow.webContents.executeJavaScript("document.body.innerText.includes('Projects')");
            console.log(JSON.stringify({ smoke: ok ? "ok" : "failed", port }));
            app.quit();
          }, 3000);
        });
      }
    } catch (e) {
      await stopBackend();
      dialog.showErrorBox(`${PRODUCT} could not start`, `${e.message}\n\nRecent log:\n${logLines.slice(-15).join("\n")}\n\nSee docs/TROUBLESHOOTING.md.`);
      app.exit(1);
    }
  });

  app.on("before-quit", async (e) => {
    if (quitting) return;
    quitting = true;
    e.preventDefault();
    await stopBackend();
    app.exit(0);
  });

  app.on("window-all-closed", () => app.quit());
}
