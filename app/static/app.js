// SphereAI Controller v12.0 - Dynamic Blue-Tone Dashboard, Smooth Reclean & Embedded Dashboard Report
let trendChartInstance = null;
let costChartInstance = null;
let currentDashboardModel = null;
let rawTableData = [];
let tableColumns = [];
let currentSelectedFile = null;
let isSampleSelected = false;
let currentStage = "idle"; // idle | awaiting_human_gatekeeper | awaiting_human_evaluation | completed

document.addEventListener("DOMContentLoaded", () => {
    console.log("SphereAI v14.0 Initialized");
    if (typeof Chart !== "undefined" && Chart.defaults && Chart.defaults.font) {
        Chart.defaults.font.family = "'Segoe UI', 'Be Vietnam Pro', Tahoma, sans-serif";
    }
    initNavigation();
    initCentralHub();
    initHumanApprovalControls();
    initGatekeeperTabs();
    initDashboardControls();
    checkCurrentStatus();
});

function switchView(viewName) {
    document.querySelectorAll(".content-view").forEach(v => v.classList.remove("active-view"));
    const targetView = document.getElementById(`view-${viewName}`);
    if (targetView) targetView.classList.add("active-view");

    document.querySelectorAll(".nav-item").forEach(item => {
        if (item.getAttribute("data-view") === viewName) {
            item.classList.add("active");
        } else {
            item.classList.remove("active");
        }
    });

    const titleEl = document.getElementById("current-view-title");
    if (titleEl) {
        if (viewName === "home") titleEl.innerText = "Hệ Thống Xử Lý & Phân Tích Dữ Liệu";
        else if (viewName === "dashboard") titleEl.innerText = "Dashboard Phân Tích Chuyên Sâu (Tone Xanh Dương)";
        else if (viewName === "report") titleEl.innerText = "Báo Cáo Word Đính Kèm Dashboard & Phân Tích Sâu Trình Cấp Trên";
        else if (viewName === "excel") titleEl.innerText = "Xem Trước File Excel Đã Làm Sạch";
    }

    const mainArea = document.getElementById("main-content-area");
    if (mainArea) mainArea.scrollTop = 0;
}

function initNavigation() {
    const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
    const sidebar = document.getElementById("left-sidebar");
    const toggleIcon = document.getElementById("sidebar-toggle-icon");

    if (btnToggleSidebar && sidebar) {
        btnToggleSidebar.addEventListener("click", () => {
            sidebar.classList.toggle("collapsed");
            toggleIcon.innerText = sidebar.classList.contains("collapsed") ? "▶" : "◀";
        });
    }

    const btnMobile = document.getElementById("btn-mobile-menu");
    if (btnMobile && sidebar) {
        btnMobile.addEventListener("click", () => {
            sidebar.classList.toggle("mobile-open");
        });
    }

    document.querySelectorAll("[data-view]").forEach(el => {
        el.addEventListener("click", () => {
            const view = el.getAttribute("data-view");
            if (view) {
                switchView(view);
                if (window.innerWidth <= 900 && sidebar) {
                    sidebar.classList.remove("mobile-open");
                }
            }
        });
    });

    const btnCenterSample = document.getElementById("btn-center-sample");
    if (btnCenterSample) {
        btnCenterSample.addEventListener("click", () => {
            switchView("home");
            currentSelectedFile = null;
            isSampleSelected = true;
            showSelectedFileBadge("Dữ liệu Hoạt động Doanh nghiệp mẫu (Đã chọn)");
            updateReadinessState();
        });
    }

    const btnReset = document.getElementById("nav-reset-data");
    if (btnReset) {
        btnReset.addEventListener("click", async () => {
            if (confirm("Bạn có muốn làm mới toàn bộ dữ liệu và bối cảnh về trạng thái ban đầu?")) {
                try {
                    await fetch("/api/reset", { method: "POST" });
                } catch(e) {}
                resetToEmptyState();
                switchView("home");
            }
        });
    }
}

function activateGatekeeperTab(tabName) {
    const btnChanges = document.getElementById("tab-btn-changes");
    const btnPreview = document.getElementById("tab-btn-preview");
    const contentChanges = document.getElementById("tab-content-changes");
    const contentPreview = document.getElementById("tab-content-preview");

    if (!btnChanges || !btnPreview) return;
    if (tabName === "changes") {
        btnChanges.classList.add("active");
        btnPreview.classList.remove("active");
        if (contentChanges) contentChanges.style.display = "block";
        if (contentPreview) contentPreview.style.display = "none";
    } else {
        btnPreview.classList.add("active");
        btnChanges.classList.remove("active");
        if (contentPreview) contentPreview.style.display = "block";
        if (contentChanges) contentChanges.style.display = "none";
    }
}

function initGatekeeperTabs() {
    const btnChanges = document.getElementById("tab-btn-changes");
    const btnPreview = document.getElementById("tab-btn-preview");
    if (btnChanges) btnChanges.addEventListener("click", () => activateGatekeeperTab("changes"));
    if (btnPreview) btnPreview.addEventListener("click", () => activateGatekeeperTab("preview"));
}

function initDashboardControls() {
    const dimSelect = document.getElementById("dk-dimension-select");
    const periodSelect = document.getElementById("dk-period-select");

    const onFilterChange = () => {
        if (!currentDashboardModel) return;
        const dimVal = dimSelect ? dimSelect.value : currentDashboardModel.default_dimension;
        const perVal = periodSelect ? periodSelect.value : currentDashboardModel.default_period;
        renderDashboardSlice(dimVal, perVal);
    };

    if (dimSelect) dimSelect.addEventListener("change", onFilterChange);
    if (periodSelect) periodSelect.addEventListener("change", onFilterChange);

    const btnToggleMonthly = document.getElementById("btn-toggle-monthly-table");
    const monthlyWrap = document.getElementById("dk-monthly-table-wrap");
    const arrowEl = document.getElementById("monthly-toggle-arrow");
    if (btnToggleMonthly && monthlyWrap) {
        btnToggleMonthly.addEventListener("click", () => {
            const isHidden = monthlyWrap.style.display === "none";
            monthlyWrap.style.display = isHidden ? "block" : "none";
            if (arrowEl) arrowEl.innerText = isHidden ? "▼" : "▶";
        });
    }
}

function updateReadinessState() {
    const contextInput = document.getElementById("business-context-input");
    const hasData = (currentSelectedFile !== null || isSampleSelected === true);
    const hasContext = contextInput && contextInput.value.trim().length > 0;

    const dataStatusEl = document.getElementById("ready-data-status");
    const ctxStatusEl = document.getElementById("ready-context-status");
    const btnRun = document.getElementById("btn-run-workflow");
    const btnRunText = document.getElementById("btn-run-text");

    if (dataStatusEl) {
        if (hasData) {
            const srcName = currentSelectedFile ? currentSelectedFile.name : "Dữ liệu Doanh nghiệp mẫu";
            dataStatusEl.className = "ready-item ready-ok";
            dataStatusEl.innerHTML = `<span>✅ 1. Đã chọn: ${srcName}</span>`;
        } else {
            dataStatusEl.className = "ready-item";
            dataStatusEl.innerHTML = `<span>⏳ 1. Chưa đưa dữ liệu lên</span>`;
        }
    }

    if (ctxStatusEl) {
        if (hasContext) {
            ctxStatusEl.className = "ready-item ready-ok";
            ctxStatusEl.innerHTML = `<span>✅ 2. Đã nhập bối cảnh doanh nghiệp</span>`;
        } else {
            ctxStatusEl.className = "ready-item";
            ctxStatusEl.innerHTML = `<span>⏳ 2. Chưa nhập bối cảnh doanh nghiệp</span>`;
        }
    }

    if (btnRun && btnRunText) {
        if (hasData && hasContext) {
            btnRun.classList.remove("btn-locked");
            btnRunText.innerText = "Bắt Đầu Phân Tích Dữ Liệu";
        } else {
            btnRun.classList.add("btn-locked");
            btnRunText.innerText = "Đưa đủ Dữ liệu & Bối cảnh để Bắt đầu phân tích";
        }
    }
}

