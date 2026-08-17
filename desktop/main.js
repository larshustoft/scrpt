/**
 * SCRPT desktop shell.
 * Ensures the local engine (:8000) and frontend (:3000) are running, then
 * opens the studio in a native window. Servers are left running on quit —
 * the engine is a companion service, not a child of the window.
 */

const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

// Install-specific paths (rewritten by the installer if the repo moves)
const BOOKR_DIR = "/Users/tiger/Desktop/CATALOG ENGINE/bookr";
const FRONTEND_DIR = path.join(os.homedir(), ".scrpt", "dev", "frontend");
const NPM = "/Users/tiger/.nvm/versions/node/v20.20.0/bin/npm";
const LOG_DIR = path.join(os.homedir(), ".scrpt");

const ENGINE_URL = "http://127.0.0.1:8000/api/health";
const FRONTEND_URL = "http://localhost:3000";
const START_URL = `${FRONTEND_URL}/study`;

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: 2500 }, (res) => {
      res.resume();
      resolve(res.statusCode && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function spawnDetached(cmd, args, cwd, logFile, env = {}) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
  const out = fs.openSync(path.join(LOG_DIR, logFile), "a");
  const child = spawn(cmd, args, {
    cwd,
    detached: true,
    stdio: ["ignore", out, out],
    env: { ...process.env, ...env },
  });
  child.unref();
}

async function ensureServers(onStatus) {
  if (!(await ping(ENGINE_URL))) {
    onStatus("Waking the engine…");
    spawnDetached(
      "/usr/bin/python3",
      ["-m", "uvicorn", "engine.main:app", "--port", "8000", "--host", "127.0.0.1"],
      BOOKR_DIR, "engine.log", { PYTHONPATH: BOOKR_DIR },
    );
  }
  if (!(await ping(FRONTEND_URL))) {
    onStatus("Opening the studio…");
    spawnDetached(NPM, ["run", "dev"], FRONTEND_DIR, "frontend.log");
  }
  // wait for both (up to 90s)
  for (let i = 0; i < 90; i++) {
    const [e, f] = await Promise.all([ping(ENGINE_URL), ping(FRONTEND_URL)]);
    if (e && f) return true;
    onStatus(e ? "Compiling the studio…" : "Waking the engine…");
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

const SPLASH = `data:text/html;charset=utf-8,${encodeURIComponent(`
  <html><body style="margin:0;background:#0e0c09;display:flex;align-items:center;
  justify-content:center;height:100vh;flex-direction:column;font-family:Georgia,serif;">
  <div style="color:#c9a45c;font-size:34px;letter-spacing:0.24em;">SCRPT</div>
  <div id="s" style="color:#83786a;font-size:12px;letter-spacing:0.2em;
  text-transform:uppercase;margin-top:18px;">Opening the study…</div>
  </body></html>`)}`;

async function createWindow() {
  const win = new BrowserWindow({
    width: 1500,
    height: 950,
    minWidth: 1050,
    minHeight: 700,
    backgroundColor: "#0e0c09",
    title: "SCRPT",
    show: true,
    fullscreen: true, // STCKR-style: the studio takes the whole screen
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });

  ipcMain.removeHandler("toggle-fullscreen");
  ipcMain.removeHandler("is-fullscreen");
  ipcMain.handle("toggle-fullscreen", () => {
    win.setFullScreen(!win.isFullScreen());
    return win.isFullScreen();
  });
  ipcMain.handle("is-fullscreen", () => win.isFullScreen());

  win.loadURL(SPLASH);

  // external links open in the real browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(FRONTEND_URL)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  const ok = await ensureServers((msg) => {
    win.webContents.executeJavaScript(
      `document.getElementById('s') && (document.getElementById('s').textContent = ${JSON.stringify(msg)})`,
    ).catch(() => {});
  });

  if (ok) {
    win.loadURL(START_URL);
  } else {
    win.loadURL(SPLASH.replace(
      encodeURIComponent("Opening the study…"),
      encodeURIComponent("Could not start the local servers — see ~/.scrpt/*.log"),
    ));
  }
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
