document.addEventListener("DOMContentLoaded", () => {
  // Session ID initialization
  let sessionId = localStorage.getItem("dg_session_id");
  if (!sessionId) {
    sessionId = "session_" + Math.random().toString(36).substring(2, 10);
    localStorage.setItem("dg_session_id", sessionId);
  }

  const sessionStatusEl = document.getElementById("sessionStatus");
  if (sessionStatusEl) {
    sessionStatusEl.textContent = `Session: ${sessionId.substring(0, 12)}...`;
  }

  const coldStartBanner = document.getElementById("coldStartBanner");

  // Health Ping & Cold-Start Detection
  checkColdStartHealth();
  fetchConfig();

  async function checkColdStartHealth() {
    let isResponsive = false;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1500);

    try {
      const res = await fetch("/health", { signal: controller.signal });
      clearTimeout(timeoutId);
      if (res.ok) isResponsive = true;
    } catch (e) {
      clearTimeout(timeoutId);
      isResponsive = false;
    }

    if (!isResponsive && coldStartBanner) {
      coldStartBanner.style.display = "flex";

      const pollInterval = setInterval(async () => {
        try {
          const pollRes = await fetch("/health");
          if (pollRes.ok) {
            clearInterval(pollInterval);
            coldStartBanner.style.display = "none";
          }
        } catch (err) {
          // Keep polling until server wakes up
        }
      }, 2000);
    }
  }

  // File Upload State
  let selectedFiles = [];
  let statusPollTimer = null;

  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const fileList = document.getElementById("fileList");
  const uploadBtn = document.getElementById("uploadBtn");
  const uploadNotice = document.getElementById("uploadNotice");
  const uploadPipelineLoader = document.getElementById("uploadPipelineLoader");
  const uploadPipelineSub = document.getElementById("uploadPipelineSub");
  const uploadPipelineBar = document.getElementById("uploadPipelineBar");
  const uploadPipelineLog = document.getElementById("uploadPipelineLog");

  const confirmCard = document.getElementById("transcriptionConfirmCard");
  const transcriptionList = document.getElementById("transcriptionList");
  const confirmTextBtn = document.getElementById("confirmTextBtn");

  // Drag & Drop Handlers
  dropZone.addEventListener("click", () => fileInput.click());
  
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
    }
  });

  function handleFiles(files) {
    const allowedExts = [".pdf", ".pptx", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp"];
    let warnings = [];

    files.forEach((file) => {
      const ext = "." + file.name.split(".").pop().toLowerCase();
      if (!allowedExts.includes(ext)) {
        warnings.push(`'${file.name}' is an unsupported format.`);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        warnings.push(`'${file.name}' exceeds the 10MB size limit.`);
        return;
      }
      if (selectedFiles.length >= 10) {
        warnings.push(`Maximum of 10 files limit reached.`);
        return;
      }
      if (!selectedFiles.some((f) => f.name === file.name && f.size === file.size)) {
        selectedFiles.push(file);
      }
    });

    if (warnings.length > 0) {
      showNotice(warnings.join(" "), "danger");
    } else {
      hideNotice();
    }

    renderFileList();
  }

  function renderFileList() {
    fileList.innerHTML = "";
    selectedFiles.forEach((file, index) => {
      const chip = document.createElement("div");
      chip.className = "file-chip";
      chip.innerHTML = `
        <span>📄 ${escapeHtml(file.name)}</span>
        <span class="remove-btn" data-index="${index}">&times;</span>
      `;
      fileList.appendChild(chip);
    });

    fileList.querySelectorAll(".remove-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.target.getAttribute("data-index"));
        selectedFiles.splice(idx, 1);
        renderFileList();
      });
    });

    uploadBtn.disabled = selectedFiles.length === 0;
  }

  let isUploadPolling = false;
  let lastLoggedMsg = "";

  function updateUploadStage(stageNum, subText, percent, logMsg) {
    if (uploadPipelineLoader) uploadPipelineLoader.style.display = "block";
    if (uploadPipelineSub) uploadPipelineSub.textContent = subText;
    if (uploadPipelineBar) uploadPipelineBar.style.width = `${percent}%`;

    for (let i = 1; i <= 4; i++) {
      const node = document.getElementById(`uploadStage${i}`);
      if (!node) continue;
      node.classList.remove("completed", "active", "upcoming", "error-state");
      if (i < stageNum) node.classList.add("completed");
      else if (i === stageNum) node.classList.add("active");
      else node.classList.add("upcoming");
    }

    if (logMsg && uploadPipelineLog && logMsg !== lastLoggedMsg) {
      lastLoggedMsg = logMsg;
      const entry = document.createElement("div");
      entry.className = "upload-log-entry";
      entry.textContent = `▸ ${logMsg}`;
      uploadPipelineLog.appendChild(entry);
      uploadPipelineLog.scrollTop = uploadPipelineLog.scrollHeight;
    }
  }

  function startStatusPolling() {
    isUploadPolling = true;
    lastLoggedMsg = "";
    if (uploadPipelineLoader) uploadPipelineLoader.style.display = "block";
    if (uploadPipelineLog) uploadPipelineLog.innerHTML = "";
    updateUploadStage(1, "Validating & preparing files...", 10, "Starting upload pipeline...");

    statusPollTimer = setInterval(async () => {
      if (!isUploadPolling) return;
      try {
        const res = await fetch(`/status/${sessionId}`);
        if (!isUploadPolling) return;
        if (res.ok) {
          const rawText = await res.text();
          if (!isUploadPolling || !rawText) return;
          let data;
          try {
            data = JSON.parse(rawText);
          } catch (e) {
            return;
          }
          if (!isUploadPolling || !data) return;
          if (data.status === "complete") {
            stopStatusPolling(true);
            setLoading(uploadBtn, false, "Upload & Process Notes");
            const fileCount = data.files_processed || selectedFiles.length || 1;
            const countStr = fileCount === 1 ? "1 file" : `${fileCount} files`;
            showNotice(
              `Successfully ingested ${countStr} (${data.chunks_created || 0} new chunks). Total stored: ${data.total_chunks || 0} chunks.`,
              "success"
            );
            selectedFiles = [];
            renderFileList();
          } else if (data.status === "needs_confirmation") {
            stopStatusPolling(true);
            setLoading(uploadBtn, false, "Upload & Process Notes");
            const fileCount = data.files_processed || selectedFiles.length || 1;
            const countStr = fileCount === 1 ? "1 file" : `${fileCount} files`;
            showNotice(
              `Successfully processed ${countStr}. AI transcribed ${data.transcriptions ? data.transcriptions.length : 0} items needing your review below.`,
              "success"
            );
            if (data.transcriptions) renderTranscriptionReview(data.transcriptions);
            selectedFiles = [];
            renderFileList();
          } else if (data.status === "error") {
            stopStatusPolling(false);
            setLoading(uploadBtn, false, "Upload & Process Notes");
            showNotice(`Upload Error: ${data.message || "Failed to ingest files"}`, "danger");
          } else if (data.message && data.message !== lastLoggedMsg) {
            const msg = data.message;
            if (msg.includes("Preparing") || msg.includes("Validating")) {
              updateUploadStage(1, msg, 15, msg);
            } else if (msg.includes("Reading") || msg.includes("Transcribing") || msg.includes("page") || msg.includes("slide")) {
              updateUploadStage(2, msg, 45, msg);
            } else if (msg.includes("Chunk") || msg.includes("Splitting")) {
              updateUploadStage(3, msg, 70, msg);
            } else if (msg.includes("Index") || msg.includes("review") || msg.includes("Confirm")) {
              updateUploadStage(4, msg, 90, msg);
            } else {
              if (uploadPipelineSub) uploadPipelineSub.textContent = msg;
              if (uploadPipelineLog) {
                const entry = document.createElement("div");
                entry.className = "upload-log-entry";
                entry.textContent = `▸ ${msg}`;
                uploadPipelineLog.appendChild(entry);
                uploadPipelineLog.scrollTop = uploadPipelineLog.scrollHeight;
              }
            }
          }
        }
      } catch (e) {
        // ignore transient network/polling errors
      }
    }, 2500);
  }

  function stopStatusPolling(success = true) {
    isUploadPolling = false;
    if (statusPollTimer) {
      clearInterval(statusPollTimer);
      statusPollTimer = null;
    }
    if (success) {
      // Complete all stages cleanly
      if (uploadPipelineBar) uploadPipelineBar.style.width = "100%";
      for (let i = 1; i <= 4; i++) {
        const node = document.getElementById(`uploadStage${i}`);
        if (node) {
          node.classList.remove("active", "upcoming", "error-state");
          node.classList.add("completed");
        }
      }
      if (uploadPipelineSub) uploadPipelineSub.textContent = "Ingestion complete!";
      if (uploadPipelineLog && lastLoggedMsg !== "Ingestion complete.") {
        lastLoggedMsg = "Ingestion complete.";
        const entry = document.createElement("div");
        entry.className = "upload-log-entry";
        entry.textContent = `▸ Ingestion complete.`;
        uploadPipelineLog.appendChild(entry);
        uploadPipelineLog.scrollTop = uploadPipelineLog.scrollHeight;
      }
    } else {
      // Error state
      for (let i = 1; i <= 4; i++) {
        const node = document.getElementById(`uploadStage${i}`);
        if (node && node.classList.contains("active")) {
          node.classList.remove("active");
          node.classList.add("error-state");
        }
      }
    }
  }

  uploadBtn.addEventListener("click", async () => {
    if (selectedFiles.length === 0) return;

    setLoading(uploadBtn, true, "Processing & Reading...");
    hideNotice();
    if (confirmCard) confirmCard.style.display = "none";

    startStatusPolling();

    const formData = new FormData();
    formData.append("session_id", sessionId);
    selectedFiles.forEach((file) => formData.append("files", file));

    try {
      const res = await fetch("/upload", {
        method: "POST",
        body: formData,
      });

      const responseText = await res.text();
      let data = {};
      try {
        if (responseText) data = JSON.parse(responseText);
      } catch (e) {
        data = { detail: responseText || `Upload failed with HTTP status ${res.status}` };
      }

      if (!res.ok) {
        throw new Error(data.detail || data.message || `Upload failed with HTTP status ${res.status}`);
      }
      // Background worker started on server.
      // statusPollTimer handles live stage updates and completion!
    } catch (err) {
      stopStatusPolling(false);
      setLoading(uploadBtn, false, "Upload & Process Notes");
      showNotice(`Upload Error: ${err.message}`, "danger");
    }
  });

  function renderTranscriptionReview(transcriptions) {
    if (!confirmCard || !transcriptionList) return;
    transcriptionList.innerHTML = "";

    transcriptions.forEach((item) => {
      const box = document.createElement("div");
      box.className = "transcription-box";
      box.innerHTML = `
        <div class="transcription-title">📄 Source: ${escapeHtml(item.source)} (Page/Type: ${escapeHtml(item.page)})</div>
        <textarea class="transcription-textarea" data-source="${escapeHtml(item.source)}" data-page="${escapeHtml(item.page)}">${escapeHtml(item.text)}</textarea>
      `;
      transcriptionList.appendChild(box);
    });

    confirmCard.style.display = "block";
  }

  if (confirmTextBtn) {
    confirmTextBtn.addEventListener("click", async () => {
      const textareas = transcriptionList.querySelectorAll(".transcription-textarea");
      const items = [];

      textareas.forEach((ta) => {
        items.push({
          text: ta.value.trim(),
          source: ta.getAttribute("data-source"),
          page: ta.getAttribute("data-page")
        });
      });

      setLoading(confirmTextBtn, true, "Indexing...");

      try {
        const res = await fetch("/confirm_text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, items: items })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Confirmation failed");

        showNotice(`Confirmed & indexed ${data.chunks_created} chunks into RAG store! Total stored: ${data.total_chunks} chunks.`, "success");
        confirmCard.style.display = "none";
      } catch (err) {
        alert(`Error confirming text: ${err.message}`);
      } finally {
        setLoading(confirmTextBtn, false, "Confirm & Index Notes");
      }
    });
  }

  // Tab Navigation
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");

      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanels.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      document.getElementById(targetTab).classList.add("active");
    });
  });

  // RAG Stage Helper Function
  function updateRagStage(prefix, stageNum, subText, percent) {
    const loader = document.getElementById(`${prefix}RagLoader`);
    const subEl = document.getElementById(`${prefix}RagSub`);
    const barEl = document.getElementById(`${prefix}RagBar`);

    if (loader) loader.style.display = "block";
    if (subEl) subEl.textContent = subText;
    if (barEl) barEl.style.width = `${percent}%`;

    for (let i = 1; i <= 4; i++) {
      const node = document.getElementById(`${prefix}Stage${i}`);
      if (!node) continue;
      node.classList.remove("completed", "active", "upcoming", "error-state");
      if (i < stageNum) {
        node.classList.add("completed");
      } else if (i === stageNum) {
        node.classList.add("active");
      } else {
        node.classList.add("upcoming");
      }
    }
  }

  function completeRagStage(prefix) {
    const loader = document.getElementById(`${prefix}RagLoader`);
    const barEl = document.getElementById(`${prefix}RagBar`);
    if (barEl) barEl.style.width = "100%";
    for (let i = 1; i <= 4; i++) {
      const node = document.getElementById(`${prefix}Stage${i}`);
      if (node) {
        node.classList.remove("active", "upcoming", "error-state");
        node.classList.add("completed");
      }
    }
    setTimeout(() => {
      if (loader) loader.style.display = "none";
    }, 800);
  }

  function errorRagStage(prefix, errorMsg) {
    const subEl = document.getElementById(`${prefix}RagSub`);
    if (subEl) subEl.textContent = `Error: ${errorMsg}`;
    for (let i = 1; i <= 4; i++) {
      const node = document.getElementById(`${prefix}Stage${i}`);
      if (node && node.classList.contains("active")) {
        node.classList.remove("active");
        node.classList.add("error-state");
      }
    }
  }

  // Helper for SSE Streaming with Detailed RAG Pipeline Loader
  async function streamFetch(url, bodyData, contentEl, resultCardEl, sourcesEl, btn, btnLabel, loaderPrefix) {
    setLoading(btn, true, "Processing & Streaming...");
    resultCardEl.style.display = "none";
    contentEl.innerHTML = "";
    sourcesEl.innerHTML = "";
    let rawMarkdown = "";

    updateRagStage(loaderPrefix, 1, "Understanding query & extracting concepts...", 25);

    try {
      updateRagStage(loaderPrefix, 2, "Retrieving relevant chunks from notes...", 50);

      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyData),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed with status ${response.status}`);
      }

      updateRagStage(loaderPrefix, 3, "Generating detailed response via LLM...", 75);
      resultCardEl.style.display = "block";

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const dataStr = trimmed.substring(6);

          if (dataStr === "[DONE]") break;

          try {
            const eventData = JSON.parse(dataStr);
            if (eventData.type === "chunk" && eventData.text) {
              rawMarkdown += eventData.text;
              contentEl.innerHTML = renderMarkdown(rawMarkdown);
            } else if (eventData.type === "sources" && eventData.sources) {
              updateRagStage(loaderPrefix, 4, "Finalising answer & formatting citations...", 95);
              renderSources(sourcesEl, eventData.sources);
            }
          } catch (e) {
            console.warn("Error parsing stream chunk:", e);
          }
        }
      }
      completeRagStage(loaderPrefix);
    } catch (err) {
      errorRagStage(loaderPrefix, err.message);
      alert(`Streaming Error: ${err.message}`);
    } finally {
      setLoading(btn, false, btnLabel);
    }
  }

  // Reset Session / Clear Notes
  const clearNotesBtn = document.getElementById("clearNotesBtn");
  if (clearNotesBtn) {
    clearNotesBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to clear all indexed notes for this session?")) return;
      try {
        const res = await fetch(`/clear/${sessionId}`, { method: "POST" });
        if (res.ok) {
          selectedFiles = [];
          renderFileList();
          if (uploadPipelineLog) uploadPipelineLog.innerHTML = "";
          if (uploadPipelineSub) uploadPipelineSub.textContent = "Session reset!";
          if (uploadPipelineBar) uploadPipelineBar.style.width = "0%";
          for (let i = 1; i <= 4; i++) {
            const node = document.getElementById(`uploadStage${i}`);
            if (node) node.classList.remove("completed", "active", "error-state");
          }
          if (askResult) askResult.style.display = "none";
          if (askContent) askContent.innerHTML = "";
          if (askSources) askSources.innerHTML = "";
          if (triageResult) triageResult.style.display = "none";
          if (triageContent) triageContent.innerHTML = "";
          if (triageSources) triageSources.innerHTML = "";
          showNotice("Session reset! All indexed notes cleared.", "success");
        }
      } catch (e) {
        alert("Failed to reset session: " + e.message);
      }
    });
  }

  // Clear session vector store in Qdrant when tab closes/unloads
  window.addEventListener("beforeunload", () => {
    if (sessionId) {
      navigator.sendBeacon(`/clear/${sessionId}`);
    }
  });

  // Tab 1: Ask
  const askBtn = document.getElementById("askBtn");
  const askInput = document.getElementById("askInput");
  const askResult = document.getElementById("askResult");
  const askContent = document.getElementById("askContent");
  const askSources = document.getElementById("askSources");

  askBtn.addEventListener("click", () => {
    const query = askInput.value.trim();
    if (!query) return;

    streamFetch("/ask/stream", { session_id: sessionId, query: query }, askContent, askResult, askSources, askBtn, "Get Answer ↗", "ask");
  });

  // Tab 2: Panic Plan (Triage)
  const triageBtn = document.getElementById("triageBtn");
  const triageHours = document.getElementById("triageHours");
  const triageResult = document.getElementById("triageResult");
  const triageContent = document.getElementById("triageContent");
  const triageSources = document.getElementById("triageSources");

  triageBtn.addEventListener("click", () => {
    const hours = parseFloat(triageHours.value) || 6.0;

    streamFetch("/triage/stream", { session_id: sessionId, hours_left: hours }, triageContent, triageResult, triageSources, triageBtn, "Build Panic Timetable ↗", "triage");
  });

  // Helper Functions
  async function fetchConfig() {
    try {
      const res = await fetch("/config");
      if (res.ok) {
        const data = await res.json();
        const footerEl = document.getElementById("footerModelInfo");
        if (footerEl && data.model) {
          footerEl.textContent = `Powered by ${data.model} (open weights)`;
        }
      }
    } catch (e) {
      console.warn("Could not fetch /config", e);
    }
  }

  function setLoading(btn, isLoading, originalText) {
    if (isLoading) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span> <span>${originalText}</span>`;
    } else {
      btn.disabled = false;
      btn.innerHTML = `<span>${originalText}</span>`;
    }
  }

  function showNotice(msg, type) {
    uploadNotice.style.display = "block";
    uploadNotice.textContent = msg;
    uploadNotice.style.color = type === "danger" ? "var(--danger)" : "var(--success)";
  }

  function hideNotice() {
    uploadNotice.style.display = "none";
  }

  function renderMarkdown(text) {
    if (!text) return "";

    let processed = text;

    // Convert any stray LaTeX algorithm blocks (\begin{algorithm}...\end{algorithm}) into clean pseudocode blocks
    processed = processed.replace(/\\begin\{algorithm\}[\s\S]*?\\end\{algorithm\}/g, (match) => {
      let clean = match
        .replace(/\\begin\{(algorithm|algorithmic)\}(\[[^\]]*\])?/g, "")
        .replace(/\\end\{(algorithm|algorithmic)\}/g, "")
        .replace(/\\caption\{([^}]*)\}/g, "// Caption: $1\n")
        .replace(/\\State\s*/g, "")
        .replace(/\\texttt\{([^}]*)\}/g, "$1")
        .replace(/\\textbf\{([^}]*)\}/g, "$1")
        .replace(/\\hspace\*?\{[^}]*\}/g, "  ")
        .replace(/\\end\{document\}/g, "")
        .trim();
      return `\n\`\`\`pseudocode\n${clean}\n\`\`\`\n`;
    });

    // 1. Protect Markdown code blocks from LaTeX regex replacement
    const codeBlocks = [];
    processed = processed.replace(/```[\s\S]*?```/g, (match) => {
      const idx = codeBlocks.length;
      codeBlocks.push(match);
      return `%%CODE_BLOCK_${idx}%%`;
    });

    // 2. Protect display math $$...$$
    const displayMathBlocks = [];
    processed = processed.replace(/\$\$([\s\S]*?)\$\$/g, (match, content) => {
      const idx = displayMathBlocks.length;
      displayMathBlocks.push(content);
      return `%%DISPLAY_MATH_${idx}%%`;
    });

    // 3. Protect inline math $...$
    const inlineMathBlocks = [];
    processed = processed.replace(/\$([^$\n]+?)\$/g, (match, content) => {
      const idx = inlineMathBlocks.length;
      inlineMathBlocks.push(content);
      return `%%INLINE_MATH_${idx}%%`;
    });

    // 4. Handle \[...\] and \(...\)
    const displayMathBlocks2 = [];
    processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (match, content) => {
      const idx = displayMathBlocks2.length;
      displayMathBlocks2.push(content);
      return `%%DISPLAY_MATH2_${idx}%%`;
    });

    const inlineMathBlocks2 = [];
    processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (match, content) => {
      const idx = inlineMathBlocks2.length;
      inlineMathBlocks2.push(content);
      return `%%INLINE_MATH2_${idx}%%`;
    });

    // Parse markdown
    let html;
    if (typeof marked !== "undefined" && marked.parse) {
      html = marked.parse(processed);
    } else {
      html = escapeHtml(processed);
    }

    // Restore display math $$...$$
    html = html.replace(/%%DISPLAY_MATH_(\d+)%%/g, (match, idx) => {
      const latex = displayMathBlocks[parseInt(idx)];
      try {
        if (typeof katex !== "undefined") {
          return katex.renderToString(latex, { displayMode: true, throwOnError: false });
        }
      } catch (e) { console.warn("KaTeX display error:", e); }
      return `$$${latex}$$`;
    });

    // Restore inline math $...$
    html = html.replace(/%%INLINE_MATH_(\d+)%%/g, (match, idx) => {
      const latex = inlineMathBlocks[parseInt(idx)];
      try {
        if (typeof katex !== "undefined") {
          return katex.renderToString(latex, { displayMode: false, throwOnError: false });
        }
      } catch (e) { console.warn("KaTeX inline error:", e); }
      return `$${latex}$`;
    });

    // Restore display math \[...\]
    html = html.replace(/%%DISPLAY_MATH2_(\d+)%%/g, (match, idx) => {
      const latex = displayMathBlocks2[parseInt(idx)];
      try {
        if (typeof katex !== "undefined") {
          return katex.renderToString(latex, { displayMode: true, throwOnError: false });
        }
      } catch (e) { console.warn("KaTeX display2 error:", e); }
      return `\\[${latex}\\]`;
    });

    // Restore inline math \(...\)
    html = html.replace(/%%INLINE_MATH2_(\d+)%%/g, (match, idx) => {
      const latex = inlineMathBlocks2[parseInt(idx)];
      try {
        if (typeof katex !== "undefined") {
          return katex.renderToString(latex, { displayMode: false, throwOnError: false });
        }
      } catch (e) { console.warn("KaTeX inline2 error:", e); }
      return `\\(${latex}\\)`;
    });

    // 5. Restore Code Blocks
    html = html.replace(/%%CODE_BLOCK_(\d+)%%/g, (match, idx) => {
      const block = codeBlocks[parseInt(idx)];
      if (typeof marked !== "undefined" && marked.parse) {
        return marked.parse(block);
      }
      return `<pre><code>${escapeHtml(block)}</code></pre>`;
    });

    return html;
  }

  function renderSources(container, sources) {
    if (!sources || sources.length === 0) {
      container.innerHTML = "";
      return;
    }

    let html = `
      <div class="sources-header">
        <span>📚 Source Citations (${sources.length})</span>
      </div>
      <div class="sources-list">
    `;

    sources.forEach((s) => {
      html += `
        <div class="source-item">
          <div class="source-tag">📄 ${escapeHtml(s.file)} (p. ${s.page})</div>
          <div class="source-snippet">"${escapeHtml(s.snippet)}"</div>
        </div>
      `;
    });

    html += `</div>`;
    container.innerHTML = html;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
