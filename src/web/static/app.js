/* Dashboard Mesin Transcribe — client logic (SSE real-time + auth) */
"use strict";

const $ = (id) => document.getElementById(id);
const apiFetch = async (resource, options = {}) => {
  const response = await fetch(resource, { ...options, credentials: "include" });
  if (response.status === 401 && resource !== "api/auth/me" && resource !== "api/auth/login") {
    const next = `${window.location.pathname}${window.location.search}`;
    window.location.assign(`api/auth/login?next=${encodeURIComponent(next)}`);
  }
  return response;
};

const dropzone = $("dropzone");
const fileInput = $("file-input");
const btnRemoveFile = $("btn-remove-file");
const btnTranscribe = $("btn-transcribe");
const defaultTranscribeLabel = btnTranscribe.textContent;
const btnCancel = $("btn-cancel");
let queueStatusTimer = null;
const btnAINotulen = $("btn-ai-notulen");
const btnAICleanup = $("btn-ai-cleanup");
const btnDownloadTranscript = $("btn-download-transcript");
const btnDownloadCleaned = $("btn-download-cleaned");
const btnDownloadMinutes = $("btn-download-minutes");
const btnDownloadCleanedMd = $("btn-download-cleaned-md");
const btnDownloadMinutesMd = $("btn-download-minutes-md");
const btnAIDocument = $("btn-ai-document");
const btnDownloadDocPdf = $("btn-download-doc-pdf");
const btnDownloadDocDocx = $("btn-download-doc-docx");
const btnDownloadDocMd = $("btn-download-doc-md");
const docDialog = $("doc-dialog");
const docJenis = $("doc-jenis");
const docJudul = $("doc-judul");
const docFields = $("doc-fields");
const docFilePrefixes = { laporan_kegiatan: "LaporanKegiatan_", notulen_rapat: "NotulenRapat_" };
const btnDownloadPdf = $("btn-download-pdf");
const progressBar = $("progress-bar");
const progressLabel = $("progress-label");
const statusText = $("status-text");
const logEl = $("log");
const previewEl = $("preview");
const historyEl = $("history");
const supportedMediaExtensions = new Set([
  ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg",
  ".wma", ".aiff", ".aif", ".amr", ".opus",
  ".webm", ".mp4", ".m4v", ".mov", ".mkv", ".avi",
]);

let authEnabled = false;
let selectedFile = null;
let uploadedPath = null;
let currentJobId = null;
let currentJobKind = null;
let eventSource = null;
let sseEventCount = 0;
let jobStatusTimer = null;
let aiProgressTimer = null;
let aiProgressValue = 0;
let progressFloor = 0;
let uploadRequest = null;
let running = false;
let aiRunning = false;
let aiReady = false;
let actionControlsLocked = false;

async function refreshQueueStatus() {
  if (running) return;
  try {
    const response = await apiFetch("api/jobs/queue-status");
    if (!response.ok) return;
    const queue = await response.json();
    const busy = Number(queue.total_count) > 0;
    btnTranscribe.textContent = busy
      ? "Worker sedang digunakan — Masuk antrean"
      : defaultTranscribeLabel;
    btnTranscribe.title = busy
      ? `Ada ${queue.total_count} job dalam proses/antrean. Job Anda tetap akan masuk antrean.`
      : "";
    btnTranscribe.setAttribute("aria-label", btnTranscribe.title || defaultTranscribeLabel);
  } catch (error) {
    // Queue status is informational; upload/transcription remains available.
  }
}

function startQueueStatusPolling() {
  if (queueStatusTimer) window.clearInterval(queueStatusTimer);
  refreshQueueStatus();
  queueStatusTimer = window.setInterval(refreshQueueStatus, 5000);
}

function stopQueueStatusPolling() {
  if (queueStatusTimer) {
    window.clearInterval(queueStatusTimer);
    queueStatusTimer = null;
  }
}

function setActionControlsLocked(locked) {
  actionControlsLocked = locked;
  if (locked) stopQueueStatusPolling();
  else startQueueStatusPolling();
  const controls = [
    btnTranscribe, btnAINotulen, btnAICleanup, btnAIDocument,
    btnDownloadTranscript, btnDownloadCleaned, btnDownloadMinutes,
    btnDownloadCleanedMd, btnDownloadMinutesMd, btnDownloadPdf,
    btnDownloadDocPdf, btnDownloadDocDocx, btnDownloadDocMd,
  ];
  controls.forEach((control) => {
    if (!control) return;
    control.setAttribute("aria-disabled", locked ? "true" : "false");
    if (control.tagName === "BUTTON") {
      control.disabled = locked;
    } else {
      control.classList.toggle("action-locked", locked);
      control.style.pointerEvents = locked ? "none" : "";
      control.tabIndex = locked ? -1 : 0;
    }
  });
}

function syncActionControls() {
  if (actionControlsLocked) return;
  btnTranscribe.disabled = running || !selectedFile || selectedFile.size > maxUploadBytes;
  btnAINotulen.disabled = running || !aiReady;
  btnAICleanup.disabled = running || !aiReady;
  btnAIDocument.disabled = running || !aiReady;
}
let maxUploadBytes = 2 * 1024 * 1024 * 1024;
let resultFiles = null;
let currentResultPath = null;
let currentResultFiles = [];
let currentDocJenis = null;
let docTypes = null;
let previewRequestId = 0;
let selectedHistoryName = null;

