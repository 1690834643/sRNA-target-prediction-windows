// sRNA Target Predictor — vanilla-JS front-end.
//
// Boots by calling /api/discover, paints tool status badges, pre-fills the
// default output dir, then lets the user pick FASTAs (via /api/pick-file,
// which drives a native Tk dialog server-side), hit Run, watch progress
// stream over WebSocket, and open the output folder when done.

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

// ── Element refs ────────────────────────────────────────────────────────
const statusLine = $("#status-line");
const statusText = $(".status-text", statusLine);
const toolBadgesEl = $("#tool-badges");

const mirnaIn = $("#mirna");
const targetsIn = $("#targets");
const outIn = $("#out");

const runBtn = $("#run");
const cancelBtn = $("#cancel");
const exampleBtn = $("#example-btn");
const setupPane = $("#setup-pane");
const runPane = $("#run-pane");
const runStateText = $("#run-state-text");
const progressEl = $("#progress");
const logEl = $("#log");
const resultRow = $("#result-row");
const downloadEl = $("#download");
const reportEl = $("#report");
const openFolderBtn = $("#open-folder");
const resetBtn = $("#reset");

// ── State ───────────────────────────────────────────────────────────────
let activeWs = null;
let activeJobId = null;
let lastOutputDir = null;
let env = null;   // /api/discover payload
let jobTerminalReached = false; // flips true on first done/error event

// ── Init ────────────────────────────────────────────────────────────────
async function init() {
  try {
    const res = await fetch("/api/discover");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    env = await res.json();
  } catch (e) {
    setStatus("none", `检测失败 · Discovery failed: ${e.message}`);
    return;
  }
  paintStatus(env);
  paintToolBadges(env);
  prefillFromEnv(env);
}

function paintStatus(env) {
  const ready = env.ready_count;
  const total = env.total_count;
  let cls;
  let text;
  if (ready === total) {
    cls = "ready";
    text = `已就绪 · ${ready}/${total}`;
  } else if (ready === 0) {
    cls = "none";
    text = `未检测到内置工具 · 在高级设置里手动指定路径`;
  } else {
    cls = "partial";
    text = `${ready}/${total} · 其余在高级设置里手动指定`;
  }
  setStatus(cls, text);
}

function setStatus(cls, text) {
  statusLine.classList.remove("loading", "ready", "partial", "none");
  statusLine.classList.add(cls);
  statusText.textContent = text;
}

function paintToolBadges(env) {
  const meta = {
    miranda:   { display: "miRanda" },
    rnahybrid: { display: "RNAhybrid" },
    pita:      { display: "PITA" },
  };
  toolBadgesEl.innerHTML = "";
  for (const key of Object.keys(meta)) {
    const tool = env.tools[key];
    const div = document.createElement("div");
    div.className = "tool-badge " + (tool.ready ? "ready" : "missing");
    div.innerHTML = `
      <span class="badge-name">${meta[key].display}</span>
      <span class="badge-status">${tool.ready ? "✓" : "未检测到"}</span>
    `;
    toolBadgesEl.appendChild(div);

    // Mirror state into the Advanced disclosure (tool-state pill + path row)
    const stateEl = $(`[data-state-for="${key}"]`);
    const pathRow = $(`[data-path-for="${key}"]`);
    if (stateEl) {
      stateEl.classList.toggle("ready", tool.ready);
      stateEl.classList.toggle("missing", !tool.ready);
      stateEl.textContent = tool.ready
        ? "已捆绑"
        : `手动指定 · ${tool.reason || "missing"}`;
    }
    if (pathRow) pathRow.hidden = tool.ready;
  }
}

function prefillFromEnv(env) {
  if (env.default_output_dir && !outIn.value) {
    outIn.value = env.default_output_dir;
  }
  // Backend picker stays visible: PITA on Windows is experimental and the
  // note in Advanced tells the user they may need to fall back to WSL.
}

