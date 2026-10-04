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

  // Fetch System Config
  fetchConfig();

  // File Upload State
  let selectedFiles = [];
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const fileList = document.getElementById("fileList");
  const uploadBtn = document.getElementById("uploadBtn");
  const uploadNotice = document.getElementById("uploadNotice");

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
    const allowedExts = [".pdf", ".pptx", ".txt", ".md"];
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

  uploadBtn.addEventListener("click", async () => {
    if (selectedFiles.length === 0) return;

    setLoading(uploadBtn, true, "Uploading & Embedding...");
    hideNotice();

    const formData = new FormData();
    formData.append("session_id", sessionId);
    selectedFiles.forEach((file) => formData.append("files", file));

    try {
      const res = await fetch("/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Upload failed");
      }

      showNotice(
        `Successfully ingested ${data.files_processed} files (${data.chunks_created} new chunks). Total stored: ${data.total_chunks} chunks.`,
        "success"
      );
      selectedFiles = [];
      renderFileList();
    } catch (err) {
      showNotice(`Upload Error: ${err.message}`, "danger");
    } finally {
      setLoading(uploadBtn, false, "Upload & Process Notes");
    }
  });

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

  // Tab 1: Ask
  const askBtn = document.getElementById("askBtn");
  const askInput = document.getElementById("askInput");
  const askResult = document.getElementById("askResult");
  const askContent = document.getElementById("askContent");
  const askSources = document.getElementById("askSources");

  askBtn.addEventListener("click", async () => {
    const query = askInput.value.trim();
    if (!query) return;

    setLoading(askBtn, true, "Searching & Thinking...");
    askResult.style.display = "none";

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, query: query }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");

      askContent.innerHTML = renderMarkdown(data.answer);
      renderSources(askSources, data.sources);
      askResult.style.display = "block";
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setLoading(askBtn, false, "Get Answer");
    }
  });

  // Tab 2: Condense (Cheat Sheet)
  const condenseBtn = document.getElementById("condenseBtn");
  const condenseTopic = document.getElementById("condenseTopic");
  const condenseResult = document.getElementById("condenseResult");
  const condenseContent = document.getElementById("condenseContent");
  const condenseSources = document.getElementById("condenseSources");

  condenseBtn.addEventListener("click", async () => {
    const topic = condenseTopic.value.trim();

    setLoading(condenseBtn, true, "Generating Cheat Sheet...");
    condenseResult.style.display = "none";

    try {
      const res = await fetch("/condense", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, topic: topic }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");

      condenseContent.innerHTML = renderMarkdown(data.answer);
      renderSources(condenseSources, data.sources);
      condenseResult.style.display = "block";
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setLoading(condenseBtn, false, "Generate Cheat Sheet");
    }
  });

  // Tab 3: Interactive Quiz
  const quizBtn = document.getElementById("quizBtn");
  const quizTopic = document.getElementById("quizTopic");
  const quizN = document.getElementById("quizN");
  const quizResult = document.getElementById("quizResult");
  const quizContent = document.getElementById("quizContent");
  const quizSources = document.getElementById("quizSources");

  quizBtn.addEventListener("click", async () => {
    const topic = quizTopic.value.trim();
    const n = parseInt(quizN.value) || 5;

    setLoading(quizBtn, true, "Creating Quiz...");
    quizResult.style.display = "none";

    try {
      const res = await fetch("/quiz", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, topic: topic, n: n }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");

      renderQuizCards(quizContent, data.quiz);
      renderSources(quizSources, data.sources);
      quizResult.style.display = "block";
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setLoading(quizBtn, false, "Generate Quiz Flashcards");
    }
  });

  // Tab 4: Panic Plan (Triage)
  const triageBtn = document.getElementById("triageBtn");
  const triageHours = document.getElementById("triageHours");
  const triageResult = document.getElementById("triageResult");
  const triageContent = document.getElementById("triageContent");
  const triageSources = document.getElementById("triageSources");

  triageBtn.addEventListener("click", async () => {
    const hours = parseFloat(triageHours.value) || 6.0;

    setLoading(triageBtn, true, "Triaging Schedule...");
    triageResult.style.display = "none";

    try {
      const res = await fetch("/triage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, hours_left: hours }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");

      triageContent.innerHTML = renderMarkdown(data.answer);
      renderSources(triageSources, data.sources);
      triageResult.style.display = "block";
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setLoading(triageBtn, false, "Build Panic Timetable");
    }
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
    if (typeof marked !== "undefined" && marked.parse) {
      return marked.parse(text || "");
    }
    return escapeHtml(text || "");
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

  function renderQuizCards(container, quizList) {
    container.innerHTML = "";
    if (!quizList || quizList.length === 0) {
      container.innerHTML = "<p>No quiz questions generated.</p>";
      return;
    }

    quizList.forEach((q, idx) => {
      const card = document.createElement("div");
      card.className = "quiz-card";

      let optionsHtml = "";
      const options = q.options || [];

      options.forEach((optStr) => {
        const optionLetter = optStr.trim().charAt(0).toUpperCase();
        optionsHtml += `
          <button class="quiz-opt-btn" data-letter="${optionLetter}">
            ${escapeHtml(optStr)}
          </button>
        `;
      });

      card.innerHTML = `
        <div class="quiz-question">Q${idx + 1}: ${escapeHtml(q.question || "")}</div>
        <div class="quiz-options">${optionsHtml}</div>
        <div class="quiz-explanation" id="exp_${idx}">
          <strong>Explanation:</strong> ${escapeHtml(q.explanation || "")}
        </div>
      `;

      container.appendChild(card);

      // Attach option button click handlers
      const optBtns = card.querySelectorAll(".quiz-opt-btn");
      const expEl = card.querySelector(".quiz-explanation");
      const correctAnswer = (q.answer || "A").trim().toUpperCase();

      optBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          optBtns.forEach((b) => b.disabled = true);
          const chosenLetter = btn.getAttribute("data-letter");

          if (chosenLetter === correctAnswer || optBtns.length === 1) {
            btn.classList.add("correct");
          } else {
            btn.classList.add("incorrect");
            // Highlight the correct button
            optBtns.forEach((b) => {
              if (b.getAttribute("data-letter") === correctAnswer) {
                b.classList.add("correct");
              }
            });
          }
          expEl.style.display = "block";
        });
      });
    });
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