function initCentralHub() {
    const centerInput = document.getElementById("center-file-input");
    const dropArea = document.getElementById("upload-drop-area");
    const btnRemoveFile = document.getElementById("btn-remove-file");
    const btnRunWorkflow = document.getElementById("btn-run-workflow");
    const contextInput = document.getElementById("business-context-input");

    document.querySelectorAll(".preset-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            document.querySelectorAll(".preset-chip").forEach(c => c.classList.remove("active-preset"));
            chip.classList.add("active-preset");
            const ctxText = chip.getAttribute("data-context");
            if (contextInput && ctxText) {
                contextInput.value = ctxText;
                updateReadinessState();
            }
        });
    });

    if (contextInput) {
        contextInput.addEventListener("input", () => {
            updateReadinessState();
        });
    }

    function onFileStaged(file) {
        if (!file) return;
        switchView("home");
        currentSelectedFile = file;
        isSampleSelected = false;
        showSelectedFileBadge(`${file.name}`);
        updateReadinessState();
    }

    if (centerInput) {
        centerInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files.length > 0) {
                onFileStaged(e.target.files[0]);
                e.target.value = "";
            }
        });
    }

    if (dropArea) {
        dropArea.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropArea.classList.add("drag-active");
        });
        dropArea.addEventListener("dragleave", () => {
            dropArea.classList.remove("drag-active");
        });
        dropArea.addEventListener("drop", (e) => {
            e.preventDefault();
            dropArea.classList.remove("drag-active");
            if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                onFileStaged(e.dataTransfer.files[0]);
            }
        });
    }

    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("drop", (e) => {
        e.preventDefault();
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            onFileStaged(e.dataTransfer.files[0]);
        }
    });

    if (btnRemoveFile) {
        btnRemoveFile.addEventListener("click", () => {
            currentSelectedFile = null;
            isSampleSelected = false;
            document.getElementById("selected-file-badge").style.display = "none";
            document.getElementById("upload-status-title").innerText = "Kéo thả file Excel (.xlsx, .xls) hoặc CSV vào đây";
            updateReadinessState();
        });
    }

    if (btnRunWorkflow) {
        btnRunWorkflow.addEventListener("click", () => {
            const hasData = (currentSelectedFile !== null || isSampleSelected === true);
            const bizContext = contextInput ? contextInput.value.trim() : "";

            if (!hasData && !bizContext) {
                alert("⚠️ Vui lòng chọn File dữ liệu (ở Mục 1) VÀ nhập Bối cảnh doanh nghiệp (ở Mục 2) trước khi bấm Bắt đầu phân tích!");
                return;
            }
            if (!hasData) {
                alert("⚠️ Bạn chưa đưa dữ liệu lên! Vui lòng chọn file Excel/CSV hoặc bấm '⚡ Dùng dữ liệu Doanh nghiệp mẫu' ở Mục 1.");
                return;
            }
            if (!bizContext) {
                alert("⚠️ Bạn chưa nhập Bối cảnh doanh nghiệp! Vui lòng chọn nhanh lĩnh vực hoặc nhập mô tả ở Mục 2.");
                if (contextInput) contextInput.focus();
                return;
            }

            if (currentSelectedFile) {
                uploadAndStartStep1Step2(currentSelectedFile, bizContext);
            } else if (isSampleSelected) {
                loadSampleCRMData(bizContext);
            }
        });
    }

    const searchInput = document.getElementById("table-search-input");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            filterPreviewTable(e.target.value.toLowerCase().trim());
        });
    }
}

function initHumanApprovalControls() {
    const btnGkYes = document.getElementById("btn-human-gk-yes");
    const btnGkNo = document.getElementById("btn-human-gk-no");
    const btnCloseReclean = document.getElementById("btn-close-reclean-drawer");
    const btnConfirmReclean = document.getElementById("btn-confirm-reclean");

    if (btnGkYes) {
        btnGkYes.addEventListener("click", () => {
            if (currentStage === "awaiting_human_gatekeeper") approveGatekeeperAndRunStep4();
        });
    }
    if (btnGkNo) {
        btnGkNo.addEventListener("click", () => {
            if (currentStage !== "awaiting_human_gatekeeper") return;
            const drawer = document.getElementById("hr-reclean-options");
            if (drawer) {
                drawer.style.display = "flex";
                drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
                const customInput = document.getElementById("input-reclean-custom");
                if (customInput) customInput.focus();
            }
        });
    }
    if (btnCloseReclean) {
        btnCloseReclean.addEventListener("click", () => {
            const drawer = document.getElementById("hr-reclean-options");
            if (drawer) drawer.style.display = "none";
        });
    }

    // Quick reclean command chips
    document.querySelectorAll(".reclean-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const cmd = chip.getAttribute("data-cmd") || "";
            const input = document.getElementById("input-reclean-custom");
            if (input) {
                input.value = cmd;
                input.focus();
            }
        });
    });

    const chkFill = document.getElementById("chk-fill-missing");
    const chkDrop = document.getElementById("chk-drop-missing");
    if (chkFill && chkDrop) {
        chkDrop.addEventListener("change", () => { if (chkDrop.checked) chkFill.checked = false; });
        chkFill.addEventListener("change", () => { if (chkFill.checked) chkDrop.checked = false; });
    }

    if (btnConfirmReclean) {
        btnConfirmReclean.addEventListener("click", () => executeRecleanLoop());
    }

    const btnEvalYes = document.getElementById("btn-human-eval-yes");
    const btnEvalNo = document.getElementById("btn-human-eval-no");
    const btnConfirmRefine = document.getElementById("btn-confirm-refine");

    if (btnEvalYes) {
        btnEvalYes.addEventListener("click", () => {
            if (currentStage === "awaiting_human_evaluation") approveEvaluationAndFinishStep5();
        });
    }
    if (btnEvalNo) {
        btnEvalNo.addEventListener("click", () => {
            if (currentStage !== "awaiting_human_evaluation") return;
            const drawer = document.getElementById("hr-refine-options");
            if (drawer) {
                drawer.style.display = "flex";
                const input = document.getElementById("input-refine-feedback");
                if (input) input.focus();
                drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        });
    }
    if (btnConfirmRefine) {
        btnConfirmRefine.addEventListener("click", () => executeRefineAnalysisLoop());
    }
}

function showSelectedFileBadge(filename) {
    const badge = document.getElementById("selected-file-badge");
    const nameEl = document.getElementById("selected-file-name");
    const titleEl = document.getElementById("upload-status-title");
    if (nameEl) nameEl.innerText = filename;
    if (badge) badge.style.display = "inline-flex";
    if (titleEl) titleEl.innerText = "Nguồn dữ liệu đã chọn:";
}

async function checkCurrentStatus() {
    try {
        const res = await fetch("/api/status");
        const json = await res.json();
        if (json.has_data && json.data) {
            isSampleSelected = true;
            showSelectedFileBadge(json.source || "Dữ liệu đã nạp");
            if (json.business_context) {
                const ctxEl = document.getElementById("business-context-input");
                if (ctxEl && !ctxEl.value) ctxEl.value = json.business_context;
            }
            updateReadinessState();
            renderSessionState(json.data, false);
        } else {
            resetToEmptyState();
        }
    } catch (e) {
        resetToEmptyState();
    }
}