// ── Browse buttons ──────────────────────────────────────────────────────
async function handleBrowse(btn) {
  const target = btn.dataset.target;        // e.g. "mirna" or "miranda-exe"
  const mode = btn.dataset.mode || "file";  // file | dir | save
  const filetypes = btn.dataset.filetypes || "any";
  const title = btn.dataset.title || "选择";

  // Pick a sensible initial dir: existing value's parent, else home.
  const targetInput = resolveInputByKey(target);
  const currentVal = targetInput ? targetInput.value : "";
  const initialdir = parentDir(currentVal) || env?.default_output_dir || "";

  btn.disabled = true;
  try {
    const res = await fetch("/api/pick-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, filetypes, title, initialdir }),
    });
    if (!res.ok) {
      // 503 → tkinter unavailable. Show a hint, don't blow up.
      const detail = (await safeJson(res))?.detail || `HTTP ${res.status}`;
      appendLog(`[browse] ${detail} — 请手动粘贴路径`, "fail");
      return;
    }
    const { path } = await res.json();
    if (path && targetInput) targetInput.value = path;
  } catch (e) {
    appendLog(`[browse] ${e.message}`, "fail");
  } finally {
    btn.disabled = false;
  }
}

function resolveInputByKey(key) {
  if (key === "mirna" || key === "targets" || key === "out") return $("#" + key);
  if (key.endsWith("-exe")) {
    const tool = key.replace(/-exe$/, "");
    return $(`.tool[data-tool="${tool}"] .exe`);
  }
  return null;
}

function parentDir(p) {
  if (!p) return "";
  const norm = p.replace(/[\\/]+$/, "");
  const idx = Math.max(norm.lastIndexOf("/"), norm.lastIndexOf("\\"));
  return idx > 0 ? norm.slice(0, idx) : "";
}

async function safeJson(res) {
  try { return await res.json(); } catch { return null; }
}