async function checkAuth() {
  const response = await apiFetch("api/auth/me");
  if (response.status === 401) {
    authEnabled = true;
    $("auth-status").textContent = "Belum masuk · akun Google UGM";
    $("btn-logout").classList.add("hidden");
    return false;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Status masuk tidak dapat dibaca");
  authEnabled = !!data.auth_enabled;
  const user = data.user || {};
  $("auth-status").textContent = authEnabled
    ? `Halo, ${user.name || user.email || "pengguna"}!`
    : "Mode lokal";
  $("btn-logout").classList.toggle("hidden", !authEnabled);
  $("login-panel").classList.add("hidden");
  $("dashboard-shell").classList.remove("hidden");
  return true;
}

// ── Environment check ────────────────────────────────────────────────
async function checkEnv() {
  const envStatus = $("env-status");
  try {
    const response = await apiFetch("api/env");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const env = await response.json();
    const router = env.ai && env.ai.router;
    aiReady = !!env.ai_enabled && !!(router && router.ok);
    const statuses = [
      env.ffmpeg.ok ? "FFmpeg siap" : `FFmpeg: ${env.ffmpeg.error || "tidak tersedia"}`,
      env.model_cached ? "Model medium tersedia" : "Model medium belum tersedia",
      !env.ai_enabled ? "Catatan AI nonaktif" : aiReady ? "Catatan AI siap" : "9router tidak terhubung",
    ];
    envStatus.textContent = statuses.join(" · ");
    envStatus.className = env.ffmpeg.ok && env.model_cached && (!env.ai_enabled || aiReady) ? "env-ready" : "env-warning";
    envStatus.title = !env.ai_enabled || aiReady ? "" : (router && router.error) || "Nyalakan 9router terlebih dahulu";
    maxUploadBytes = Number.isFinite(Number(env.max_upload_bytes)) && Number(env.max_upload_bytes) > 0
      ? Number(env.max_upload_bytes) : maxUploadBytes;
    const aiTitle = !env.ai_enabled
      ? "Fitur AI dimatikan di server ini"
      : aiReady ? "9router siap digunakan" : "Nyalakan 9router terlebih dahulu";
    syncActionControls();
    btnAINotulen.title = aiTitle;
    btnAICleanup.title = aiTitle;
    btnAIDocument.title = aiTitle;
    if (env.settings) {
      if (env.settings.model && [...$("model").options].some(o => o.value === env.settings.model)) {
        $("model").value = env.settings.model;
      }
      if (env.settings.language && [...$("language").options].some(o => o.value === env.settings.language)) {
        $("language").value = env.settings.language;
      }
    }
  } catch (error) {
    aiReady = false;
    btnAINotulen.disabled = true;
    btnAICleanup.disabled = true;
    btnAIDocument.disabled = true;
    envStatus.textContent = "Server tidak merespons.";
    envStatus.className = "env-warning";
    envStatus.title = "Periksa server lalu muat ulang halaman.";
  }
}

// ── Drop zone / file picker ──────────────────────────────────────────
function handleSelectedInputFile() {
  if (fileInput.files && fileInput.files.length) setFile(fileInput.files[0]);
}

function clearSelectedFile() {
  if (running) return;
  selectedFile = null;
  uploadedPath = null;
  fileInput.value = "";
  $("file-info").classList.add("hidden");
  btnTranscribe.disabled = true;
  statusText.textContent = "Siap. Tambahkan rekaman untuk memulai.";
  log("Pilihan berkas dihapus.");
}

fileInput.addEventListener("change", handleSelectedInputFile);
btnRemoveFile.addEventListener("click", clearSelectedFile);
dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  if (event.dataTransfer.files.length) setFile(event.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});

function formatBytes(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function setFile(file) {
  const ext = file.name.includes(".") ? `.${file.name.split(".").pop().toLowerCase()}` : "";
  selectedFile = null;
  uploadedPath = null;
  if (!supportedMediaExtensions.has(ext)) {
    $("file-info").classList.add("hidden");
    statusText.textContent = "Format audio tidak didukung.";
    log(`Berkas ditolak: format ${ext || "tanpa ekstensi"} tidak didukung.`, "err");
    btnTranscribe.disabled = true;
    return;
  }
  $("file-name").textContent = file.name;
  $("file-meta").textContent = `${formatBytes(file.size)} · ${file.type || "audio"}`;
  $("file-info").classList.remove("hidden");
  if (file.size > maxUploadBytes) {
    statusText.textContent = `Berkas terlalu besar. Maksimum ${formatBytes(maxUploadBytes)}.`;
    log(`Berkas ditolak sebelum pengunggahan: ukuran ${formatBytes(file.size)} melebihi batas ${formatBytes(maxUploadBytes)}.`, "err");
    btnTranscribe.disabled = true;
    return;
  }
  selectedFile = file;
  btnTranscribe.disabled = running;
  log(`Berkas dipilih: ${file.name}`);
}

function uploadFile(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    uploadRequest = xhr;
    xhr.open("POST", "api/upload");
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const ratio = event.loaded / event.total;
      setProgress(Math.round(ratio * 20), `Mengunggah berkas... ${Math.round(ratio * 100)}%`);
    });
    xhr.addEventListener("load", () => {
      uploadRequest = null;
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else reject(new Error((xhr.response && xhr.response.detail) || "Pengunggahan gagal"));
    });
    xhr.addEventListener("error", () => {
      uploadRequest = null;
      reject(new Error("Pengunggahan gagal karena koneksi terputus"));
    });
    xhr.addEventListener("abort", () => {
      uploadRequest = null;
      reject(new DOMException("Pengunggahan dibatalkan", "AbortError"));
    });
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