function showLoadingBar(title, subtitle) {
    const bar = document.getElementById("ai-loading-bar");
    const titleEl = document.getElementById("loading-title");
    const subEl = document.getElementById("loading-subtitle");
    if (titleEl && title) titleEl.innerText = title;
    if (subEl && subtitle) subEl.innerText = subtitle;
    if (bar) bar.style.display = "flex";
}

function hideLoadingBar() {
    const bar = document.getElementById("ai-loading-bar");
    if (bar) bar.style.display = "none";
}

function showRecleanToast(message) {
    const toast = document.getElementById("reclean-status-toast");
    if (!toast) return;
    toast.innerHTML = `
        <span>✅ ${message}</span>
        <button type="button" onclick="this.parentElement.style.display='none'" style="background:none;border:none;color:#1e3a8a;font-weight:800;cursor:pointer;">✕</button>
    `;
    toast.style.display = "flex";
}

// =========================================================================
// API CALLS
// =========================================================================
async function uploadAndStartStep1Step2(file, bizContext) {
    if (!file || !bizContext) return;
    showLoadingBar(
        `Đang nhập dữ liệu & làm sạch: ${file.name}...`,
        "Đang đối chiếu dữ liệu trước và sau làm sạch..."
    );

    const formData = new FormData();
    formData.append("file", file);
    formData.append("business_context", bizContext);

    try {
        const res = await fetch("/api/upload", { method: "POST", body: formData });
        const json = await res.json();
        hideLoadingBar();

        if (res.ok && json.status === "success") {
            const toast = document.getElementById("reclean-status-toast");
            if (toast) toast.style.display = "none";
            showSelectedFileBadge(`${file.name} ✓`);
            renderSessionState(json.data, true);
        } else {
            alert("Lỗi xử lý file: " + (json.detail || "Không rõ nguyên nhân"));
        }
    } catch (err) {
        hideLoadingBar();
        alert("Lỗi kết nối máy chủ: " + err.message);
    }
}

async function loadSampleCRMData(bizContext) {
    if (!bizContext) return;
    showLoadingBar(
        "Đang nạp dữ liệu Doanh nghiệp mẫu & thực hiện làm sạch...",
        "Đang lọc trùng lặp, xử lý ô trống và lập bảng so sánh với file ban đầu..."
    );

    try {
        const res = await fetch("/api/load-sample", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ business_context: bizContext })
        });
        const json = await res.json();
        hideLoadingBar();

        if (res.ok && json.status === "success") {
            const toast = document.getElementById("reclean-status-toast");
            if (toast) toast.style.display = "none";
            showSelectedFileBadge("Dữ liệu Doanh nghiệp mẫu ✓");
            renderSessionState(json.data, true);
        } else {
            alert("Lỗi nạp mẫu: " + (json.detail || "Không rõ nguyên nhân"));
        }
    } catch (err) {
        hideLoadingBar();
        alert("Lỗi kết nối máy chủ: " + err.message);
    }
}

async function executeRecleanLoop() {
    const dropDup = document.getElementById("chk-drop-dup")?.checked ?? true;
    const fillMissing = document.getElementById("chk-fill-missing")?.checked ?? true;
    const dropMissing = document.getElementById("chk-drop-missing")?.checked ?? false;
    const fixAnomaly = document.getElementById("chk-fix-anomaly")?.checked ?? true;
    const customInst = document.getElementById("input-reclean-custom")?.value.trim() || "";

    showLoadingBar("↩ Đang thực thi làm sạch lại trên File gốc...", "Đang áp dụng tùy chọn và lệnh làm sạch của bạn...");

    try {
        const res = await fetch("/api/gatekeeper/reclean", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                drop_duplicates: dropDup,
                fill_missing: fillMissing,
                drop_missing_rows: dropMissing,
                fix_anomalies: fixAnomaly,
                custom_instruction: customInst
            })
        });
        const json = await res.json();
        hideLoadingBar();

        if (res.ok && json.status === "success") {
            const drawer = document.getElementById("hr-reclean-options");
            if (drawer) drawer.style.display = "none";
            renderSessionState(json.data, false);
            activateGatekeeperTab("changes");

            const cmp = json.data.gatekeeper?.comparison || {};
            const loopNum = json.data.cleaning_loop_count || 1;
            const customNote = customInst ? ` (Đã áp dụng lệnh: "${customInst}")` : "";
            showRecleanToast(
                `Đã làm sạch lại lần #${loopNum} thành công! Hiện có ${cmp.after_rows} dòng sạch (Đã loại bỏ ${cmp.removed_rows} dòng, cập nhật ${cmp.change_logs?.length || 0} thay đổi chi tiết bên dưới)${customNote}.`
            );

            const gkPanel = document.getElementById("human-gatekeeper-panel");
            if (gkPanel) gkPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        } else {
            alert("Lỗi khi làm sạch lại: " + (json.detail || "Không rõ nguyên nhân"));
        }
    } catch (err) {
        hideLoadingBar();
        alert("Lỗi kết nối máy chủ: " + err.message);
    }
}

async function approveGatekeeperAndRunStep4() {
    const contextInput = document.getElementById("business-context-input");
    const bizContext = contextInput ? contextInput.value.trim() : "";

    showLoadingBar(
        "✅ Đã duyệt dữ liệu! Đang dựng Dashboard & Báo cáo Word đính kèm Dashboard...",
        "Đang phân tích đa chiều theo dữ liệu thực tế và bối cảnh doanh nghiệp..."
    );

    try {
        const res = await fetch("/api/gatekeeper/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ business_context: bizContext })
        });
        const json = await res.json();
        hideLoadingBar();

        if (res.ok && json.status === "success") {
            renderSessionState(json.data, true);
        } else {
            alert("Lỗi phân tích: " + (json.detail || "Không rõ nguyên nhân"));
        }
    } catch (err) {
        hideLoadingBar();
        alert("Lỗi kết nối máy chủ: " + err.message);
    }
}

async function executeRefineAnalysisLoop() {
    const feedbackEl = document.getElementById("input-refine-feedback");
    const feedback = feedbackEl ? feedbackEl.value.trim() : "";
    if (!feedback) {
        alert("Vui lòng nhập nội dung bạn muốn AI điều chỉnh và phân tích lại!");
        if (feedbackEl) feedbackEl.focus();
        return;
    }

    const contextInput = document.getElementById("business-context-input");
    const bizContext = contextInput ? contextInput.value.trim() : "";

    showLoadingBar("↩ Đang điều chỉnh & phân tích lại...", `Yêu cầu điều chỉnh: "${feedback}"`);

    try {
        const res = await fetch("/api/evaluation/refine", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ feedback: feedback, business_context: bizContext })
        });
        const json = await res.json();
        hideLoadingBar();

        if (res.ok && json.status === "success") {
            const drawer = document.getElementById("hr-refine-options");
            if (drawer) drawer.style.display = "none";
            if (feedbackEl) feedbackEl.value = "";
            renderSessionState(json.data, true);
        } else {
            alert("Lỗi khi phân tích lại: " + (json.detail || "Không rõ nguyên nhân"));
        }
    } catch (err) {
        hideLoadingBar();
        alert("Lỗi kết nối máy chủ: " + err.message);
    }
}

async function approveEvaluationAndFinishStep5() {
    showLoadingBar("✅ Đã duyệt kết quả! Đang hoàn tất xuất bản...", "Mở khóa Dashboard, Báo cáo Word và File Excel...");

    try {
        const res = await fetch("/api/evaluation/approve", { method: "POST" });
        const json = await res.json();
        hideLoadingBar();

        if (res.ok && json.status === "success") {
            renderSessionState(json.data, true);
        } else {
            alert("Lỗi hoàn tất: " + (json.detail || "Không rõ nguyên nhân"));
        }
    } catch (err) {
        hideLoadingBar();
        alert("Lỗi kết nối máy chủ: " + err.message);
    }
}