// ── Log helpers ─────────────────────────────────────────────────────────
function appendLog(text, klass) {
  const line = document.createElement("span");
  if (klass) line.className = klass;
  line.textContent = text + "\n";
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function clearLog() { logEl.textContent = ""; }

// ── Build the request payload ────────────────────────────────────────────
function readToolConfig(toolKey) {
  const root = $(`.tool[data-tool="${toolKey}"]`);
  if (!root) return null;
  if (!$(".enable", root).checked) return null;

  const cfg = {};
  // exe / script: prefer user-typed path; fall back to bundled (server resolves).
  const exeInput = $(".exe", root);
  const exeVal = exeInput ? exeInput.value.trim() : "";
  if (exeVal) {
    cfg[toolKey === "pita" ? "script" : "exe"] = exeVal;
  }
  // tool params
  for (const el of $$("[data-key]", root)) {
    const key = el.dataset.key;
    if (el.type === "checkbox") {
      if (el.checked) cfg[key] = true;
    } else if (el.type === "number") {
      const v = el.value.trim();
      if (v !== "") cfg[key] = parseFloat(v);
    } else {
      const v = el.value.trim();
      if (v !== "") cfg[key] = v;
    }
  }
  return cfg;
}

function buildPayload() {
  const tools = {};
  for (const key of ["miranda", "rnahybrid", "pita"]) {
    const cfg = readToolConfig(key);
    if (cfg !== null) tools[key] = cfg;
  }
  return {
    mirna: mirnaIn.value.trim(),
    targets: targetsIn.value.trim(),
    out: outIn.value.trim(),
    workers: parseInt($("#workers").value, 10) || 4,
    chunk_size: parseInt($("#chunk").value, 10) || 500,
    mirna_chunk_size: parseInt($("#mirna_chunk").value, 10) || 0,
    backend: $("#backend").value,
    resume: $("#resume").checked,
    tools,
  };
}

// ── Pre-flight validation before submitting ─────────────────────────────
function validateBeforeSubmit(payload) {
  const errs = [];
  if (!payload.mirna)   errs.push("miRNA FASTA");
  if (!payload.targets) errs.push("Targets FASTA");
  if (!payload.out)     errs.push("Output folder");
  if (errs.length) return `请填: ${errs.join(", ")}`;

  if (Object.keys(payload.tools).length === 0) {
    return "至少启用一个工具(高级设置 → 工具参数)";
  }

  // If a tool is enabled but missing both bundled binary AND a typed path → block.
  for (const [key, cfg] of Object.entries(payload.tools)) {
    const tool = env?.tools?.[key];
    const hasTyped = cfg.exe || cfg.script;
    if (!hasTyped && !(tool && tool.ready)) {
      return `${key} 未就绪:在高级设置里指定路径,或取消勾选`;
    }
  }
  return null;
}

// ── Run flow ────────────────────────────────────────────────────────────
async function startRun() {
  const payload = buildPayload();
  const err = validateBeforeSubmit(payload);
  if (err) {
    showError(err);
    return;
  }

  enterRunning();
  appendLog(`[start] 提交任务 · tools=${Object.keys(payload.tools).join(", ")}`);

  let res;
  try {
    res = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    appendLog(`[error] network: ${e.message}`, "fail");
    enterFailed(e.message);
    return;
  }

  if (!res.ok) {
    const detail = (await safeJson(res))?.detail || "";
    appendLog(`[error] HTTP ${res.status} ${detail}`, "fail");
    enterFailed(detail || `HTTP ${res.status}`);
    return;
  }

  const { job_id } = await res.json();
  activeJobId = job_id;
  lastOutputDir = payload.out;
  appendLog(`[job] ${job_id} accepted, streaming progress…`);
  openWebSocket(job_id);
}

function openWebSocket(jobId) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/api/jobs/${jobId}/events`);
  activeWs = ws;

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "progress") {
      const klass = statusToClass(msg.status);
      const extra = msg.message ? `  ${msg.message}` : "";
      appendLog(`[${msg.status}] ${msg.tool} ${msg.chunk_id}${extra}`, klass);
      if (msg.total) {
        progressEl.max = msg.total;
        progressEl.value = msg.completed;
      }
    } else if (msg.type === "status") {
      appendLog(`[status] ${msg.status}`);
    } else if (msg.type === "done") {
      appendLog(`[ok] merged CSV: ${msg.merged_csv}`, "ok");
      if (msg.report_html) appendLog(`[ok] report: ${msg.report_html}`, "ok");
      jobTerminalReached = true;
      enterDone(msg.merged_csv, jobId, msg.report_html);
    } else if (msg.type === "error") {
      appendLog(`[error] ${msg.message}`, "fail");
      jobTerminalReached = true;
      enterFailed(msg.message);
    }
  };
  ws.onerror = () => appendLog("[error] websocket error", "fail");
  ws.onclose = (event) => {
    activeWs = null;
    // If the connection closed mid-stream without a done/error event, the
    // user would otherwise stare at "预测中…" forever. Probe the job
    // status REST endpoint, surface what we know, and unblock the UI.
    if (!jobTerminalReached) {
      handleUnexpectedDisconnect(jobId, event);
    }
  };
}

async function handleUnexpectedDisconnect(jobId, event) {
  appendLog(`[error] WebSocket closed before job finished (code=${event ? event.code : "?"})`, "fail");
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (res.ok) {
      const status = await res.json();
      if (status.status === "completed" && status.merged_csv) {
        appendLog(`[recover] 服务器报告任务已完成，恢复结果界面`, "ok");
        enterDone(status.merged_csv, jobId, null);
        return;
      }
      if (status.status === "failed") {
        enterFailed(status.error || "job failed (status fetched after WS close)");
        return;
      }
      enterFailed(`WS 断开，但任务仍在运行 (status=${status.status})。刷新页面可重新订阅事件流。`);
      return;
    }
  } catch (e) {
    // fall through to generic failure
  }
  enterFailed("连接断开且无法查询任务状态");
}

function statusToClass(status) {
  if (status === "completed") return "done";
  if (status === "failed")    return "fail";
  if (status === "skipped")   return "skip";
  return "";
}

// ── UI state transitions ────────────────────────────────────────────────
function enterRunning() {
  clearLog();
  resultRow.classList.add("hidden");
  progressEl.value = 0;
  progressEl.max = 100;
  runPane.classList.remove("hidden");
  runStateText.textContent = "预测中… · Running";
  runStateText.classList.remove("ok", "fail");
  runBtn.disabled = true;
  cancelBtn.disabled = false;
  exampleBtn.disabled = true;
  jobTerminalReached = false; // reset for the new run
}

function enterDone(mergedCsv, jobId, reportHtml) {
  runStateText.textContent = `✅ 预测完成 · ${mergedCsv.split(/[/\\]/).pop()}`;
  runStateText.classList.add("ok");
  downloadEl.href = `/api/jobs/${jobId}/download`;
  if (reportHtml) {
    reportEl.href = `/api/jobs/${jobId}/report`;
    reportEl.classList.remove("hidden");
  } else {
    reportEl.classList.add("hidden");
  }
  resultRow.classList.remove("hidden");
  runBtn.disabled = false;
  cancelBtn.disabled = true;
  exampleBtn.disabled = false;
}

function enterFailed(msg) {
  runStateText.textContent = `✗ 失败 · ${msg || "see log"}`;
  runStateText.classList.add("fail");
  resultRow.classList.add("hidden");
  runBtn.disabled = false;
  cancelBtn.disabled = true;
  exampleBtn.disabled = false;
}

function showError(msg) {
  runPane.classList.remove("hidden");
  runStateText.textContent = `✗ ${msg}`;
  runStateText.classList.add("fail");
  clearLog();
  appendLog(`[error] ${msg}`, "fail");
  resultRow.classList.add("hidden");
}

function cancelRun() {
  if (activeWs) { activeWs.close(); activeWs = null; }
  appendLog("[cancel] 断开事件流。服务器仍在跑已启动的 chunk;刷新页面可重连。");
  runBtn.disabled = false;
  cancelBtn.disabled = true;
  exampleBtn.disabled = false;
}

function resetToSetup() {
  runPane.classList.add("hidden");
  resultRow.classList.add("hidden");
  clearLog();
  progressEl.value = 0;
  runBtn.disabled = false;
  cancelBtn.disabled = true;
}

// ── Example-data quickstart ─────────────────────────────────────────────
function fillExampleAndRun() {
  if (!env || !env.examples) {
    appendLog("[example] 未找到内置示例数据", "fail");
    return;
  }
  mirnaIn.value = env.examples.mirna;
  targetsIn.value = env.examples.targets;
  if (!outIn.value) outIn.value = env.default_output_dir;
  // Make sure all bundled tools are enabled.
  for (const key of ["miranda", "rnahybrid", "pita"]) {
    const enableBox = $(`.tool[data-tool="${key}"] .enable`);
    const tool = env.tools[key];
    if (enableBox) enableBox.checked = Boolean(tool && tool.ready);
  }
  startRun();
}

// ── Open output folder ──────────────────────────────────────────────────
async function openOutputFolder() {
  if (!lastOutputDir) return;
  try {
    const res = await fetch("/api/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: lastOutputDir }),
    });
    if (!res.ok) {
      const detail = (await safeJson(res))?.detail || `HTTP ${res.status}`;
      appendLog(`[open-folder] ${detail}`, "fail");
    }
  } catch (e) {
    appendLog(`[open-folder] ${e.message}`, "fail");
  }
}

// ── Wire up events ──────────────────────────────────────────────────────
$$(".browse").forEach((btn) => btn.addEventListener("click", () => handleBrowse(btn)));
runBtn.addEventListener("click", startRun);
cancelBtn.addEventListener("click", cancelRun);
exampleBtn.addEventListener("click", fillExampleAndRun);
openFolderBtn.addEventListener("click", openOutputFolder);
resetBtn.addEventListener("click", resetToSetup);

init();