// ── Upload + transcribe ──────────────────────────────────────────────
btnTranscribe.addEventListener("click", async () => {
  if (!selectedFile || running || selectedFile.size > maxUploadBytes) return;
  setActionControlsLocked(true);
  running = true;
  currentJobId = null;
  currentJobKind = null;
  btnCancel.disabled = false;
  resetResult();
  setProgress(0, "");
  statusText.textContent = "Mengunggah berkas...";
  log("Mengunggah berkas ke server...");
  try {
    const up = await uploadFile(selectedFile);
    uploadedPath = up.path;
    setProgress(20, "Pengunggahan selesai. Menyiapkan transkripsi...");
    log(`Pengunggahan selesai: ${up.filename} (${formatBytes(up.size)})`);
    const body = { audio_path: uploadedPath, model: $("model").value, language: $("language").value };
    const response = await apiFetch("api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Gagal memulai transkripsi");
    }
    const job = await response.json();
    currentJobId = job.id;
    currentJobKind = job.kind || "transcribe";
    log(`Transkripsi dimulai: ${job.id} (model=${body.model}, bahasa=${body.language})`);
    statusText.textContent = "Transkripsi sedang diproses...";
    connectSSE(job.id);
    startJobStatusPolling(job.id);
  } catch (error) {
    if (error.name === "AbortError") {
      statusText.textContent = "Pengunggahan dibatalkan.";
      endJob();
      return;
    }
    setError(error.message);
  }
});

// ── Durable job status fallback ──────────────────────────────────────
function stopJobStatusPolling() {
  if (jobStatusTimer) {
    window.clearInterval(jobStatusTimer);
    jobStatusTimer = null;
  }
}

function applyJobStatus(job) {
  if (!job || job.id !== currentJobId) return;
  const rawProgress = Number(job.progress) || 0;
  // Perkiraan hanya untuk satu panggilan AI yang panjang; job yang melaporkan
  // progres per bagian memakai angka aslinya.
  const waitingOnAi = ["ai_cleanup", "ai_notulen"].includes(currentJobKind) && job.status === "running"
    && rawProgress >= 25 && rawProgress < 80 && /Memanggil AI/i.test(job.message || "");
  if (waitingOnAi) {
    if (!aiProgressTimer) startAiProgressEstimate("AI sedang bekerja · persentase perkiraan");
    return;
  }
  const percent = displayPercent(rawProgress);
  if (job.status === "pending" && job.queue_ahead !== null && job.queue_ahead !== undefined && Number.isFinite(Number(job.queue_ahead))) {
    const ahead = Number(job.queue_ahead);
    const message = ahead === 0
      ? "Antrean · Anda berikutnya"
      : `Masuk antrean · ${ahead} pekerjaan di depan Anda`;
    advanceProgress(percent, message);
    return;
  }
  advanceProgress(percent, job.message || "Proses sedang berjalan...");
}

function startAiProgressEstimate(message) {
  stopAiProgressEstimate();
  aiProgressValue = Math.max(aiProgressValue, progressFloor, 25);
  advanceProgress(aiProgressValue, message || "AI sedang bekerja · durasi bervariasi");
  aiProgressTimer = window.setInterval(() => {
    if (aiProgressValue < 78) {
      aiProgressValue = Math.min(78, aiProgressValue + 1);
      advanceProgress(aiProgressValue, "AI sedang bekerja · persentase perkiraan");
    }
  }, 2500);
}

function stopAiProgressEstimate() {
  if (aiProgressTimer) {
    window.clearInterval(aiProgressTimer);
    aiProgressTimer = null;
  }
}

async function pollJobStatus(jobId) {
  if (!running || jobId !== currentJobId) return;
  try {
    const response = await apiFetch(`api/jobs/${encodeURIComponent(jobId)}`);
    if (!response.ok) return;
    const job = await response.json();
    applyJobStatus(job);
    if (!["pending", "running"].includes(job.status)) stopJobStatusPolling();
  } catch (error) {
    // SSE remains the primary channel; a transient polling failure is harmless.
  }
}

function startJobStatusPolling(jobId) {
  stopJobStatusPolling();
  pollJobStatus(jobId);
  jobStatusTimer = window.setInterval(() => pollJobStatus(jobId), 5000);
}