// =========================================================================
// RENDER SESSION STATE
// =========================================================================
function renderSessionState(data, autoScroll = false) {
    currentStage = data.stage || "idle";
    const gk = data.gatekeeper;
    const analysis = data.gemini_analysis;
    rawTableData = data.preview || [];
    tableColumns = data.columns || [];

    if (gk) {
        renderExcelView(data);
    }

    if (analysis) {
        renderDashboardView(analysis);
        renderReportView(analysis, gk);
    }

    const gkPanel = document.getElementById("human-gatekeeper-panel");
    const evalPanel = document.getElementById("human-evaluation-panel");
    const homeBanner = document.getElementById("home-data-banner");
    const topPill = document.getElementById("top-stage-pill");

    if (currentStage === "awaiting_human_gatekeeper") {
        if (topPill) topPill.innerText = "Chờ bạn Kiểm duyệt dữ liệu đã làm sạch";
        updateSidebarDataStatus(true, "Chờ bạn Kiểm duyệt", data.source);
        if (gkPanel) {
            populateHumanGatekeeperPanel(data);
            gkPanel.style.display = "block";
            if (autoScroll) gkPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        if (evalPanel) evalPanel.style.display = "none";
        if (homeBanner) homeBanner.style.display = "none";
    } else if (currentStage === "awaiting_human_evaluation") {
        if (topPill) topPill.innerText = "Chờ bạn Đánh giá kết quả phân tích";
        updateSidebarDataStatus(true, "Chờ bạn Đánh giá KQ", data.source);
        if (gkPanel) gkPanel.style.display = "none";
        if (evalPanel) {
            populateHumanEvaluationPanel(data);
            evalPanel.style.display = "block";
            if (autoScroll) evalPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        if (homeBanner) homeBanner.style.display = "none";
    } else if (currentStage === "completed") {
        if (topPill) topPill.innerText = "Đã hoàn tất & Xuất 3 báo cáo";
        updateSidebarDataStatus(true, analysis ? analysis.domain_detected : "Hoàn tất", data.source);
        if (gkPanel) gkPanel.style.display = "none";
        if (evalPanel) evalPanel.style.display = "none";
        if (homeBanner) {
            const bannerTitle = document.getElementById("banner-title");
            if (bannerTitle && analysis) {
                bannerTitle.innerText = `Hoàn tất: ${analysis.domain_detected} (${data.total_rows} dòng sạch)`;
            }
            homeBanner.style.display = "flex";
            if (autoScroll) homeBanner.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }
}

function populateHumanGatekeeperPanel(data) {
    const gk = data.gatekeeper.summary;
    const cmp = data.gatekeeper.comparison || {};
    const loopCount = data.cleaning_loop_count || 0;

    document.getElementById("hr-gk-loop-tag").innerText = loopCount > 0 ? `Đã làm sạch lại (${loopCount} lần)` : "Đã làm sạch tự động";

    const beforeHealth = cmp.before_health_score !== undefined ? cmp.before_health_score : gk.health_score;
    const afterHealth = cmp.after_health_score !== undefined ? cmp.after_health_score : gk.health_score;
    document.getElementById("cmp-health-before").innerText = `${beforeHealth}%`;
    document.getElementById("cmp-health-after").innerText = `${afterHealth}%`;
    const healthDiff = (afterHealth - beforeHealth).toFixed(1);
    document.getElementById("cmp-health-note").innerText = healthDiff > 0 ? `Tăng +${healthDiff}% độ sạch dữ liệu` : "Dữ liệu đạt chuẩn hợp lệ";

    const beforeRows = cmp.before_rows !== undefined ? cmp.before_rows : gk.total_records;
    const afterRows = cmp.after_rows !== undefined ? cmp.after_rows : gk.total_records;
    const removedRows = cmp.removed_rows || 0;
    document.getElementById("cmp-rows-before").innerText = `${beforeRows} dòng`;
    document.getElementById("cmp-rows-after").innerText = `${afterRows} dòng`;
    document.getElementById("cmp-rows-note").innerText = removedRows > 0 ? `Đã loại bỏ ${removedRows} dòng trùng/lọc` : "Giữ nguyên dòng hợp lệ";

    const beforeDup = cmp.before_duplicates !== undefined ? cmp.before_duplicates : 0;
    const afterDup = cmp.after_duplicates !== undefined ? cmp.after_duplicates : gk.duplicate_count;
    document.getElementById("cmp-dup-before").innerText = `${beforeDup} dòng`;
    document.getElementById("cmp-dup-after").innerText = `${afterDup} dòng`;
    document.getElementById("cmp-dup-note").innerText = beforeDup > afterDup ? `Đã xóa ${beforeDup - afterDup} bản ghi trùng lặp` : "Không còn bản ghi trùng lặp";

    const beforeMissing = cmp.before_missing_cells !== undefined ? cmp.before_missing_cells : 0;
    const afterMissing = cmp.after_missing_cells !== undefined ? cmp.after_missing_cells : 0;
    document.getElementById("cmp-missing-before").innerText = `${beforeMissing} ô trống`;
    document.getElementById("cmp-missing-after").innerText = `${afterMissing} ô trống`;
    if (cmp.dropped_missing_rows > 0) {
        document.getElementById("cmp-missing-note").innerText = `Đã xóa ${cmp.dropped_missing_rows} dòng có ô trống`;
    } else if (cmp.filled_missing_cells > 0) {
        document.getElementById("cmp-missing-note").innerText = `Đã chuẩn hóa ${cmp.filled_missing_cells} ô trống`;
    } else {
        document.getElementById("cmp-missing-note").innerText = "Không có ô bị bỏ trống";
    }

    const actionsEl = document.getElementById("hr-gk-actions-list");
    const actions = data.gatekeeper.actions_taken || [];
    if (actionsEl) {
        const bulletItems = actions.map(a => `<li>✓ ${a}</li>`).join("");
        actionsEl.innerHTML = `
            <strong>🧹 Tổng hợp các xử lý đã thực hiện so với File ban đầu:</strong>
            <ul style="margin-top: 4px; padding-left: 18px; list-style: none;">${bulletItems}</ul>
        `;
    }

    const changeLogs = cmp.change_logs || [];
    const countBadge = document.getElementById("changes-count-badge");
    if (countBadge) countBadge.innerText = changeLogs.length;

    const changesTbody = document.getElementById("hr-changes-tbody");
    if (changesTbody) {
        if (changeLogs.length === 0) {
            changesTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 16px; color: #16a34a; font-weight: 700;">File ban đầu đã sạch chuẩn, không phát sinh lỗi trùng lặp hay ô trống.</td></tr>`;
        } else {
            changesTbody.innerHTML = changeLogs.map(log => `
                <tr>
                    <td><strong>${log.row}</strong></td>
                    <td><strong>${log.column}</strong></td>
                    <td><span class="badge-before-val">${log.before}</span></td>
                    <td><span class="badge-after-val">${log.after}</span></td>
                    <td>${log.action}</td>
                </tr>
            `).join("");
        }
    }

    const thead = document.getElementById("hr-gk-thead");
    const tbody = document.getElementById("hr-gk-tbody");
    const rows = (data.preview || []).slice(0, 12);
    const cols = data.columns || [];

    if (thead && cols.length > 0) {
        thead.innerHTML = `<tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr>`;
    }
    if (tbody) {
        tbody.innerHTML = rows.map(r => {
            return `<tr>${cols.map(c => `<td>${r[c] !== undefined ? r[c] : ""}</td>`).join("")}</tr>`;
        }).join("");
    }
}

function populateHumanEvaluationPanel(data) {
    const analysis = data.gemini_analysis || {};
    const loopCount = data.analysis_loop_count || 0;

    document.getElementById("hr-eval-loop-tag").innerText = loopCount > 0 ? `Đã điều chỉnh & phân tích lại (${loopCount} lần)` : "Đánh giá lần #1";

    const domainEl = document.getElementById("hr-eval-domain");
    if (domainEl) {
        const feedbackHtml = analysis.human_feedback_applied
            ? `<br><strong>🔄 Yêu cầu điều chỉnh đã áp dụng:</strong> <em>"${analysis.human_feedback_applied}"</em>`
            : "";
        domainEl.innerHTML = `
            <strong>🎯 Lĩnh vực &amp; Chiều phân tích chính:</strong> ${analysis.domain_detected || ""}<br>
            <strong>📌 Tóm tắt phân tích Dashboard trình lãnh đạo:</strong> ${analysis.dataset_summary || ""}
            ${feedbackHtml}
        `;
    }

    const kpisEl = document.getElementById("hr-eval-kpis");
    if (kpisEl) {
        kpisEl.innerHTML = (analysis.kpis || []).map(k => `
            <div class="hr-kpi-mini">
                <span>${k.label}</span>
                <strong>${k.value}</strong>
            </div>
        `).join("");
    }

    const prioEl = document.getElementById("hr-eval-priorities");
    if (prioEl) {
        const roadmap = analysis.strategic_roadmap || {};
        const proposals = (roadmap.proposals_for_upper_management || []).slice(0, 3).map(pr => `<li>${pr}</li>`).join("");
        prioEl.innerHTML = `
            <strong>📌 Kiến nghị trình Cấp trên phê duyệt (từ phân tích Dashboard):</strong>
            <ul style="margin-top: 6px; padding-left: 20px;">${proposals}</ul>
        `;
    }
}

function updateSidebarDataStatus(hasData, domain, source) {
    const dot = document.getElementById("nav-data-dot");
    const text = document.getElementById("nav-data-text");
    const sub = document.getElementById("nav-data-sub");

    if (hasData) {
        if (dot) dot.className = "status-dot dot-ready";
        if (text) text.innerText = domain || "Đang xử lý";
        if (sub) sub.innerText = source || "Đã nạp dữ liệu";
    } else {
        if (dot) dot.className = "status-dot dot-idle";
        if (text) text.innerText = "Chưa có dữ liệu";
        if (sub) sub.innerText = "Chọn file & bối cảnh để bắt đầu";
    }
}

function resetToEmptyState() {
    currentStage = "idle";
    currentSelectedFile = null;
    isSampleSelected = false;
    currentDashboardModel = null;
    updateSidebarDataStatus(false, "", "");
    rawTableData = [];
    tableColumns = [];
    updateReadinessState();

    const topPill = document.getElementById("top-stage-pill");
    if (topPill) topPill.innerText = "Bước 1: Nhập dữ liệu & Bối cảnh";

    const gkPanel = document.getElementById("human-gatekeeper-panel");
    const evalPanel = document.getElementById("human-evaluation-panel");
    if (gkPanel) gkPanel.style.display = "none";
    if (evalPanel) evalPanel.style.display = "none";

    const fileBadge = document.getElementById("selected-file-badge");
    if (fileBadge) fileBadge.style.display = "none";
    const uploadTitle = document.getElementById("upload-status-title");
    if (uploadTitle) uploadTitle.innerText = "Kéo thả file Excel (.xlsx, .xls) hoặc CSV vào đây";

    const homeBanner = document.getElementById("home-data-banner");
    if (homeBanner) homeBanner.style.display = "none";

    document.getElementById("dash-empty").style.display = "flex";
    document.getElementById("dash-content").style.display = "none";
    document.getElementById("report-empty").style.display = "flex";
    document.getElementById("report-content").style.display = "none";
    document.getElementById("excel-empty").style.display = "flex";
    document.getElementById("excel-content").style.display = "none";
}

// =========================================================================
// DASHBOARD RENDERING (BỐ CỤC MẪU - TONE XANH DƯƠNG & DỮ LIỆU ĐỘNG)
// =========================================================================
function renderDashboardView(analysis) {
    document.getElementById("dash-empty").style.display = "none";
    document.getElementById("dash-content").style.display = "block";

    const dash = analysis.dashboard_model;
    if (!dash) return;
    currentDashboardModel = dash;

    const mainTitleEl = document.getElementById("dk-main-title");
    if (mainTitleEl) {
        mainTitleEl.innerText = dash.dashboard_title || "Dashboard Phân Tích Quản Trị";
    }

    // Populate Dimension filter ("Chiều phân tích")
    const dimSelect = document.getElementById("dk-dimension-select");
    if (dimSelect) {
        const dimOpts = dash.dimension_options || [];
        dimSelect.innerHTML = dimOpts.map(o => `<option value="${o.value}">${o.label}</option>`).join("");
        dimSelect.value = dash.default_dimension || (dimOpts[0] ? dimOpts[0].value : "");
    }

    // Populate Period filter ("Kỳ báo cáo")
    const periodSelect = document.getElementById("dk-period-select");
    if (periodSelect) {
        const opts = dash.period_options || [];
        periodSelect.innerHTML = opts.map(o => `<option value="${o.value}">${o.label}</option>`).join("");
        periodSelect.value = dash.default_period || (opts[0] ? opts[0].value : "all");
    }

    // Render Trend Chart (Card 1: Top-Left - Blue Theme)
    renderTrendCard(dash.trend_chart);

    // Render active slice (Dimension + Period)
    renderDashboardSlice(dash.default_dimension, dash.default_period || "all");
}

function renderTrendCard(trendChart) {
    if (!trendChart) return;
    document.getElementById("dk-trend-title").innerText = trendChart.title || "Biến động theo kỳ";
    document.getElementById("dk-trend-sub").innerText = trendChart.subtitle || "Đối chiếu xu hướng qua các kỳ dữ liệu";

    const tbody = document.getElementById("dk-monthly-tbody");
    if (tbody) {
        tbody.innerHTML = (trendChart.monthly_table || []).map(r => `
            <tr>
                <td><strong>${r.month}</strong></td>
                <td>${r.orders}</td>
                <td><strong style="color: #1d4ed8;">${r.revenue}</strong></td>
                <td>${r.cost}</td>
                <td>${r.profit}</td>
            </tr>
        `).join("");
    }

    if (typeof Chart === "undefined") return;
    const canvas = document.getElementById("dkTrendCanvas");
    if (!canvas) return;
    if (trendChartInstance) trendChartInstance.destroy();

    const ctx = canvas.getContext("2d");
    const vals = trendChart.values || [];
    const maxVal = Math.max(...vals, 1);

    trendChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: trendChart.labels || [],
            datasets: [{
                label: trendChart.title || "Giá trị",
                data: vals,
                borderColor: "#2563eb",
                backgroundColor: "rgba(37, 99, 235, 0.14)",
                borderWidth: 2.8,
                pointBackgroundColor: "#1d4ed8",
                pointBorderColor: "#ffffff",
                pointBorderWidth: 1.5,
                pointRadius: 4.5,
                fill: true,
                tension: 0.15
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: "#eff6ff" },
                    ticks: { color: "#334155", font: { size: 11, weight: "600" } }
                },
                y: {
                    beginAtZero: true,
                    suggestedMax: maxVal,
                    grid: { color: "#eff6ff" },
                    ticks: {
                        color: "#334155",
                        font: { size: 11 },
                        callback: function(value) {
                            if (value === 0) return "0";
                            if (Math.abs(value) >= 1000000) {
                                return (value / 1000000).toFixed(1).replace(".", ",") + " Tr";
                            }
                            return value.toLocaleString("vi-VN");
                        }
                    }
                }
            }
        }
    });
}

