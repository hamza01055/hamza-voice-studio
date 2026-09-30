import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PY =
  process.env.HVS_PYTHON ??
  (process.platform === "win32" ? path.join(ROOT, ".venv", "Scripts", "python.exe") : path.join(ROOT, ".venv", "bin", "python"));

export const TOKEN = "e2e-token-0123456789";

export class Backend {
  proc: ChildProcess | null = null;
  readonly port: number;
  readonly dataDir: string;
  constructor(port = 18765, dataDir?: string) {
    this.port = port;
    this.dataDir = dataDir ?? mkdtempSync(path.join(tmpdir(), "hvs-e2e-"));
  }
  get url() {
    return `http://127.0.0.1:${this.port}`;
  }
  async start(): Promise<void> {
    if (!existsSync(PY)) throw new Error(`Python not found at ${PY}; set HVS_PYTHON`);
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      HVS_TOKEN: TOKEN,
      HVS_DATA_DIR: this.dataDir,
      HVS_FRONTEND_DIST: path.join(ROOT, "frontend", "dist"),
    };
    if (process.env.HVS_E2E_MODELS_DIR) env.HVS_MODELS_DIR = process.env.HVS_E2E_MODELS_DIR;
    this.proc = spawn(PY, ["-m", "app.run", "--no-browser", "--strict-port", "--port", String(this.port)], {
      cwd: path.join(ROOT, "backend"),
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let log = "";
    this.proc.stdout?.on("data", (d) => (log += d));
    this.proc.stderr?.on("data", (d) => (log += d));
    for (let i = 0; i < 120; i++) {
      try {
        const r = await fetch(`${this.url}/api/health`);
        if (r.ok) {
          const h = (await r.json()) as { worker: { state: string } };
          if (h.worker.state === "running") return;
        }
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error(`backend did not start:\n${log}`);
  }
  async stop(): Promise<void> {
    const p = this.proc;
    if (!p || p.exitCode !== null) return;
    await new Promise<void>((resolve) => {
      p.once("exit", () => resolve());
      p.kill("SIGTERM");
      setTimeout(() => p.kill("SIGKILL"), 15000);
    });
    this.proc = null;
  }
  async api<T>(method: string, p: string, body?: unknown): Promise<T> {
    const r = await fetch(`${this.url}/api${p}`, {
      method,
      headers: { "X-HVS-Token": TOKEN, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${method} ${p} -> ${r.status} ${await r.text()}`);
    return (await r.json()) as T;
  }
}