// ── SSE stream ───────────────────────────────────────────────────────
function connectSSE(jobId, resume = false) {
  if (eventSource) eventSource.close();
  // Sambungan ulang melanjutkan dari event terakhir yang diterima; job baru mulai dari awal.
  if (!resume) sseEventCount = 0;
  eventSource = new EventSource(`api/jobs/${jobId}/stream?after=${sseEventCount}`);
  const on = (type, handler) => eventSource.addEventListener(type, (event) => {
    if (event.lastEventId) sseEventCount = Number(event.lastEventId) || sseEventCount;
    handler(event);
  });
  on("log", (event) => log(JSON.parse(event.data).message));
  on("progress", (event) => {
    const data = JSON.parse(event.data);
    stopAiProgressEstimate();
    aiProgressValue = Math.max(aiProgressValue, Number(data.percent) || 0);
    advanceProgress(displayPercent(data.percent), data.message);
    if (["ai_cleanup", "ai_notulen"].includes(currentJobKind) && /Memanggil AI/i.test(data.message || "")) {
      startAiProgressEstimate("AI sedang bekerja · persentase perkiraan");
    }
  });
  on("segment", (event) => {
    const data = JSON.parse(event.data);
    logSegment(data.start, data.text);
  });
  on("finished", async (event) => {
    const data = JSON.parse(event.data);
    if (currentJobKind === "ai_cleanup") {
      setProgress(100, "Transkrip rapi AI selesai.");
      if (data.metadata && data.metadata.docx_path) resultFileLink(data.metadata.docx_path, btnDownloadCleaned);
      if (data.metadata && data.metadata.md_path) resultFileLink(data.metadata.md_path, btnDownloadCleanedMd);
      await loadResult(data.output_dir, data.metadata, "cleaned");
      return;
    }
    if (currentJobKind === "ai_notulen") {
      setProgress(100, "Notulensi rapat AI selesai.");
      if (data.metadata && data.metadata.docx_path) resultFileLink(data.metadata.docx_path, btnDownloadMinutes);
      if (data.metadata && data.metadata.md_path) resultFileLink(data.metadata.md_path, btnDownloadMinutesMd);
      if (data.metadata && data.metadata.pdf_path) setPdfLink(data.metadata.pdf_path);
      await loadResult(data.output_dir, data.metadata, "ai");
      return;
    }
    if (currentJobKind === "ai_document") {
      setProgress(100, "Dokumen resmi selesai.");
      const meta = data.metadata || {};
      currentDocJenis = meta.jenis || currentDocJenis;
      // Tautan dokumen resmi diisi sendiri; tombol DOCX/PDF umum tetap milik notulensi.
      await loadResult(data.output_dir, null, "doc");
      if (meta.pdf_path) resultFileLink(meta.pdf_path, btnDownloadDocPdf);
      if (meta.docx_path) resultFileLink(meta.docx_path, btnDownloadDocDocx);
      if (meta.md_path) resultFileLink(meta.md_path, btnDownloadDocMd);
      return;
    }
    await loadResult(data.output_dir, data.metadata, "txt");
    setProgress(100, "Selesai.");
  });
  on("error", (event) => {
    if (!event.data) return;
    try {
      const data = JSON.parse(event.data);
      setError(data.error || "Proses gagal.");
    } catch (error) {
      setError("Proses gagal.");
    }
  });
  on("cancelled", () => {
    statusText.textContent = "Dibatalkan.";
    const cancelledLabels = { ai_notulen: "Pembuatan catatan AI", ai_document: "Penyusunan dokumen resmi", ai_cleanup: "Perapian transkrip" };
    log(`${cancelledLabels[currentJobKind] || "Transkripsi"} dibatalkan.`);
    setProgress(0, "Dibatalkan.");
    endJob();
  });
  on("job_end", () => endJob());
  eventSource.onerror = () => {
    if (!running || jobId !== currentJobId) {
      if (eventSource) eventSource.close();
      return;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    statusText.textContent = "Koneksi progress tersambung ulang...";
    window.setTimeout(() => {
      if (running && jobId === currentJobId) connectSSE(jobId, true);
    }, 2000);
  };
}

function endJob() {
  stopAiProgressEstimate();
  stopJobStatusPolling();
  if (eventSource) { eventSource.close(); eventSource = null; }
  running = false;
  aiRunning = false;
  currentJobKind = null;
  // Job berikutnya mulai dari nol; angka di layar dibiarkan sampai job itu melapor.
  progressFloor = 0;
  aiProgressValue = 0;
  setActionControlsLocked(false);
  syncActionControls();
  btnCancel.disabled = true;
  refreshHistory();
}

// ── Cancel ───────────────────────────────────────────────────────────
btnCancel.addEventListener("click", async () => {
  if (uploadRequest) {
    statusText.textContent = "Membatalkan pengunggahan...";
    uploadRequest.abort();
    return;
  }
  if (!currentJobId) return;
  statusText.textContent = "Membatalkan proses...";
  btnCancel.disabled = true;
  try {
    const response = await apiFetch(`api/jobs/${currentJobId}/cancel`, { method: "POST" });
  } catch (error) {
    setError(error.message);
  }
});

// ── Results ───────────────────────────────────────────────────────────
function resetResult() {
  previewRequestId += 1;
  previewEl.textContent = "Belum ada hasil transkripsi.";
  $("result-actions").hidden = true;
  btnDownloadTranscript.classList.add("hidden");
  btnDownloadCleaned.classList.add("hidden");
  btnDownloadMinutes.classList.add("hidden");
  btnDownloadCleanedMd.classList.add("hidden");
  btnDownloadMinutesMd.classList.add("hidden");
  btnDownloadPdf.classList.add("hidden");
  [btnDownloadDocPdf, btnDownloadDocDocx, btnDownloadDocMd].forEach((button) => button.classList.add("hidden"));
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.tab === "txt";
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.setAttribute("tabindex", active ? "0" : "-1");
  });
  previewEl.removeAttribute("aria-labelledby");
  $("result-actions").dataset.activeTab = "txt";
}
function resultFileLink(path, button) {
  const folderName = resultFiles || path.split(/[\\/]/).slice(-2, -1)[0];
  const fileName = path.split(/[\\/]/).pop();
  button.href = `api/history/${encodeURIComponent(folderName)}/file/${encodeURIComponent(fileName)}?download=1`;
  button.classList.remove("hidden");
}
function setTranscriptLink(folderName) {
  const stem = folderName.replace(/[^\w.\- ]/g, "").trim().slice(0, 50) || "transkrip";
  resultFileLink(`${folderName}/Transkrip_${stem}.docx`, btnDownloadTranscript);
}
function setPdfLink(path) { resultFileLink(path, btnDownloadPdf); }
function officialDocJenis(names) {
  const available = Object.keys(docFilePrefixes).filter((jenis) => names.includes(`dokumen_${jenis}.md`));
  if (available.includes(currentDocJenis)) return currentDocJenis;
  return available[0] || null;
}
function syncOfficialDocLinks(names, folderName) {
  const jenis = officialDocJenis(names);
  // Berkas lama diberi akhiran nomor urut, jadi berkas terbaru adalah nama terpendek.
  const latest = (extension) => names
    .filter((file) => jenis && file.startsWith(docFilePrefixes[jenis]) && file.toLowerCase().endsWith(extension))
    .sort((a, b) => a.length - b.length)[0];
  [[latest(".pdf"), btnDownloadDocPdf], [latest(".docx"), btnDownloadDocDocx],
    [jenis ? `dokumen_${jenis}.md` : null, btnDownloadDocMd]].forEach(([file, button]) => {
    if (file) resultFileLink(`${folderName}/${file}`, button);
    else button.classList.add("hidden");
  });
}
function syncDownloadLinks(files, folderName) {
  const names = files || [];
  syncOfficialDocLinks(names, folderName);
  // Setiap tombol unduh terikat pada satu berkas menurut awalan namanya.
  const link = (file, button) => {
    if (file) resultFileLink(`${folderName}/${file}`, button);
    else button.classList.add("hidden");
  };
  const find = (prefix, extension) => names.find((file) => file.startsWith(prefix) && file.toLowerCase().endsWith(extension));
  link(find("TranskripRapiAI_", ".docx"), btnDownloadCleaned);
  link(names.includes("transkrip_rapi_ai.md") ? "transkrip_rapi_ai.md" : null, btnDownloadCleanedMd);
  link(find("NotulenAI_", ".docx"), btnDownloadMinutes);
  link(names.includes("notulen_ai.md") ? "notulen_ai.md" : null, btnDownloadMinutesMd);
  link(find("NotulenAI_", ".pdf"), btnDownloadPdf);
}