function renderDashboardSlice(dimKey, periodKey) {
    if (!currentDashboardModel) return;
    let view = null;

    if (currentDashboardModel.by_dim_and_period && currentDashboardModel.by_dim_and_period[dimKey]) {
        const dimMap = currentDashboardModel.by_dim_and_period[dimKey];
        view = dimMap[periodKey] || dimMap[currentDashboardModel.default_period];
    }
    if (!view && currentDashboardModel.by_period) {
        view = currentDashboardModel.by_period[periodKey] || currentDashboardModel.by_period[currentDashboardModel.default_period];
    }
    if (!view) return;

    // 1. Header Subtitle
    document.getElementById("dk-main-sub").innerText = view.header_subtitle || "";

    // 2. Render 4 KPI Cards (Blue top border & Blue numbers)
    const kpiContainer = document.getElementById("dk-kpi-container");
    if (kpiContainer) {
        kpiContainer.innerHTML = (view.kpis || []).map(k => `
            <div class="dk-kpi-box">
                <div>
                    <div class="dk-kpi-title">${k.label}</div>
                    <div class="dk-kpi-val">${k.value}</div>
                </div>
                <div>
                    <div class="dk-kpi-unit">${k.sub}</div>
                    <div class="dk-kpi-cmp">${k.comparison_html}</div>
                </div>
            </div>
        `).join("");
    }

    // 3. Render Card 2 (Top-Right): Cơ cấu (Doughnut + Legend in Blue palette)
    const costSt = view.cost_structure || {};
    document.getElementById("dk-cost-title").innerText = costSt.title || "Cơ cấu phân bổ";
    document.getElementById("dk-cost-sub").innerText = costSt.subtitle || "";

    const costItems = costSt.items || [];
    const legendContainer = document.getElementById("dk-cost-legend");
    if (legendContainer) {
        legendContainer.innerHTML = costItems.map(item => `
            <div class="dk-legend-item">
                <div class="dk-legend-top">
                    <span class="dk-legend-name">
                        <span class="dk-legend-dot" style="background: ${item.color};"></span>
                        <span>${item.label}</span>
                    </span>
                    <span class="dk-legend-pct">${item.pct_str}</span>
                </div>
                <div class="dk-legend-val">${item.formatted_value}</div>
            </div>
        `).join("");
    }

    if (typeof Chart !== "undefined") {
        const costCanvas = document.getElementById("dkCostCanvas");
        if (costCanvas) {
            if (costChartInstance) costChartInstance.destroy();
            costChartInstance = new Chart(costCanvas.getContext("2d"), {
                type: "doughnut",
                data: {
                    labels: costItems.map(x => x.label),
                    datasets: [{
                        data: costItems.map(x => x.value),
                        backgroundColor: costItems.map(x => x.color),
                        borderWidth: 1,
                        borderColor: "#ffffff"
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "58%",
                    plugins: {
                        legend: { display: false }
                    }
                }
            });
        }
    }

    // 4. Render Card 3 (Bottom-Left): Tỷ trọng đóng góp (Blue Horizontal Bars)
    const revSt = view.revenue_contribution || {};
    document.getElementById("dk-rev-title").innerText = revSt.title || "Tỷ trọng đóng góp";
    document.getElementById("dk-rev-sub").innerText = revSt.subtitle || "";
    document.getElementById("dk-rev-footer").innerText = revSt.footer || "";

    const revBarsEl = document.getElementById("dk-rev-bars");
    if (revBarsEl) {
        revBarsEl.innerHTML = (revSt.items || []).map(item => `
            <div class="dk-bar-row">
                <div class="dk-bar-label" title="${item.label}">${item.label}</div>
                <div class="dk-bar-track">
                    <div class="dk-bar-fill" style="width: ${item.bar_pct}%;"></div>
                </div>
                <div class="dk-bar-val">${item.formatted_value}</div>
            </div>
        `).join("");
    }

    // 5. Render Card 4 (Bottom-Right): Nhóm làm thay đổi giữa các kỳ (Blue for +, Purple for -)
    const deltaSt = view.revenue_delta || {};
    document.getElementById("dk-delta-title").innerText = deltaSt.title || "Nhóm tạo biến động";
    document.getElementById("dk-delta-sub").innerText = deltaSt.subtitle || "";
    document.getElementById("dk-delta-summary").innerText = deltaSt.summary_line || "";
    document.getElementById("dk-delta-footer").innerText = deltaSt.footer || "";

    const deltaBarsEl = document.getElementById("dk-delta-bars");
    if (deltaBarsEl) {
        deltaBarsEl.innerHTML = (deltaSt.items || []).map(item => `
            <div class="dk-bar-row">
                <div class="dk-bar-label" title="${item.label}">${item.label}</div>
                <div class="dk-bar-track">
                    <div class="dk-bar-fill ${item.is_negative ? 'fill-negative' : ''}" style="width: ${item.bar_pct}%;"></div>
                </div>
                <div class="dk-bar-val">${item.formatted_delta}</div>
            </div>
        `).join("");
    }
}

// =========================================================================
// WORD REPORT RENDERING (ĐƯA CẢ DASHBOARD VÀO BÁO CÁO & PHÂN TÍCH SÂU)
// =========================================================================
function renderReportView(analysis, gk) {
    document.getElementById("report-empty").style.display = "none";
    document.getElementById("report-content").style.display = "block";

    const summary = gk ? gk.summary : {};
    const cmp = (gk && gk.comparison) ? gk.comparison : {};
    const dash = analysis.dashboard_model || {};
    const defaultP = dash.default_period || "all";
    const activeView = (dash.by_period && dash.by_period[defaultP]) ? dash.by_period[defaultP] : {};
    const trendChart = dash.trend_chart || {};
    const deep = analysis.report_deep_analysis || {};
    const roadmap = analysis.strategic_roadmap || {};
    const nowStr = new Date().toLocaleDateString("vi-VN");

    const kpis = activeView.kpis || [];
    const kpiAnalyses = deep.kpi_deep_analysis || [];

    // Embedded visual KPI cards inside Word Report
    const embeddedKpisHtml = kpis.map(k => `
        <div class="report-embedded-kpi-card">
            <div class="rk-lbl">${k.label}</div>
            <div class="rk-val">${k.value}</div>
            <div class="rk-cmp">${k.comparison_html || k.sub || ""}</div>
        </div>
    `).join("");

    // Embedded visual Chart 1 (Trend bars - 2-line safe layout so numbers never overflow)
    const trendVals = trendChart.values || [];
    const maxTrend = Math.max(...trendVals, 1);
    const embeddedTrendBarsHtml = (trendChart.monthly_table || []).map((m, i) => {
        const pct = Math.max(8, Math.round(((trendVals[i] || 0) / maxTrend) * 100));
        return `
            <div class="report-bar-item">
                <div class="report-bar-top">
                    <span class="report-bar-lbl"><strong>${m.month}</strong></span>
                    <span class="report-bar-num" style="color: #1d4ed8;">${m.revenue}</span>
                </div>
                <div class="dk-bar-track"><div class="dk-bar-fill" style="width: ${pct}%;"></div></div>
            </div>
        `;
    }).join("");

    const costItems = (activeView.cost_structure && activeView.cost_structure.items) ? activeView.cost_structure.items : [];
    const embeddedCostHtml = costItems.map(c => `
        <div class="report-bar-item">
            <div class="report-bar-top">
                <span class="report-bar-lbl"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c.color};margin-right:6px;"></span>${c.label}</span>
                <span class="report-bar-num">${c.formatted_value} (${c.pct_str})</span>
            </div>
            <div class="dk-bar-track"><div class="dk-bar-fill" style="width: ${Math.max(6, Math.round(c.pct))}%; background: ${c.color};"></div></div>
        </div>
    `).join("");

    const revItems = (activeView.revenue_contribution && activeView.revenue_contribution.items) ? activeView.revenue_contribution.items : [];
    const embeddedRevHtml = revItems.map(r => `
        <div class="report-bar-item">
            <div class="report-bar-top">
                <span class="report-bar-lbl">${r.label}</span>
                <span class="report-bar-num" style="color: #1d4ed8;">${r.formatted_value} (${r.share_pct}%)</span>
            </div>
            <div class="dk-bar-track"><div class="dk-bar-fill" style="width: ${r.bar_pct}%;"></div></div>
        </div>
    `).join("");

    const deltaItems = (activeView.revenue_delta && activeView.revenue_delta.items) ? activeView.revenue_delta.items : [];
    const embeddedDeltaHtml = deltaItems.map(d => `
        <div class="report-bar-item">
            <div class="report-bar-top">
                <span class="report-bar-lbl">${d.label}</span>
                <span class="report-bar-num" style="color: ${d.is_negative ? '#7c3aed' : '#1d4ed8'};">${d.formatted_delta}</span>
            </div>
            <div class="dk-bar-track"><div class="dk-bar-fill ${d.is_negative ? 'fill-negative' : ''}" style="width: ${d.bar_pct}%;"></div></div>
        </div>
    `).join("");

    const kpiRowsHtml = kpis.map((k, idx) => `
        <tr>
            <td><strong>${k.label}</strong></td>
            <td><strong style="color: #1d4ed8;">${k.value}</strong></td>
            <td>${k.comparison_html || ""}</td>
            <td>${kpiAnalyses[idx] || k.sub || ""}</td>
        </tr>
    `).join("");

    const monthlyRowsHtml = (trendChart.monthly_table || []).map(m => `
        <tr>
            <td><strong>${m.month_display} (${m.month})</strong></td>
            <td>${m.orders}</td>
            <td><strong style="color: #1d4ed8;">${m.revenue}</strong></td>
            <td>${m.cost}</td>
            <td>${m.profit}</td>
        </tr>
    `).join("");

    const costRowsHtml = costItems.map(c => `
        <tr>
            <td><strong>${c.label}</strong></td>
            <td><strong>${c.formatted_value}</strong></td>
            <td>${c.pct_str}</td>
        </tr>
    `).join("");

    const revRowsHtml = revItems.map(r => `
        <tr>
            <td><strong>${r.label}</strong></td>
            <td><strong style="color: #1d4ed8;">${r.formatted_value}</strong></td>
            <td>${r.share_pct}%</td>
        </tr>
    `).join("");

    const deltaRowsHtml = deltaItems.map(d => {
        const sign = (!d.is_negative && d.delta > 0) ? "+" : "";
        const color = d.is_negative ? "#7c3aed" : "#1d4ed8";
        const statusTxt = d.is_negative ? "Sụt giảm (Thanh tím - Cần khắc phục)" : "Đóng góp tăng trưởng dương (Thanh xanh dương)";
        return `
            <tr>
                <td><strong>${d.label}</strong></td>
                <td><strong style="color: ${color};">${sign}${d.formatted_delta}</strong></td>
                <td>${statusTxt}</td>
            </tr>
        `;
    }).join("");

    const bottlenecksHtml = (roadmap.bottlenecks_and_risks || []).map(b => `<li>${b}</li>`).join("");
    const shortTermHtml = (roadmap.short_term_actions || []).map(s => `<li>${s}</li>`).join("");
    const longTermHtml = (roadmap.medium_long_term_orientation || []).map(l => `<li>${l}</li>`).join("");
    const proposalsHtml = (roadmap.proposals_for_upper_management || []).map(pr => `<li><strong>${pr}</strong></li>`).join("");

    const reportPaper = document.getElementById("report-paper-body");
    reportPaper.innerHTML = `
        <div class="report-admin-header">
            <div>
                <strong>HỆ THỐNG PHÂN TÍCH QUẢN TRỊ SPHEREAI</strong><br>
                <span>BỘ PHẬN PHÂN TÍCH DỮ LIỆU &amp; CHIẾN LƯỢC</span>
            </div>
            <div>
                <strong>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</strong><br>
                <strong>Độc lập - Tự do - Hạnh phúc</strong><br>
                <em>Ngày lập báo cáo: ${nowStr}</em>
            </div>
        </div>

        <div class="report-main-heading">
            <h1>${analysis.report_title || "BÁO CÁO PHÂN TÍCH SÂU DASHBOARD QUẢN TRỊ & ĐỊNH HƯỚNG PHÁT TRIỂN TRÌNH CẤP TRÊN"}</h1>
            <div class="sub-kính-trình">Kính trình: Ban Giám đốc / Cấp Lãnh đạo có thẩm quyền phê duyệt • Kỳ báo cáo: ${activeView.period_display || ""}</div>
        </div>

        <h2>I. BỐI CẢNH DOANH NGHIỆP &amp; TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)</h2>
        <p><strong>1. Bối cảnh &amp; Bài toán doanh nghiệp đang gặp phải:</strong> ${analysis.business_context || ""}</p>
        <p><strong>2. Tóm tắt kết quả phân tích trên Dashboard trình Lãnh đạo:</strong> ${analysis.dataset_summary || ""}</p>
        <p><strong>3. Đối chiếu chất lượng dữ liệu đầu vào (Trước → Sau khi làm sạch):</strong> Từ ${cmp.before_rows || summary.total_records} dòng ban đầu (Độ sạch ${cmp.before_health_score || 0}%) → Sau làm sạch đạt <strong>${summary.total_records || 0} dòng sạch (Độ sạch ${summary.health_score || 100}%)</strong>, đã lọc bỏ ${cmp.removed_duplicates || 0} dòng trùng và xử lý chuẩn hóa ${cmp.filled_missing_cells || 0} ô bị trống.</p>

        <h2>II. TỔNG QUAN DASHBOARD TRỰC QUAN &amp; PHÂN TÍCH SÂU 4 CHỈ SỐ KPI (${activeView.period_display || ""})</h2>
        <p><em>Bản chụp trực quan Dashboard KPI (4 chỉ số trọng tâm &amp; 4 biểu đồ phân tích theo chiều "${activeView.dimension_col || dash.default_dimension || "Tổng hợp"}") được đính kèm trực tiếp dưới đây và trong file Word (.docx) tải về:</em></p>

        <div class="report-embedded-dash">
            <div class="report-embedded-dash-header">
                <div class="report-embedded-dash-title">📊 ${dash.dashboard_title || "Dashboard KPI Quản Trị"} — ${activeView.period_display || ""}</div>
                <span class="report-embedded-dash-badge">Chiều phân tích: ${activeView.dimension_col || dash.default_dimension || "Tổng hợp"}</span>
            </div>
            <div class="report-embedded-kpis">
                ${embeddedKpisHtml}
            </div>
            <div class="report-embedded-charts-grid">
                <div class="report-embedded-chart-box">
                    <h4>1. ${trendChart.title || "Xu hướng theo kỳ"}</h4>
                    <div class="rc-sub">${trendChart.subtitle || ""}</div>
                    ${embeddedTrendBarsHtml}
                </div>
                <div class="report-embedded-chart-box">
                    <h4>2. ${activeView.cost_structure?.title || "Cơ cấu phân bổ"}</h4>
                    <div class="rc-sub">${activeView.cost_structure?.subtitle || ""}</div>
                    ${embeddedCostHtml}
                </div>
                <div class="report-embedded-chart-box">
                    <h4>3. ${activeView.revenue_contribution?.title || "Tỷ trọng đóng góp"}</h4>
                    <div class="rc-sub">${activeView.revenue_contribution?.subtitle || ""}</div>
                    ${embeddedRevHtml}
                </div>
                <div class="report-embedded-chart-box">
                    <h4>4. ${activeView.revenue_delta?.title || "Nhóm làm thay đổi giữa 2 kỳ"}</h4>
                    <div class="rc-sub">${activeView.revenue_delta?.subtitle || ""}</div>
                    ${embeddedDeltaHtml}
                </div>
            </div>
        </div>

        <table class="report-table">
            <thead>
                <tr>
                    <th>Chỉ số KPI trên Dashboard</th>
                    <th>Giá trị đạt được</th>
                    <th>So sánh kỳ trước</th>
                    <th>Phân tích chuyên sâu &amp; Đánh giá quản trị</th>
                </tr>
            </thead>
            <tbody>${kpiRowsHtml}</tbody>
        </table>

        <h2>III. PHÂN TÍCH CHUYÊN SÂU TỪNG BIỂU ĐỒ TRÊN DASHBOARD</h2>

        <h3>1. Phân tích Biểu đồ 1 — "${trendChart.title || "Xu hướng theo kỳ"}"</h3>
        <p><strong>• Nhận định chuyên sâu xu hướng:</strong> ${deep.trend_analysis || ""}</p>
        <table class="report-table">
            <thead>
                <tr>
                    <th>Kỳ dữ liệu</th>
                    <th>Số bản ghi</th>
                    <th>Giá trị / Doanh thu</th>
                    <th>Chi phí / Nguồn lực</th>
                    <th>Lợi nhuận / Hiệu quả</th>
                </tr>
            </thead>
            <tbody>${monthlyRowsHtml}</tbody>
        </table>

        <h3>2. Phân tích Biểu đồ 2 — "${activeView.cost_structure?.title || "Cơ cấu phân bổ"}" (${activeView.cost_structure?.subtitle || ""})</h3>
        <p><strong>• Nhận định chuyên sâu cơ cấu:</strong> ${deep.cost_structure_analysis || ""}</p>
        <table class="report-table">
            <thead>
                <tr>
                    <th>Nhóm / Hạng mục</th>
                    <th>Giá trị phân bổ</th>
                    <th>Tỷ trọng (%)</th>
                </tr>
            </thead>
            <tbody>${costRowsHtml}</tbody>
        </table>

        <h3>3. Phân tích Biểu đồ 3 — "${activeView.revenue_contribution?.title || "Tỷ trọng đóng góp"}" (${activeView.revenue_contribution?.subtitle || ""})</h3>
        <p><strong>• Nhận định chuyên sâu đóng góp:</strong> ${deep.revenue_contribution_analysis || ""}</p>
        <table class="report-table">
            <thead>
                <tr>
                    <th>Nhóm / Hạng mục (Theo giá trị giảm dần)</th>
                    <th>Giá trị đóng góp</th>
                    <th>Tỷ trọng đóng góp (%)</th>
                </tr>
            </thead>
            <tbody>${revRowsHtml}</tbody>
        </table>

        <h3>4. Phân tích Biểu đồ 4 — "${activeView.revenue_delta?.title || "Nhóm làm thay đổi giữa 2 kỳ"}" (${activeView.revenue_delta?.subtitle || ""})</h3>
        <p><strong>• Tổng hợp biến động giữa 2 kỳ:</strong> ${activeView.revenue_delta?.summary_line || ""}</p>
        <p><strong>• Phân tích sâu động lực tăng/giảm:</strong> ${deep.revenue_delta_analysis || ""}</p>
        <table class="report-table">
            <thead>
                <tr>
                    <th>Nhóm / Hạng mục</th>
                    <th>Mức biến động</th>
                    <th>Đánh giá biến động trên Dashboard</th>
                </tr>
            </thead>
            <tbody>${deltaRowsHtml}</tbody>
        </table>

        <h2>IV. ĐỊNH HƯỚNG PHÁT TRIỂN TIẾP THEO &amp; KIẾN NGHỊ TRÌNH CẤP TRÊN PHÊ DUYỆT</h2>
        <h3>1. Các điểm nghẽn &amp; rủi ro trọng yếu đúc kết từ Dashboard:</h3>
        <ul>${bottlenecksHtml}</ul>

        <h3>2. Giải pháp hành động ngắn hạn (Trong 30 ngày tới):</h3>
        <ul>${shortTermHtml}</ul>

        <h3>3. Định hướng phát triển trung và dài hạn (Quý tới / 6 - 12 tháng):</h3>
        <ul>${longTermHtml}</ul>

        <h3>4. Kiến nghị &amp; Đề xuất trình Cấp trên / Ban Giám đốc xem xét phê duyệt:</h3>
        <ul>${proposalsHtml}</ul>

        <div class="report-sig-box">
            <div>
                <strong>NGƯỜI LẬP BÁO CÁO / ĐƠN VỊ TRÌNH</strong><br>
                <em>(Ký và ghi rõ họ tên)</em><br><br><br><br>
            </div>
            <div>
                <strong>Ý KIẾN PHÊ DUYỆT CỦA CẤP TRÊN / BAN GIÁM ĐỐC</strong><br>
                <em>(Phê duyệt định hướng &amp; giao chỉ tiêu thực hiện)</em><br><br><br><br>
            </div>
        </div>
    `;
}

// ---------------- EXCEL VIEW RENDERING ----------------
function renderExcelView(data) {
    document.getElementById("excel-empty").style.display = "none";
    document.getElementById("excel-content").style.display = "block";

    const gk = data.gatekeeper.summary;
    const cmp = data.gatekeeper.comparison || {};
    document.getElementById("gk-stat-health").innerText = `${cmp.before_health_score || 0}% → ${gk.health_score}%`;
    document.getElementById("gk-stat-decision").innerText = gk.decision || "Đã làm sạch";
    document.getElementById("gk-stat-valid").innerText = `${cmp.before_rows || gk.total_records} → ${gk.total_records} dòng`;
    document.getElementById("gk-stat-missing").innerText = `${cmp.filled_missing_cells || 0} ô`;
    document.getElementById("gk-stat-dup").innerText = `${cmp.removed_duplicates || 0} dòng`;

    renderPreviewTable(rawTableData);
}

function renderPreviewTable(rows) {
    const thead = document.getElementById("preview-thead");
    const tbody = document.getElementById("preview-tbody");
    const countLabel = document.getElementById("table-rows-count");

    if (countLabel) countLabel.innerText = `Hiển thị ${rows.length} / ${rawTableData.length} dòng`;

    if (tableColumns.length > 0) {
        thead.innerHTML = `<tr>${tableColumns.map(c => `<th>${c}</th>`).join('')}</tr>`;
    } else if (rows.length > 0) {
        thead.innerHTML = `<tr>${Object.keys(rows[0]).map(c => `<th>${c}</th>`).join('')}</tr>`;
    }

    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${tableColumns.length || 5}" style="text-align: center; color: #94a3b8; padding: 24px;">Không tìm thấy bản ghi phù hợp</td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map(r => {
        const cells = (tableColumns.length > 0 ? tableColumns : Object.keys(r)).map(col => {
            const val = r[col] !== undefined ? r[col] : "";
            return `<td>${val}</td>`;
        }).join('');
        return `<tr>${cells}</tr>`;
    }).join('');
}

function filterPreviewTable(query) {
    if (!query) {
        renderPreviewTable(rawTableData);
        return;
    }
    const filtered = rawTableData.filter(row => {
        return Object.values(row).some(v => String(v).toLowerCase().includes(query));
    });
    renderPreviewTable(filtered);
}
