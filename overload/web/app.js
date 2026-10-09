(() => {
  "use strict";

  const state = {
    projects: [],
    projectId: null,
    projectName: "",
    assets: [],
    health: null,
    editor: "premiere",
    filter: "all",
    view: "overview",
    jobs: new Map(),
    pollingJobs: new Set(),
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: { ...(options.headers || {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || `Erreur HTTP ${response.status}`);
      error.status = response.status;
      error.details = payload.details;
      throw error;
    }
    return payload;
  }

  function post(path, body = {}) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  function notify(message, kind = "", timeout = 4400) {
    const toast = document.createElement("div");
    toast.className = `toast ${kind}`.trim();
    toast.textContent = message;
    $("#toast-region").append(toast);
    window.setTimeout(() => toast.remove(), timeout);
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return "—";
    if (bytes < 1024) return `${bytes} o`;
    const units = ["Ko", "Mo", "Go", "To"];
    let current = bytes / 1024;
    let index = 0;
    while (current >= 1024 && index < units.length - 1) { current /= 1024; index += 1; }
    return `${current.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} ${units[index]}`;
  }

  function formatDuration(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return "—";
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
  }

  function formatEta(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return "calcul…";
    if (seconds < 60) return `~${Math.ceil(seconds)} s restantes`;
    if (seconds < 3600) return `~${Math.ceil(seconds / 60)} min restantes`;
    return `~${Math.floor(seconds / 3600)} h ${Math.ceil((seconds % 3600) / 60)} min restantes`;
  }

  function integrityInfo(report = {}) {
    const integrity = report.integrity;
    const compatibility = compatibilityFor(report).status;
    if (integrity === "verified" && compatibility === "compatible") return { label: "Vérifié · prêt", className: "ready", caption: "Décodage intégral confirmé" };
    if (integrity === "verified") return { label: "Codec à vérifier", className: "review", caption: compatibilityFor(report).title || "Compatibilité à contrôler" };
    if (integrity === "readable") return { label: "Lecture détectée", className: "review", caption: "Intégrité complète non vérifiée" };
    if (integrity === "incomplete") return { label: "Incomplet", className: "invalid", caption: "Taille inférieure à celle attendue" };
    if (integrity === "size_mismatch") return { label: "Taille différente", className: "invalid", caption: "Comparaison avec la taille attendue" };
    if (integrity === "not_media") return { label: "Média illisible", className: "invalid", caption: "Aucun flux reconnu" };
    if (integrity === "corrupt") return { label: "Lecture impossible", className: "invalid", caption: "Fichier incomplet ou endommagé" };
    return { label: "Non vérifié", className: "unknown", caption: "FFprobe ou FFmpeg requis" };
  }

  function compatibilityFor(report = {}) {
    return report.compatibility_by_editor?.[state.editor] || report.compatibility || {
      status: "unknown", title: "Compatibilité inconnue", message: "Aucun diagnostic disponible.",
    };
  }

  function fileSymbol(asset) {
    const type = asset.media_type || asset.analysis?.media_type;
    if (type === "audio") return { glyph: "♫", className: "audio" };
    if (type === "image") return { glyph: "▧", className: "image" };
    return { glyph: "▧", className: "" };
  }

  function getCurrentJobs() {
    return [...state.jobs.values()].filter((job) => job.project_id === state.projectId);
  }

  function renderHealth() {
    if (!state.health) return;
    const ffprobe = $("#ffprobe-status");
    const ffmpeg = $("#ffmpeg-status");
    ffprobe.className = `tool-pill ${state.health.ffprobe.available ? "is-ok" : "is-missing"}`;
    ffprobe.innerHTML = `<span class="mini-status"></span><span>FFprobe : ${state.health.ffprobe.available ? "détecté" : "absent"}</span>`;
    ffmpeg.className = `tool-pill ${state.health.ffmpeg.available ? "is-ok" : "is-missing"}`;
    ffmpeg.innerHTML = `<span class="mini-status"></span><span>FFmpeg : ${state.health.ffmpeg.available ? "détecté" : "absent"}</span>`;
    const engine = $("#conversion-engine-badge");
    engine.className = `profile-engine ${state.health.ffmpeg.available ? "is-ok" : "is-missing"}`;
    engine.innerHTML = `<span class="mini-status"></span><span>${state.health.ffmpeg.available ? "FFmpeg prêt" : "FFmpeg requis"}</span>`;
    $("#app-version").textContent = state.health.version || "0.1.0";

    for (const editor of state.health.editors || []) {
      const card = $(`[data-editor-card="${editor.id}"]`);
      if (!card) continue;
      const status = $(".integration-status", card);
      status.textContent = editor.installed ? "Détecté" : "Non détecté";
      status.classList.toggle("available", editor.installed);
      const action = $("[data-open-latest-editor]", card);
      if (action && !editor.installed) action.title = "Le logiciel n'a pas été détecté sur cet ordinateur.";
    }
  }

  function renderProjects() {
    const select = $("#project-select");
    select.replaceChildren();
    for (const project of state.projects) {
      const option = document.createElement("option");
      option.value = project.id;
      option.textContent = project.name;
      select.append(option);
    }
    if (state.projectId) select.value = state.projectId;
  }

  function changeView(view) {
    const known = ["overview", "media", "conversions", "integrations"];
    if (!known.includes(view)) return;
    state.view = view;
    for (const button of $$(".nav-item[data-view]")) button.classList.toggle("is-active", button.dataset.view === view);
    for (const panel of $$(".view-panel")) panel.classList.toggle("hidden", panel.id !== `${view}-view`);
    const titles = { overview: "Vue d'ensemble", media: "Médias", conversions: "Conversions", integrations: "Intégrations" };
    $("#breadcrumb-title").textContent = titles[view];
    history.replaceState(null, "", `#${view}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (view === "conversions") renderJobs();
  }

  function renderAssets() {
    const body = $("#media-table-body");
    const filtered = state.assets.filter((asset) => {
      const report = asset.analysis || {};
      if (state.filter === "all") return true;
      if (state.filter === "video" || state.filter === "audio") return asset.media_type === state.filter;
      if (state.filter === "review") return Boolean(asset.stale) || integrityInfo(report).className !== "ready";
      return true;
    });
    $("#filter-all-count").textContent = String(state.assets.length);
    $("#filter-review-count").textContent = String(state.assets.filter((asset) => asset.stale || integrityInfo(asset.analysis || {}).className !== "ready").length);
    $("#library-count").textContent = `${filtered.length} ${filtered.length === 1 ? "fichier" : "fichiers"}`;
    $("#nav-media-count").textContent = String(state.assets.length);
    $("#media-empty").classList.toggle("hidden", filtered.length > 0);
    body.replaceChildren();

    for (const asset of filtered) {
      const report = asset.analysis || {};
      const compat = compatibilityFor(report);
      const integrity = asset.stale
        ? { label: "À réanalyser", className: "review", caption: "Fichier modifié depuis le dernier diagnostic" }
        : integrityInfo(report);
      const icon = fileSymbol(asset);
      const videoCodec = report.video_codec_label || report.video_codec;
      const audioCodec = (report.audio_codec_labels || report.audio_codecs || []).join(" + ");
      const codecText = report.media_type === "image"
        ? "Image fixe"
        : videoCodec ? `${videoCodec}${audioCodec ? ` · ${audioCodec}` : report.audio_stream_count === 0 ? " · sans audio" : ""}` : (audioCodec || "Flux non identifiés");
      const resolution = report.width && report.height ? `${report.width} × ${report.height}` : (report.media_type === "audio" ? "Audio seul" : "—");
      const props = [resolution, report.frame_rate_label].filter(Boolean).join(" · ");
      const diagnostics = (report.diagnostics || []).find((diagnostic) => diagnostic.severity === "error") || (report.diagnostics || []).find((diagnostic) => diagnostic.severity === "warning");
      const reason = asset.stale ? integrity.caption : diagnostics?.title || compat.title || integrity.caption;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><div class="file-cell"><div class="file-thumb ${icon.className}">${icon.glyph}</div><div class="file-cell-copy"><strong title="${escapeHtml(asset.filename)}">${escapeHtml(asset.filename)}</strong><small>${escapeHtml(formatBytes(asset.size_bytes))}${report.duration_seconds ? ` · ${escapeHtml(formatDuration(report.duration_seconds))}` : ""}${asset.role === "converted" ? " · copie convertie" : ""}</small></div></div></td>
        <td><div class="codec-cell"><span class="format-chip">${escapeHtml(report.container || "FORMAT INCONNU")}</span><span class="codec-line" title="${escapeHtml(codecText)}">${escapeHtml(codecText)}</span></div></td>
        <td class="properties-cell"><strong>${escapeHtml(props || "—")}</strong><br>${report.media_type === "image" ? "Image fixe" : report.video_stream_count ? `${report.video_stream_count} piste${report.video_stream_count > 1 ? "s" : ""} vidéo` : ""}${report.audio_stream_count ? ` · ${report.audio_stream_count} audio` : (report.media_type === "video" ? " · sans audio" : "")}</td>
        <td><span class="diagnostic-badge ${integrity.className}" title="${escapeHtml((report.diagnostics || []).map((item) => item.message).join("\n") || reason)}">${escapeHtml(integrity.label)}</span><small class="diagnostic-subtext">${escapeHtml(reason)}</small></td>
        <td><div class="row-actions">
          <button class="row-action" type="button" data-action="open-file" data-path="${escapeHtml(asset.relative_path)}" ${!asset.stale && ["verified", "readable"].includes(report.integrity) ? "" : "disabled"} title="Ouvrir avec l'application par défaut">Ouvrir</button>
          <button class="row-action" type="button" data-action="open-editor" data-path="${escapeHtml(asset.relative_path)}" ${!asset.stale && ["verified", "readable"].includes(report.integrity) ? "" : "disabled"} title="Ouvrir dans ${escapeHtml(compat.editor_label || "le logiciel choisi")}">Dans app</button>
          <button class="row-action primary" type="button" data-action="convert" data-path="${escapeHtml(asset.relative_path)}" ${!asset.stale && state.health?.ffmpeg.available && report.media_type === "video" && ["verified", "readable"].includes(report.integrity) ? "" : "disabled"} title="${state.health?.ffmpeg.available ? "Créer une copie MP4 H.264/AAC" : "Installe FFmpeg pour convertir"}">Convertir</button>
        </div></td>`;
      body.append(tr);
    }
  }

  function renderOverview() {
    const verified = state.assets.filter((asset) => asset.analysis?.integrity === "verified").length;
    const review = state.assets.filter((asset) => asset.stale || integrityInfo(asset.analysis || {}).className !== "ready").length;
    const videos = state.assets.filter((asset) => asset.media_type === "video" && asset.analysis?.height);
    const heights = videos.map((asset) => Number(asset.analysis.height)).filter(Number.isFinite).sort((a, b) => a - b);
    let resolution = "—";
    if (heights.length) {
      const median = heights[Math.floor(heights.length / 2)];
      resolution = median >= 2100 ? "4K+" : median >= 1000 ? `${Math.round(median / 100) * 100}p` : `${median}p`;
    }
    const activeJobs = getCurrentJobs().filter((job) => ["queued", "running"].includes(job.status)).length;
    $("#stat-verified").textContent = String(verified);
    $("#stat-review").textContent = String(review);
    $("#stat-resolution").textContent = resolution;
    $("#stat-conversions").textContent = String(activeJobs);
    $("#overview-empty").classList.toggle("hidden", state.assets.length > 0);
    $("#recent-media").classList.toggle("hidden", state.assets.length === 0);
    const recent = $("#recent-media");
    recent.replaceChildren();
    for (const asset of state.assets.slice(0, 6)) {
      const icon = fileSymbol(asset);
      const info = asset.stale
        ? { label: "À réanalyser", className: "review" }
        : integrityInfo(asset.analysis || {});
      const article = document.createElement("button");
      article.type = "button";
      article.className = "recent-card";
      article.dataset.openRecent = asset.relative_path;
      article.innerHTML = `<span class="file-thumb ${icon.className}">${icon.glyph}</span><span class="recent-meta"><strong>${escapeHtml(asset.filename)}</strong><small>${escapeHtml(asset.analysis?.container || "Format inconnu")} · ${escapeHtml(info.label)}</small></span><span class="recent-status ${info.className === "ready" ? "" : info.className === "invalid" ? "invalid" : "review"}"></span>`;
      recent.append(article);
    }
    renderAssets();
  }

  function renderJobs() {
    const current = getCurrentJobs().sort((a, b) => b.created_at.localeCompare(a.created_at));
    const container = $("#conversion-jobs");
    container.replaceChildren();
    $("#conversion-empty").classList.toggle("hidden", current.length > 0);
    $("#nav-job-count").classList.toggle("hidden", current.filter((job) => ["queued", "running"].includes(job.status)).length === 0);
    $("#nav-job-count").textContent = String(current.filter((job) => ["queued", "running"].includes(job.status)).length);
    for (const job of current) {
      const percent = Math.round((Number(job.progress) || 0) * 100);
      const statusLabel = { queued: "En attente", running: "Conversion", completed: "Terminé", failed: "Échec", cancelled: "Annulé" }[job.status] || job.status;
      const active = ["queued", "running"].includes(job.status);
      const card = document.createElement("article");
      card.className = "job-card";
      const symbol = job.status === "completed" ? "✓" : "⟳";
      const progressText = job.status === "completed" ? "Copie créée · source conservée" : job.status === "failed" ? "La source est intacte" : job.status === "cancelled" ? "Conversion annulée · source intacte" : `${percent}% · ${formatEta(job.eta_seconds)}`;
      card.innerHTML = `
        <div class="job-file"><span class="file-thumb">${symbol}</span><span style="min-width:0"><strong title="${escapeHtml(job.source_name)}">${escapeHtml(job.source_name)}</strong><small>${escapeHtml(job.mode || "Profil MP4 H.264/AAC")}</small></span></div>
        <div class="job-progress-wrap"><div class="job-progress-label"><span>${escapeHtml(progressText)}</span><span>${active ? `${percent}%` : ""}</span></div><div class="job-progress-track"><div class="job-progress-bar" style="width:${job.status === "completed" ? 100 : percent}%"></div></div></div>
        <div class="job-actions"><span class="job-status ${escapeHtml(job.status)}">${escapeHtml(statusLabel)}</span>${active ? `<button class="cancel-job" type="button" data-cancel-job="${escapeHtml(job.id)}">Annuler</button>` : job.status === "completed" ? `<button class="cancel-job" type="button" data-open-output="${escapeHtml(job.output_relative_path || "")}">Ouvrir</button>` : ""}</div>
        ${job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ""}`;
      container.append(card);
    }
  }

  async function loadAssets() {
    if (!state.projectId) return;
    const projectId = encodeURIComponent(state.projectId);
    const [data, jobData] = await Promise.all([
      api(`/api/projects/${projectId}/files`),
      api(`/api/projects/${projectId}/jobs`),
    ]);
    state.assets = data.assets || [];
    for (const job of (jobData.jobs || [])) {
      state.jobs.set(job.id, job);
      if (["queued", "running"].includes(job.status)) pollJob(job.id);
    }
    renderOverview();
    renderJobs();
  }

  async function loadProjects() {
    const data = await api("/api/projects");
    state.projects = data.projects || [];
    let preferred = localStorage.getItem("overload-project-id");
    let active = state.projects.find((project) => project.id === preferred) || state.projects[0];
    if (!active) {
      const created = await post("/api/projects", { name: "Mon premier projet" });
      await loadProjectsWithoutCreate();
      active = state.projects.find((project) => project.id === created.project.id) || state.projects[0];
    }
    state.projectId = active?.id || null;
    state.projectName = active?.name || "";
    localStorage.setItem("overload-project-id", state.projectId || "");
    renderProjects();
    await loadAssets();
  }

  async function loadProjectsWithoutCreate() {
    const data = await api("/api/projects");
    state.projects = data.projects || [];
    renderProjects();
  }

  function uploadFile(file) {
    return new Promise((resolve, reject) => {
      const item = document.createElement("div");
      item.className = "upload-item";
      item.innerHTML = `<span class="upload-file-icon">▧</span><span class="upload-item-main"><strong></strong><small>Préparation du transfert…</small></span><span class="upload-progress-wrap"><span class="upload-progress-bar"></span></span><span class="upload-state">En attente</span>`;
      $(".upload-item-main strong", item).textContent = file.name;
      $(".upload-item-main small", item).textContent = `${formatBytes(file.size)} · contrôle à venir`;
      const queue = $("#upload-queue");
      queue.append(item);
      const stateLabel = $(".upload-state", item);
      const progress = $(".upload-progress-bar", item);
      const detail = $(".upload-item-main small", item);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/projects/${encodeURIComponent(state.projectId)}/files`);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
      xhr.setRequestHeader("X-Expected-Size", String(file.size));
      xhr.setRequestHeader("X-Target-Editor", state.editor);
      xhr.upload.onprogress = (event) => {
        const percent = event.lengthComputable ? Math.round((event.loaded / event.total) * 100) : 0;
        progress.style.width = `${percent}%`;
        stateLabel.textContent = `${percent}%`;
        if (percent >= 100) {
          stateLabel.textContent = "Vérification…";
          detail.textContent = "Transfert reçu · analyse des flux en cours";
        }
      };
      xhr.onload = async () => {
        let response;
        try { response = JSON.parse(xhr.responseText || "{}"); } catch { response = {}; }
        if (xhr.status >= 200 && xhr.status < 300 && response.asset) {
          progress.style.width = "100%";
          const report = response.asset.analysis || {};
          const info = integrityInfo(report);
          stateLabel.textContent = info.label;
          if (info.className === "ready") stateLabel.classList.add("success");
          if (info.className === "invalid") stateLabel.classList.add("error");
          detail.textContent = response.message || info.caption;
          try { await loadAssets(); } catch (error) { console.error(error); }
          if (report.integrity === "verified" && compatibilityFor(report).status === "compatible") notify(`${file.name} est vérifié et prêt pour le montage.`, "success");
          else notify(`${file.name} a été conservé. Consulte le diagnostic avant l'import.`, "");
          resolve(response.asset);
        } else {
          stateLabel.textContent = "Échec";
          stateLabel.classList.add("error");
          detail.textContent = response.error || `Erreur HTTP ${xhr.status}`;
          reject(new Error(response.error || `Erreur HTTP ${xhr.status}`));
        }
      };
      xhr.onerror = () => {
        stateLabel.textContent = "Réseau indisponible";
        stateLabel.classList.add("error");
        detail.textContent = "Le serveur n'a pas confirmé la réception. Le fichier source reste sur ton appareil.";
        reject(new Error("Connexion au serveur interrompue."));
      };
      xhr.onabort = () => {
        stateLabel.textContent = "Transfert annulé";
        stateLabel.classList.add("error");
        detail.textContent = "La source locale n'a pas été modifiée.";
        reject(new Error("Transfert annulé."));
      };
      stateLabel.textContent = "Transfert…";
      xhr.send(file);
    });
  }

  async function handleFiles(files) {
    const selected = [...files];
    if (!selected.length) return;
    if (!state.projectId) {
      notify("Crée d'abord un projet pour organiser ces fichiers.", "error");
      return;
    }
    changeView("media");
    let failures = 0;
    for (const file of selected) {
      try { await uploadFile(file); }
      catch (error) { failures += 1; notify(`${file.name} : ${error.message}`, "error"); }
    }
    if (!failures) await loadAssets().catch(() => {});
    $("#file-input").value = "";
  }

  function requestPicker() {
    $("#file-input").click();
  }

  async function openFolder() {
    if (!state.projectId) return;
    try {
      const result = await post(`/api/projects/${encodeURIComponent(state.projectId)}/open-folder`);
      notify(result.message || "Ouverture demandée.", result.opened ? "success" : "");
    } catch (error) { notify(error.message, "error"); }
  }

  async function openAsset(relativePath, editor = null, asset = null) {
    const found = asset || state.assets.find((item) => item.relative_path === relativePath);
    const report = found?.analysis || {};
    const compatibility = compatibilityFor(report);
    if (editor && compatibility.status !== "compatible") {
      const answer = window.confirm(`${compatibility.title || "Compatibilité à vérifier"}\n\n${compatibility.message || "Le codec peut poser problème dans ce logiciel."}\n\n${compatibility.suggestion || "Tu peux convertir une copie en MP4 H.264/AAC."}\n\nOuvrir quand même le fichier ?`);
      if (!answer) return;
    }
    try {
      const route = editor ? "open-editor" : "open-file";
      const result = await post(`/api/projects/${encodeURIComponent(state.projectId)}/${route}`, {
        relative_path: relativePath,
        editor: editor || undefined,
        confirmed: true,
      });
      notify(result.message || "Ouverture demandée.", result.opened ? "success" : "");
    } catch (error) { notify(error.message, "error"); }
  }

  async function startConversion(relativePath) {
    try {
      const result = await post(`/api/projects/${encodeURIComponent(state.projectId)}/convert`, {
        relative_path: relativePath,
        target_editor: state.editor,
      });
      state.jobs.set(result.job.id, result.job);
      renderJobs();
      renderOverview();
      changeView("conversions");
      notify("Conversion démarrée. La source reste intacte.", "success");
      pollJob(result.job.id);
    } catch (error) { notify(error.message, "error"); }
  }

  function pollJob(jobId) {
    if (state.pollingJobs.has(jobId)) return;
    state.pollingJobs.add(jobId);
    const poll = async () => {
      try {
        const result = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
        state.jobs.set(jobId, result.job);
        renderJobs();
        renderOverview();
        if (["completed", "failed", "cancelled"].includes(result.job.status)) {
          state.pollingJobs.delete(jobId);
          if (result.job.status === "completed") {
            await loadAssets().catch(() => {});
            notify("Copie de compatibilité terminée. L'original a été conservé.", "success");
          } else if (result.job.status === "failed") {
            notify(`Conversion échouée : ${result.job.error || "voir les détails"}`, "error", 6500);
          } else {
            notify("Conversion annulée. L'original est intact.");
          }
          return;
        }
        window.setTimeout(poll, 900);
      } catch (error) {
        console.error(error);
        window.setTimeout(poll, 2000);
      }
    };
    poll();
  }

  async function cancelJob(jobId) {
    try {
      const result = await post(`/api/jobs/${encodeURIComponent(jobId)}/cancel`);
      state.jobs.set(jobId, result.job);
      renderJobs();
      notify("Annulation demandée…");
    } catch (error) { notify(error.message, "error"); }
  }

  async function reanalyzeAssets() {
    if (!state.assets.length) return;
    const button = $("#refresh-library");
    button.classList.add("is-spinning");
    button.disabled = true;
    let errors = 0;
    try {
      for (const asset of [...state.assets]) {
        try {
          const result = await post(`/api/projects/${encodeURIComponent(state.projectId)}/analyze`, {
            relative_path: asset.relative_path,
            target_editor: state.editor,
          });
          state.assets = state.assets.map((item) => item.relative_path === asset.relative_path ? result.asset : item);
          renderOverview();
        } catch (error) {
          errors += 1;
          console.error(error);
        }
      }
      notify(errors ? `Analyse terminée avec ${errors} erreur(s).` : "Diagnostics actualisés.", errors ? "error" : "success");
    } finally {
      button.classList.remove("is-spinning");
      button.disabled = false;
      await loadAssets().catch(() => {});
    }
  }

  function showProjectDialog() {
    const dialog = $("#project-dialog");
    $("#project-name-input").value = "";
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    window.setTimeout(() => $("#project-name-input").focus(), 20);
  }

  async function createProject(event) {
    event.preventDefault();
    const name = $("#project-name-input").value.trim();
    if (!name) return;
    try {
      const result = await post("/api/projects", { name });
      await loadProjectsWithoutCreate();
      state.projectId = result.project.id;
      state.projectName = result.project.name;
      localStorage.setItem("overload-project-id", state.projectId);
      renderProjects();
      state.assets = [];
      renderOverview();
      $("#project-dialog").close?.();
      notify(`Projet « ${result.project.name} » créé.`, "success");
    } catch (error) { notify(error.message, "error"); }
  }

  async function openLatestInEditor(editor) {
    const candidate = state.assets.find((asset) => ["verified", "readable"].includes(asset.analysis?.integrity) && asset.media_type === "video");
    if (!candidate) {
      notify("Aucune vidéo lisible dans le projet. Ajoute ou analyse un média d'abord.");
      return;
    }
    await openAsset(candidate.relative_path, editor, candidate);
  }

  async function init() {
    document.addEventListener("click", async (event) => {
      const nav = event.target.closest(".nav-item[data-view]");
      if (nav) { changeView(nav.dataset.view); return; }
      const goView = event.target.closest("[data-go-view]");
      if (goView) { changeView(goView.dataset.goView); return; }
      if (event.target.closest("[data-open-picker]")) { event.preventDefault(); requestPicker(); return; }
      if (event.target.closest("#import-main-button")) { changeView("media"); requestPicker(); return; }
      if (event.target.closest("#new-project-button")) { showProjectDialog(); return; }
      if (event.target.closest("[data-close-dialog]")) { $("#project-dialog").close?.(); return; }
      if (event.target.closest("#open-folder-button, #open-folder-main, [data-open-folder], #open-folder-integration")) { await openFolder(); return; }
      if (event.target.closest(".notice-close")) { $("#downloader-notice").remove(); return; }
      if (event.target.closest("#refresh-library")) { await reanalyzeAssets(); return; }
      const filter = event.target.closest(".filter-tab[data-filter]");
      if (filter) {
        state.filter = filter.dataset.filter;
        $$(".filter-tab").forEach((button) => button.classList.toggle("is-active", button === filter));
        renderAssets();
        return;
      }
      const tableAction = event.target.closest("[data-action]");
      if (tableAction) {
        if (tableAction.disabled) return;
        const relativePath = tableAction.dataset.path;
        if (tableAction.dataset.action === "open-file") await openAsset(relativePath);
        if (tableAction.dataset.action === "open-editor") await openAsset(relativePath, state.editor);
        if (tableAction.dataset.action === "convert") await startConversion(relativePath);
        return;
      }
      const recent = event.target.closest("[data-open-recent]");
      if (recent) { changeView("media"); return; }
      const cancel = event.target.closest("[data-cancel-job]");
      if (cancel) { await cancelJob(cancel.dataset.cancelJob); return; }
      const output = event.target.closest("[data-open-output]");
      if (output && output.dataset.openOutput) { await openAsset(output.dataset.openOutput); return; }
      const latest = event.target.closest("[data-open-latest-editor]");
      if (latest) { await openLatestInEditor(latest.dataset.openLatestEditor); return; }
    });

    $("#file-input").addEventListener("change", (event) => handleFiles(event.target.files));
    const dropzone = $("#upload-zone");
    dropzone.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      requestPicker();
    });
    for (const name of ["dragenter", "dragover"]) dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add("is-dragover"); });
    for (const name of ["dragleave", "drop"]) dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove("is-dragover"); });
    dropzone.addEventListener("drop", (event) => handleFiles(event.dataTransfer?.files || []));

    $("#target-editor").addEventListener("change", (event) => {
      state.editor = event.target.value;
      renderOverview();
      renderHealth();
    });
    $("#project-select").addEventListener("change", async (event) => {
      const selected = state.projects.find((project) => project.id === event.target.value);
      if (!selected) return;
      state.projectId = selected.id;
      state.projectName = selected.name;
      localStorage.setItem("overload-project-id", state.projectId);
      state.assets = [];
      renderOverview();
      try { await loadAssets(); } catch (error) { notify(error.message, "error"); }
    });
    $("#new-project-form").addEventListener("submit", createProject);

    try {
      state.health = await api("/api/health");
      renderHealth();
      await loadProjects();
    } catch (error) {
      console.error(error);
      notify(`Impossible de joindre le service local : ${error.message}`, "error", 7000);
    }
    const hash = location.hash.slice(1);
    if (["overview", "media", "conversions", "integrations"].includes(hash)) changeView(hash);
  }

  init();
})();