async function loadResult(outputDir, metadata, initialTab = "txt") {
  if (!outputDir) return;
  const folderName = outputDir.split(/[\\/]/).pop();
  resultFiles = folderName;
  selectedHistoryName = folderName;
  currentResultPath = folderName;
  $("result-actions").hidden = false;
  setTranscriptLink(folderName);
  $("result-path").textContent = `Hasil: ${folderName}`;
  log(`Selesai. Hasil: ${folderName}`);
  if (metadata) {
    log(`   Segmen: ${metadata.segment_count || "-"} · durasi proses: ${metadata.duration_s || "-"} detik · durasi audio: ${metadata.audio_duration_s || "-"} detik`);
  }
  await showTab(initialTab);
  refreshHistory();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
});
document.querySelector(".tabs").addEventListener("keydown", (event) => {
  if (!event.target.matches('[role="tab"]')) return;
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const current = tabs.indexOf(event.target);
  const next = event.key === "ArrowRight" ? (current + 1) % tabs.length
    : event.key === "ArrowLeft" ? (current - 1 + tabs.length) % tabs.length
      : event.key === "Home" ? 0
        : event.key === "End" ? tabs.length - 1 : current;
  if (next !== current) {
    event.preventDefault();
    tabs[next].focus();
    showTab(tabs[next].dataset.tab);
  }
});
async function showTab(tab) {
  document.querySelectorAll(".tab").forEach((item) => {
    const active = item.dataset.tab === tab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
    item.setAttribute("tabindex", active ? "0" : "-1");
  });
  previewEl.setAttribute("aria-labelledby", `tab-${tab}`);
  $("result-actions").dataset.activeTab = tab;
  if (!resultFiles) return;
  const requestId = ++previewRequestId;
  const setPreview = (text) => {
    if (requestId === previewRequestId) previewEl.textContent = text;
  };
  setPreview("Memuat hasil...");
  if (tab === "ai") {
    try {
      const response = await apiFetch(`api/history/${encodeURIComponent(resultFiles)}/file/notulen_ai.txt`);
      if (!response.ok) {
        setPreview("Belum ada notulensi untuk hasil ini. Pilih \"Buat notulensi rapat\" untuk membuatnya.");
        return;
      }
      const data = await response.json();
      setPreview(data.content.length > 200000 ? data.content.slice(0, 200000) + "\n...(dipotong)" : data.content);
    } catch (error) { setPreview(`Gagal memuat hasil: ${error.message}`); }
    return;
  }
  if (tab === "doc") {
    const empty = "Belum ada dokumen resmi untuk hasil ini. Pilih \"Susun dokumen resmi\" untuk membuatnya.";
    try {
      const candidates = [currentDocJenis, ...Object.keys(docFilePrefixes)].filter(Boolean);
      for (const jenis of [...new Set(candidates)]) {
        const response = await apiFetch(`api/history/${encodeURIComponent(resultFiles)}/file/dokumen_${jenis}.md`);
        if (!response.ok) continue;
        const data = await response.json();
        setPreview(data.content);
        return;
      }
      setPreview(empty);
    } catch (error) { setPreview(`Gagal memuat hasil: ${error.message}`); }
    return;
  }
  if (tab === "cleaned") {
    try {
      const response = await apiFetch(`api/history/${encodeURIComponent(resultFiles)}/file/transkrip_rapi_ai.txt`);
      if (!response.ok) {
        setPreview("Belum ada transkrip rapi AI. Pilih \"Rapikan transkrip\" untuk membuatnya.");
        return;
      }
      const data = await response.json();
      setPreview(data.content.length > 200000 ? data.content.slice(0, 200000) + "\n...(dipotong)" : data.content);
    } catch (error) { setPreview(`Gagal memuat hasil: ${error.message}`); }
    return;
  }
  const fileName = tab === "txt" ? "transkrip.txt" : "transkrip.json";
  try {
    const response = await apiFetch(`api/history/${encodeURIComponent(resultFiles)}/file/${fileName}`);
    if (!response.ok) { setPreview(`Berkas ${fileName} tidak tersedia.`); return; }
    const data = await response.json();
    setPreview(data.content.length > 200000 ? data.content.slice(0, 200000) + "\n...(dipotong)" : data.content);
  } catch (error) { setPreview(`Gagal memuat hasil: ${error.message}`); }
}
// ── AI actions ───────────────────────────────────────────────────────
btnAICleanup.addEventListener("click", async () => {
  if (!currentResultPath || !aiReady || running) return;
  setActionControlsLocked(true);
  running = true;
  currentJobKind = "ai_cleanup";
  btnCancel.disabled = false;
  statusText.textContent = "AI sedang merapikan transkrip...";
  log("Memanggil AI perapian transkrip melalui 9router lokal...");
  try {
    const response = await apiFetch("api/transcript/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_name: resultFiles }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Gagal memulai perapian transkrip AI");
    }
    const job = await response.json();
    currentJobId = job.id;
    currentJobKind = job.kind || "ai_cleanup";
    log(`Perapian transkrip AI dimulai: ${job.id}`);
    connectSSE(job.id);
  } catch (error) {
    setError(error.message);
  }
});

btnAINotulen.addEventListener("click", async () => {
  if (!currentResultPath || !aiReady || running) return;
  aiRunning = true;
  setActionControlsLocked(true);
  running = true;
  currentJobKind = "ai_notulen";
  btnCancel.disabled = false;
  statusText.textContent = "AI sedang menyusun notulensi rapat...";
  log("Memanggil AI notulensi rapat melalui 9router lokal...");
  try {
    const response = await apiFetch("api/notulen/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_name: resultFiles }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Gagal memulai notulensi rapat AI");
    }
    const job = await response.json();
    currentJobId = job.id;
    currentJobKind = job.kind || "ai_notulen";
    log(`Notulensi rapat AI dimulai: ${job.id}`);
    connectSSE(job.id);
  } catch (error) {
    setError(error.message);
  }
});
// ── Dokumen resmi ────────────────────────────────────────────────────
function renderDocFields() {
  const type = (docTypes || []).find((item) => item.jenis === docJenis.value);
  docFields.replaceChildren();
  ((type && type.kepala) || []).forEach((field) => {
    const wrapper = document.createElement("div");
    wrapper.className = "doc-field";
    const label = document.createElement("label");
    label.htmlFor = `doc-field-${field.kunci}`;
    label.textContent = field.label;
    const input = document.createElement("input");
    input.type = "text";
    input.id = `doc-field-${field.kunci}`;
    input.dataset.kunci = field.kunci;
    input.maxLength = 200;
    input.autocomplete = "off";
    wrapper.append(label, input);
    docFields.append(wrapper);
  });
}
docJenis.addEventListener("change", renderDocFields);
$("doc-cancel").addEventListener("click", () => docDialog.close());

btnAIDocument.addEventListener("click", async () => {
  if (!currentResultPath || !aiReady || running) return;
  try {
    if (!docTypes) {
      const response = await apiFetch("api/documents/types");
      if (!response.ok) throw new Error("Daftar jenis dokumen tidak dapat dimuat");
      docTypes = (await response.json()).items || [];
      docJenis.replaceChildren(...docTypes.map((item) => new Option(item.nama, item.jenis)));
      renderDocFields();
    }
    if (!docJudul.value || docJudul.dataset.folder !== resultFiles) {
      docJudul.value = resultFiles.replace(/^\d{2,}_/, "").replace(/[_.]+/g, " ").trim();
      docJudul.dataset.folder = resultFiles;
    }
    docDialog.showModal();
  } catch (error) {
    setError(error.message);
  }
});

$("doc-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  docDialog.close();
  if (!currentResultPath || !aiReady || running) return;
  const kepala = {};
  docFields.querySelectorAll("input").forEach((input) => { kepala[input.dataset.kunci] = input.value.trim(); });
  setActionControlsLocked(true);
  running = true;
  currentJobKind = "ai_document";
  btnCancel.disabled = false;
  statusText.textContent = "AI sedang menyusun dokumen resmi...";
  log("Menyusun dokumen resmi dari transkrip...");
  try {
    const response = await apiFetch("api/documents/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_name: resultFiles, jenis: docJenis.value, judul: docJudul.value.trim(), kepala }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Gagal memulai penyusunan dokumen resmi");
    }
    const job = await response.json();
    currentJobId = job.id;
    currentJobKind = job.kind || "ai_document";
    log(`Penyusunan dokumen resmi dimulai: ${job.id}`);
    connectSSE(job.id);
  } catch (error) {
    setError(error.message);
  }
});

async function refreshHistory() {
  historyEl.setAttribute("aria-busy", "true");
  setHistoryState("Memuat riwayat...");
  try {
    const response = await apiFetch("api/history");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    historyEl.replaceChildren();
    if (!data.items.length) {
      setHistoryState("Belum ada hasil. Mulai dengan menambahkan rekaman.", "empty");
      return;
    }
    data.items.forEach((item) => {
      const li = document.createElement("li");
      li.className = `history-item${selectedHistoryName === item.name ? " active" : ""}`;
      const open = document.createElement("button");
      open.className = "history-open";
      open.type = "button";
      open.textContent = item.name;
      open.title = `Buka hasil ${item.name}`;
      open.setAttribute("aria-label", `Buka hasil ${item.name}`);
      open.disabled = running;
      open.setAttribute("aria-disabled", running ? "true" : "false");
      const remove = document.createElement("button");
      remove.className = "history-delete";
      remove.type = "button";
      remove.disabled = running;
      remove.setAttribute("aria-disabled", running ? "true" : "false");
      remove.title = `Hapus ${item.name}`;
      remove.setAttribute("aria-label", `Hapus riwayat ${item.name}`);
      remove.textContent = "×";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Hapus hasil ${item.name} beserta semua berkas di dalamnya?`)) return;
        remove.disabled = true;
        try {
          const result = await apiFetch(`api/history/${encodeURIComponent(item.name)}`, { method: "DELETE" });
          const error = await result.json().catch(() => ({}));
          if (!result.ok) throw new Error(error.detail || "Gagal menghapus riwayat");
          if (resultFiles === item.name) {
            selectedHistoryName = null;
            resultFiles = null;
            currentResultPath = null;
            currentResultFiles = [];
            resetResult();
          }
          log(`Riwayat dihapus: ${item.name}`);
          refreshHistory();
        } catch (error) {
          remove.disabled = false;
          showHistoryError(error.message);
        }
      });
      open.addEventListener("click", () => selectHistoryItem(item, li));
      li.append(open, remove);
      historyEl.appendChild(li);
    });
  } catch (error) {
    showHistoryError("Riwayat gagal dimuat. Coba lagi.");
  } finally {
    historyEl.setAttribute("aria-busy", "false");
  }
}

function selectHistoryItem(item, li) {
  document.querySelectorAll(".history li").forEach((entry) => entry.classList.remove("active"));
  li.classList.add("active");
  selectedHistoryName = item.name;
  resultFiles = item.name;
  currentResultPath = item.name;
  currentResultFiles = item.files || [];
  $("result-actions").hidden = false;
  setTranscriptLink(item.name);
  $("result-path").textContent = `Hasil: ${item.name}`;
  syncDownloadLinks(currentResultFiles, item.name);
  showTab("txt");
}
function setHistoryState(message, stateClass = "") {
  historyEl.replaceChildren();
  const state = document.createElement("li");
  state.className = `history-state${stateClass ? ` ${stateClass}` : ""}`;
  state.textContent = message;
  historyEl.appendChild(state);
}

function showHistoryError(message) {
  setHistoryState(message, "error");
  const retry = document.createElement("button");
  retry.className = "btn btn-text history-retry";
  retry.type = "button";
  retry.textContent = "Muat ulang riwayat";
  retry.addEventListener("click", refreshHistory);
  historyEl.querySelector(".history-state").appendChild(retry);
}

// ── Helpers ──────────────────────────────────────────────────────────
// Persentase job dari server → persentase yang ditampilkan. Pada transkripsi,
// 20% pertama adalah pengunggahan, jadi progres server mengisi sisa 20-100.
function displayPercent(percent) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  return currentJobKind === "transcribe" ? Math.round(20 + value * 0.8) : value;
}
// Progres job yang sedang berjalan tidak pernah mundur: event SSE, polling status,
// dan perkiraan AI bisa tiba tidak berurutan, jadi nilai yang lebih kecil diabaikan.
function advanceProgress(percent, message) {
  setProgress(Math.max(progressFloor, Number(percent) || 0), message);
}
function setProgress(percent, message) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  progressFloor = value;
  progressBar.style.width = `${value}%`;
  progressLabel.textContent = `${value}%`;
  document.querySelector(".progress-wrap").setAttribute("aria-valuenow", String(value));
  if (message) statusText.textContent = message;
}
function setError(message) {
  statusText.textContent = "Terjadi kesalahan.";
  log(message, "err");
  setProgress(0, "Proses gagal.");
  endJob();
}
function log(message, cls = "") {
  const line = document.createElement("div");
  const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
  if (cls) line.className = cls;
  line.textContent = `[${time}] ${message}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}
function logSegment(start, text) {
  const line = document.createElement("div");
  line.className = "seg";
  const preview = text.length > 150 ? text.slice(0, 147) + "..." : text;
  line.textContent = `[${Math.floor(start)}s] ${preview}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

$("btn-logout").addEventListener("click", async () => {
  try { await apiFetch("api/auth/logout", { method: "POST" }); }
  finally { window.location.assign(window.location.pathname); }
});

const portalIntro = $("portal-intro");
const portalEnter = $("portal-enter");
const appShell = $("app-shell");
const workspaceHeading = $("workspace-heading");
let portalBusy = false;
if (portalIntro && portalEnter && appShell) {
  const setPortalStatus = (message) => {
    let status = $("portal-status");
    if (!status) {
      status = document.createElement("p");
      status.id = "portal-status";
      status.className = "portal-login-note portal-status";
      status.setAttribute("role", "status");
      portalEnter.parentElement.after(status);
    }
    status.textContent = message;
  };
  portalEnter.addEventListener("click", async () => {
    if (portalBusy) return;
    portalBusy = true;
    portalEnter.disabled = true;
    portalEnter.textContent = "Memeriksa akses...";
    try {
      const response = await apiFetch("api/auth/me");
      if (response.status === 401) {
        const next = `${window.location.pathname}${window.location.search}`;
        window.location.assign(`api/auth/login?next=${encodeURIComponent(next)}`);
        return;
      }
      if (!response.ok) throw new Error("Status login tidak dapat diperiksa.");
      const data = await response.json();
      if (data.auth_enabled && !data.user) throw new Error("Sesi login tidak ditemukan.");
      portalIntro.classList.add("portal-opening");
      window.setTimeout(() => {
        portalIntro.classList.add("hidden");
        appShell.removeAttribute("aria-hidden");
        appShell.removeAttribute("inert");
        startDashboard();
        workspaceHeading?.setAttribute("tabindex", "-1");
        workspaceHeading?.focus();
      }, 350);
    } catch (error) {
      portalEnter.disabled = false;
      portalEnter.textContent = "Buka Pandora";
      setPortalStatus("Belum dapat memeriksa akses. Coba lagi sebentar ya.");
    } finally {
      portalBusy = false;
    }
  });
}
document.addEventListener("keydown", (event) => {
  if (!portalIntro || portalIntro.classList.contains("hidden")) return;
  if (event.key === "Escape") portalEnter?.focus();
});
portalEnter?.focus();


async function startDashboard() {
  try {
    if (!(await checkAuth())) return;
    await Promise.all([checkEnv(), refreshHistory(), recoverActiveJob()]);
    startQueueStatusPolling();
  } catch (error) {
    $("auth-status").textContent = "Gagal memeriksa login.";
    $("login-panel").classList.remove("hidden");
    $("dashboard-shell").classList.add("hidden");
  }
}

async function recoverActiveJob() {
  try {
    const response = await apiFetch("api/jobs/active");
    if (!response.ok) return;
    const data = await response.json();
    const job = (data.items || [])[0];
    if (!job || !["pending", "running"].includes(job.status)) return;
    currentJobId = job.id;
    currentJobKind = job.kind || "transcribe";
    running = true;
    aiRunning = currentJobKind === "ai_notulen";
    setActionControlsLocked(true);
    btnCancel.disabled = false;
    btnTranscribe.disabled = true;
    btnAINotulen.disabled = true;
    setProgress(displayPercent(job.progress || 0), job.message || "Memulihkan proses...");
    log(`Memulihkan proses ${job.id} setelah halaman dimuat ulang...`);
    connectSSE(job.id);
  } catch (error) { log("Proses sebelumnya tidak dapat dipulihkan.", "err"); }
}

checkAuth().then((authenticated) => {
  const params = new URLSearchParams(window.location.search);
  if (authenticated && authEnabled && params.get("auth") !== "success" && portalIntro && appShell) {
    portalIntro.classList.add("hidden");
    appShell.removeAttribute("aria-hidden");
    appShell.removeAttribute("inert");
    startDashboard();
    return;
  }
  if (authenticated && params.get("auth") === "success" && portalIntro && !portalIntro.classList.contains("hidden")) {
    const status = document.createElement("p");
    status.className = "portal-login-note portal-status";
    status.setAttribute("role", "status");
    status.textContent = "Login berhasil! Selamat datang di Pandora.";
    portalEnter?.parentElement.after(status);
    params.delete("auth");
    const query = params.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }
}).catch(() => {
  authEnabled = true;
  $("auth-status").textContent = "Belum masuk · akun Google UGM";
});
setInterval(() => {
  if (!$("dashboard-shell").classList.contains("hidden")) refreshHistory();
}, 15000);
window.addEventListener("beforeunload", () => {
  if (eventSource) eventSource.close();
});
