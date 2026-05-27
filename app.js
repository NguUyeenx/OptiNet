// Global state
const API_BASE = ""; // Same origin
let logPollInterval = null;
let lastLogLength = 0;
let lastAction = ""; // "diagnose" or "optimize"
let activeBtnElement = null;
let activeBtnOriginalHtml = "";

// On page load
document.addEventListener("DOMContentLoaded", () => {
    init();
});

// Initialization
async function init() {
    logToTerminal("[System] Connecting to OptiNet backend server...");
    initCardTilt();
    await fetchSystemStatus();
    await loadExistingReports();
}

// Float Toast Notification system
function showToast(title, message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let icon = "fa-circle-info text-cyan";
    if (type === "success") icon = "fa-circle-check text-emerald";
    if (type === "warning") icon = "fa-triangle-exclamation text-gold";
    if (type === "danger") icon = "fa-circle-xmark text-red";
    
    toast.innerHTML = `
        <i class="fa-solid ${icon} toast-icon"></i>
        <div class="toast-content">
            <span class="toast-title">${title}</span>
            <span class="toast-message">${message}</span>
        </div>
    `;
    
    container.appendChild(toast);
    
    // Trigger transition reflow
    setTimeout(() => {
        toast.classList.add("active");
    }, 10);
    
    // Auto dismiss after 4.5 seconds
    setTimeout(() => {
        toast.style.animation = "toastFadeOut 0.4s ease forwards";
        setTimeout(() => {
            toast.remove();
        }, 400);
    }, 4500);
}

// Fetch general system status
async function fetchSystemStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (!res.ok) throw new Error("Could not fetch API status");
        
        const data = await res.json();
        
        // Update Wi-Fi SSID
        document.getElementById("activeSsid").innerText = data.active_profile;
        
        // Update LLMNR status label
        const llmnrVal = document.getElementById("llmnrVal");
        if (data.llmnr_status === "Disabled") {
            llmnrVal.innerText = "Disabled (Safe & Optimal)";
            llmnrVal.className = "llmnr-value text-emerald";
        } else {
            llmnrVal.innerText = "Enabled (Default - Noise)";
            llmnrVal.className = "llmnr-value text-magenta";
        }

        // Check if engine is currently busy
        if (data.engine_status === "diagnosing" || data.engine_status === "optimizing") {
            lastAction = data.engine_status === "diagnosing" ? "diagnose" : "optimize";
            logToTerminal(`[System] Active background task detected: '${data.engine_status}'. Syncing logs...`);
            
            // Set the appropriate button as active progress button
            const btnScan = document.getElementById("btnScan");
            const btnOptimize = document.getElementById("btnOptimize");
            if (data.engine_status === "diagnosing") {
                activeBtnElement = btnScan;
                activeBtnOriginalHtml = btnScan.innerHTML;
                btnScan.classList.add("btn-progress-active");
                btnScan.style.setProperty("--progress-percent", `${data.engine_progress}%`);
                btnScan.innerHTML = `
                    <div class="circle-dots-loader">
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                    </div>
                    <span>Scanning... <span class="btn-progress-pct">${data.engine_progress}%</span></span>
                `;
            } else {
                activeBtnElement = btnOptimize;
                activeBtnOriginalHtml = btnOptimize.innerHTML;
                btnOptimize.classList.add("btn-progress-active");
                btnOptimize.style.setProperty("--progress-percent", `${data.engine_progress}%`);
                btnOptimize.innerHTML = `
                    <div class="circle-dots-loader">
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                        <div class="spinner-dot"></div>
                    </div>
                    <span>Optimizing... <span class="btn-progress-pct">${data.engine_progress}%</span></span>
                `;
            }
            
            startLogPolling();
        } else if (data.engine_status === "completed") {
            updateSystemHeader(true);
        }
    } catch (err) {
        logToTerminal(`[!] Connection failed: ${err.message}. Ensure python server.py is running.`);
        showToast("Connection Error", "Could not connect to OptiNet backend. Ensure server.py is running.", "danger");
    }
}

// Load existing report files to pre-populate UI
async function loadExistingReports() {
    try {
        // 1. Try to load baseline report
        const resReport = await fetch(`${API_BASE}/api/report-data`);
        if (resReport.ok) {
            const beforeData = await resReport.json();
            if (!beforeData.error) {
                logToTerminal("[System] Baseline diagnostics report loaded successfully.");
                updateUiWithReport(beforeData, false);
            }
        }

        // 2. Try to load post-optimization report
        const resAfter = await fetch(`${API_BASE}/api/after-data`);
        if (resAfter.ok) {
            const afterData = await resAfter.json();
            if (!afterData.error) {
                logToTerminal("[System] Post-optimization report loaded successfully.");
                updateUiWithReport(afterData, true);
                updateSystemHeader(true);
            }
        }

        // 3. Try to load comparative report
        checkAndRenderCompare();
    } catch (err) {
        console.error("Error loading reports:", err);
    }
}

// Update the main header indicator
function updateSystemHeader(isOptimized) {
    const statusDot = document.getElementById("statusDot");
    const statusLabel = document.getElementById("statusLabel");
    
    if (isOptimized) {
        statusDot.className = "status-dot success";
        statusLabel.innerText = "System Optimized";
    } else {
        statusDot.className = "status-dot warning";
        statusLabel.innerText = "System Unoptimized";
    }
}

// LOG TERMINAL UTILITY
function logToTerminal(message) {
    const terminal = document.getElementById("terminalLog");
    if (!terminal) return;
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.innerText = message;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

// Polling for background task logs
function startLogPolling() {
    if (logPollInterval) clearInterval(logPollInterval);
    
    // Disable action buttons based on which is active
    const btnScan = document.getElementById("btnScan");
    const btnOptimize = document.getElementById("btnOptimize");
    
    if (activeBtnElement === btnScan) {
        btnOptimize.disabled = true;
    } else if (activeBtnElement === btnOptimize) {
        btnScan.disabled = true;
    } else {
        btnScan.disabled = true;
        btnOptimize.disabled = true;
    }
    
    document.getElementById("terminalProgressContainer").style.display = "block";
    const statusIndicator = document.getElementById("engineStatusIndicator");
    const statusDot = document.getElementById("statusDot");
    
    statusDot.className = "status-dot animating";
    statusIndicator.innerText = "Processing...";
    
    lastLogLength = 0;
    
    logPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/logs`);
            if (!res.ok) return;
            const data = await res.json();
            
            // Render new log lines
            if (data.logs.length > lastLogLength) {
                for (let i = lastLogLength; i < data.logs.length; i++) {
                    logToTerminal(data.logs[i]);
                }
                lastLogLength = data.logs.length;
            }
            
            // Update progress bar
            document.getElementById("terminalProgressFill").style.width = `${data.progress}%`;
            statusIndicator.innerText = `Running (${data.progress}%)`;
            
            // Update active button progress fill and percentage text
            if (activeBtnElement) {
                activeBtnElement.style.setProperty("--progress-percent", `${data.progress}%`);
                const pctSpan = activeBtnElement.querySelector(".btn-progress-pct");
                if (pctSpan) pctSpan.innerText = `${data.progress}%`;
            }
            
            // Check for completion
            if (data.status === "completed") {
                clearInterval(logPollInterval);
                logPollInterval = null;
                
                logToTerminal("[System] Task completed successfully!");
                
                // Hide progress bar and set status
                document.getElementById("terminalProgressContainer").style.display = "none";
                statusIndicator.innerText = "Completed";
                
                // Refresh data
                await fetchSystemStatus();
                
                const resReport = await fetch(`${API_BASE}/api/report-data`);
                let beforeReport = null;
                if (resReport.ok) beforeReport = await resReport.json();
                
                const resAfter = await fetch(`${API_BASE}/api/after-data`);
                let afterReport = null;
                if (resAfter.ok) afterReport = await resAfter.json();
                
                if (afterReport && !afterReport.error) {
                    updateUiWithReport(afterReport, true);
                    updateSystemHeader(true);
                } else if (beforeReport && !beforeReport.error) {
                    updateUiWithReport(beforeReport, false);
                }
                
                // Check if we can show comparative report
                await checkAndRenderCompare();
                
                // Toast notification on completion
                if (lastAction === "diagnose") {
                    showToast("Scan Complete", "Baseline network stats and metrics loaded successfully.", "success");
                } else if (lastAction === "optimize") {
                    showToast("Optimization Complete", "Stale Wi-Fi networks dọn dẹp, system noise closed successfully!", "success");
                }
                
                // Trigger button completed filling animation
                if (activeBtnElement) {
                    activeBtnElement.style.setProperty("--progress-percent", "100%");
                    const pctSpan = activeBtnElement.querySelector(".btn-progress-pct");
                    if (pctSpan) pctSpan.innerText = "100%";
                    
                    setTimeout(() => {
                        // Switch to Completed state
                        activeBtnElement.innerHTML = `<i class="fa-solid fa-circle-check"></i> Completed`;
                        
                        // Stay completed for 1.8s then restore original button layout
                        setTimeout(() => {
                            activeBtnElement.classList.remove("btn-progress-active");
                            activeBtnElement.style.removeProperty("--progress-percent");
                            activeBtnElement.innerHTML = activeBtnOriginalHtml;
                            
                            // Re-enable buttons
                            btnScan.disabled = false;
                            btnOptimize.disabled = false;
                            activeBtnElement = null;
                            activeBtnOriginalHtml = "";
                        }, 1800);
                    }, 300);
                } else {
                    btnScan.disabled = false;
                    btnOptimize.disabled = false;
                }
            }
        } catch (err) {
            console.error("Error polling logs:", err);
        }
    }, 600);
}

// Trigger Diagnostics Scan
async function runDiagnostics() {
    const btn = document.getElementById("btnScan");
    try {
        logToTerminal("[System] Dispatching request to start Scan & Diagnose task...");
        showToast("Diagnostics Started", "OptiNet is running deep network analysis...", "info");
        
        // Active button progress initiation
        activeBtnElement = btn;
        activeBtnOriginalHtml = btn.innerHTML;
        btn.classList.add("btn-progress-active");
        btn.style.setProperty("--progress-percent", "0%");
        btn.innerHTML = `
            <div class="circle-dots-loader">
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
            </div>
            <span>Scanning... <span class="btn-progress-pct">0%</span></span>
        `;
        
        // Determine if after optimization based on report files presence
        const checkAfterRes = await fetch(`${API_BASE}/api/report-data`);
        const checkAfterData = await checkAfterRes.json();
        const query = (!checkAfterData.error) ? "?after=true" : "";
        
        const res = await fetch(`${API_BASE}/api/diagnose${query}`);
        if (!res.ok) throw new Error("Diagnose request failed");
        
        const data = await res.json();
        if (data.status === "started") {
            lastAction = "diagnose";
            startLogPolling();
        } else {
            logToTerminal(`[!] Error: Server busy: ${data.message}`);
            showToast("Server Busy", "Another process is already in progress.", "warning");
            
            // Failsafe restore button
            btn.classList.remove("btn-progress-active");
            btn.style.removeProperty("--progress-percent");
            btn.innerHTML = activeBtnOriginalHtml;
            activeBtnElement = null;
            activeBtnOriginalHtml = "";
            document.getElementById("btnScan").disabled = false;
            document.getElementById("btnOptimize").disabled = false;
        }
    } catch (err) {
        logToTerminal(`[!] Diagnose failed: ${err.message}`);
        showToast("Error", `Could not launch diagnostics: ${err.message}`, "danger");
        
        // Failsafe restore button
        btn.classList.remove("btn-progress-active");
        btn.style.removeProperty("--progress-percent");
        if (activeBtnOriginalHtml) btn.innerHTML = activeBtnOriginalHtml;
        activeBtnElement = null;
        activeBtnOriginalHtml = "";
        document.getElementById("btnScan").disabled = false;
        document.getElementById("btnOptimize").disabled = false;
    }
}

// Trigger Optimization Speedup
async function optimizeNetwork() {
    const btn = document.getElementById("btnOptimize");
    try {
        logToTerminal("[System] Dispatching request to launch Network Optimization packages...");
        showToast("Optimization Started", "Applying advanced network configurations...", "info");
        
        // Active button progress initiation
        activeBtnElement = btn;
        activeBtnOriginalHtml = btn.innerHTML;
        btn.classList.add("btn-progress-active");
        btn.style.setProperty("--progress-percent", "0%");
        btn.innerHTML = `
            <div class="circle-dots-loader">
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
            </div>
            <span>Optimizing... <span class="btn-progress-pct">0%</span></span>
        `;
        
        const res = await fetch(`${API_BASE}/api/optimize`, { method: "POST" });
        if (!res.ok) throw new Error("Optimize request failed");
        
        const data = await res.json();
        if (data.status === "started") {
            lastAction = "optimize";
            startLogPolling();
        } else {
            logToTerminal(`[!] Error: Server busy: ${data.message}`);
            showToast("Server Busy", "Another process is already in progress.", "warning");
            
            // Failsafe restore button
            btn.classList.remove("btn-progress-active");
            btn.style.removeProperty("--progress-percent");
            btn.innerHTML = activeBtnOriginalHtml;
            activeBtnElement = null;
            activeBtnOriginalHtml = "";
            document.getElementById("btnScan").disabled = false;
            document.getElementById("btnOptimize").disabled = false;
        }
    } catch (err) {
        logToTerminal(`[!] Optimization failed: ${err.message}`);
        showToast("Error", `Could not execute optimizations: ${err.message}`, "danger");
        
        // Failsafe restore button
        btn.classList.remove("btn-progress-active");
        btn.style.removeProperty("--progress-percent");
        if (activeBtnOriginalHtml) btn.innerHTML = activeBtnOriginalHtml;
        activeBtnElement = null;
        activeBtnOriginalHtml = "";
        document.getElementById("btnScan").disabled = false;
        document.getElementById("btnOptimize").disabled = false;
    }
}

// Update Dashboard Widgets with report data
function updateUiWithReport(report, isAfter) {
    if (!report || report.error) return;
    
    // 1. Update Speed Gauges
    const dl = report.speed.download_mbps;
    const ul = report.speed.upload_mbps;
    
    document.getElementById("downloadVal").innerText = dl.toFixed(1);
    document.getElementById("uploadVal").innerText = ul.toFixed(1);
    
    // Animate gauges (Download and Upload scale from 0 to 500 Mbps max for scaling percent)
    const dlPercent = Math.min(100, Math.round((dl / 500) * 100));
    const ulPercent = Math.min(100, Math.round((ul / 500) * 100));
    
    document.getElementById("downloadGauge").style.setProperty("--percent", dlPercent);
    document.getElementById("uploadGauge").style.setProperty("--percent", ulPercent);
    
    // Update badge status
    const speedBadge = document.getElementById("speedtestStatus");
    speedBadge.innerText = isAfter ? "Optimized" : "Default";
    speedBadge.className = isAfter ? "badge success" : "badge";
    
    // 2. Update Latency, Jitter, Packet Loss
    document.getElementById("pingVal").innerText = `${report.speed.ping_ms || report.latency.avg} ms`;
    document.getElementById("jitterVal").innerText = `${report.latency.jitter} ms`;
    document.getElementById("lossVal").innerText = `${report.latency.loss_pct} %`;
    
    // 3. Render DNS Tables
    renderDnsTable(report.dns);
    
    // 4. Render Wifi clutter cleaner
    renderWifiCleaner(report.active_profile, report.stale_profiles, report.all_profiles_count);
    
    // 5. Render Bandwidth hogs list
    renderHogsList(report.bandwidth_hogs);
    
    // 6. Update MTU
    document.getElementById("mtuVal").innerText = report.mtu;
    const mtuStatus = document.getElementById("mtuStatus");
    if (report.mtu === 1500) {
        mtuStatus.innerText = "Standard";
        mtuStatus.className = "mtu-status text-emerald";
    } else {
        mtuStatus.innerText = "Optimized";
        mtuStatus.className = "mtu-status text-cyan";
    }
}

// DNS Table rendering
function renderDnsTable(dnsData) {
    const tableBody = document.getElementById("dnsTableBody");
    tableBody.innerHTML = "";
    
    if (!dnsData || Object.keys(dnsData).length === 0) {
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No benchmark data. Click "Scan & Diagnose" to begin.</td></tr>`;
        return;
    }
    
    // Sort dns servers by latency (avg_ms)
    const sortedDns = Object.entries(dnsData).sort((a, b) => a[1].avg_ms - b[1].avg_ms);
    const fastestDnsIp = sortedDns[0][0];
    
    sortedDns.forEach(([ip, info]) => {
        const isFastest = ip === fastestDnsIp && info.avg_ms !== 9999;
        const speedClass = isFastest ? "text-emerald font-weight-bold" : (info.avg_ms > 200 ? "text-red" : "text-white");
        const speedText = info.avg_ms === 9999 ? "Timed Out" : `${info.avg_ms} ms`;
        
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>
                <div class="font-weight-bold">${info.name}</div>
                <div class="text-muted text-sm">${ip}</div>
            </td>
            <td class="${speedClass}">
                ${speedText} ${isFastest ? '<span class="badge success text-sm py-0">Fastest</span>' : ""}
            </td>
            <td>
                <span class="status-dot ${info.status === 'Online' ? 'success' : 'warning'}"></span>
                <span class="text-sm">${info.status}</span>
            </td>
            <td>
                <button class="btn btn-secondary btn-xs" onclick="setSystemDns('${ip}')">
                    <i class="fa-solid fa-square-rss"></i> Apply
                </button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

// Wifi Profiles Cleaner rendering
function renderWifiCleaner(activeSsid, staleProfiles, totalCount) {
    const wifiList = document.getElementById("wifiList");
    wifiList.innerHTML = "";
    
    document.getElementById("wifiCountLabel").innerText = `Total Saved Profiles: ${totalCount}`;
    
    const staleWifiBadge = document.getElementById("staleWifiBadge");
    staleWifiBadge.innerText = `${staleProfiles.length} Stale`;
    
    if (staleProfiles.length > 0) {
        staleWifiBadge.className = "badge warning";
        document.getElementById("btnCleanAllWifi").style.display = "inline-flex";
    } else {
        staleWifiBadge.className = "badge";
        document.getElementById("btnCleanAllWifi").style.display = "none";
    }
    
    // Add current SSID if connected
    if (activeSsid && activeSsid !== "Disconnected") {
        const activeItem = document.createElement("div");
        activeItem.className = "wifi-item";
        activeItem.innerHTML = `
            <div class="wifi-item-details">
                <i class="fa-solid fa-wifi text-emerald"></i>
                <div>
                    <span class="wifi-name text-emerald">${activeSsid}</span>
                    <span class="text-muted text-sm block">Current Connection</span>
                </div>
            </div>
            <span class="badge success text-sm">Active</span>
        `;
        wifiList.appendChild(activeItem);
    }
    
    // Add stale profiles
    if (staleProfiles.length === 0) {
        if (!activeSsid || activeSsid === "Disconnected") {
            wifiList.innerHTML = `<div class="text-center text-muted py-4">No Wi-Fi profiles found.</div>`;
        }
        return;
    }
    
    staleProfiles.forEach(profile => {
        const item = document.createElement("div");
        item.className = "wifi-item stale";
        item.innerHTML = `
            <div class="wifi-item-details">
                <i class="fa-solid fa-triangle-exclamation text-gold"></i>
                <div>
                    <span class="wifi-name">${profile}</span>
                    <span class="text-muted text-sm block">Historical Stale Profile</span>
                </div>
            </div>
            <button class="btn-icon" onclick="deleteWifiProfile('${profile}')" title="Clean profile">
                <i class="fa-regular fa-trash-can text-red"></i>
            </button>
        `;
        wifiList.appendChild(item);
    });
}

// Bandwidth Hogs list rendering
function renderHogsList(hogs) {
    const hogsList = document.getElementById("hogsList");
    hogsList.innerHTML = "";
    
    const hogsBadge = document.getElementById("hogsBadge");
    hogsBadge.innerText = `${hogs.length} Hogs`;
    
    if (hogs.length > 0) {
        hogsBadge.className = "badge danger";
    } else {
        hogsBadge.className = "badge";
    }
    
    if (hogs.length === 0) {
        hogsList.innerHTML = `<div class="text-center text-muted py-5"><i class="fa-regular fa-circle-check text-emerald" style="font-size: 1.5rem;"></i><br><span class="mt-2 block">No background network hogs detected!</span></div>`;
        return;
    }
    
    hogs.forEach(hog => {
        const item = document.createElement("div");
        item.className = "hog-item";
        item.innerHTML = `
            <div class="hog-info">
                <span class="hog-name">${hog.name}</span>
                <span class="hog-pid">PID: ${hog.pid} &bull; Wasting Bandwidth</span>
            </div>
            <button class="btn btn-secondary btn-xs text-red" onclick="killProcess(${hog.pid}, '${hog.name}')">
                <i class="fa-solid fa-ban"></i> Terminate
            </button>
        `;
        hogsList.appendChild(item);
    });
}

// Compare reports data
async function checkAndRenderCompare() {
    try {
        const res = await fetch(`${API_BASE}/api/compare`);
        if (!res.ok) return;
        const data = await res.json();
        
        if (data.ready) {
            document.getElementById("compareSection").style.display = "flex";
            
            const before = data.before;
            const after = data.after;
            
            // 1. Download
            document.getElementById("compDlBefore").innerText = before.speed.download_mbps.toFixed(1);
            document.getElementById("compDlAfter").innerText = after.speed.download_mbps.toFixed(1);
            const dlDiff = after.speed.download_mbps - before.speed.download_mbps;
            const dlPct = before.speed.download_mbps > 0 ? (dlDiff / before.speed.download_mbps) * 100 : 0;
            const dlImpLabel = document.getElementById("compDlImp");
            if (dlDiff > 0) {
                dlImpLabel.innerText = `+${dlPct.toFixed(1)}% Speedup`;
                dlImpLabel.className = "compare-improvement positive";
            } else {
                dlImpLabel.innerText = `${dlPct.toFixed(1)}% Variation`;
                dlImpLabel.className = "compare-improvement text-muted";
            }
            
            // 2. Upload
            document.getElementById("compUlBefore").innerText = before.speed.upload_mbps.toFixed(1);
            document.getElementById("compUlAfter").innerText = after.speed.upload_mbps.toFixed(1);
            const ulDiff = after.speed.upload_mbps - before.speed.upload_mbps;
            const ulPct = before.speed.upload_mbps > 0 ? (ulDiff / before.speed.upload_mbps) * 100 : 0;
            const ulImpLabel = document.getElementById("compUlImp");
            if (ulDiff > 0) {
                ulImpLabel.innerText = `+${ulPct.toFixed(1)}% Speedup`;
                ulImpLabel.className = "compare-improvement positive";
            } else {
                ulImpLabel.innerText = `${ulPct.toFixed(1)}% Variation`;
                ulImpLabel.className = "compare-improvement text-muted";
            }
            
            // 3. Ping
            const pBefore = before.speed.ping_ms || before.latency.avg;
            const pAfter = after.speed.ping_ms || after.latency.avg;
            document.getElementById("compPingBefore").innerText = `${pBefore} ms`;
            document.getElementById("compPingAfter").innerText = `${pAfter} ms`;
            const pingDiff = pBefore - pAfter;
            const pingImpLabel = document.getElementById("compPingImp");
            if (pingDiff > 0) {
                pingImpLabel.innerText = `-${pingDiff.toFixed(1)} ms Latency Reduced`;
                pingImpLabel.className = "compare-improvement positive";
            } else {
                pingImpLabel.innerText = `+${Math.abs(pingDiff).toFixed(1)} ms Change`;
                pingImpLabel.className = "compare-improvement text-red bg-opacity-red";
            }
            
            // 4. Summaries
            const cleanedCount = before.all_profiles_count - after.all_profiles_count;
            document.getElementById("compWifiCleaned").innerText = `${Math.max(0, cleanedCount)} profiles`;
            
            const llmnrStatus = document.getElementById("compLlmnrStatus");
            if (after.mdns.llmnr === "Disabled") {
                llmnrStatus.innerText = "Safely Disabled";
                llmnrStatus.className = "val text-emerald font-weight-bold";
            } else {
                llmnrStatus.innerText = "Enabled (Unoptimized)";
                llmnrStatus.className = "val text-gold font-weight-bold";
            }
        } else {
            document.getElementById("compareSection").style.display = "none";
        }
    } catch (err) {
        console.error("Error comparing logs:", err);
    }
}

// API - Set system DNS
async function setSystemDns(ip) {
    try {
        logToTerminal(`[System] Attempting to apply system DNS settings to: ${ip}...`);
        const res = await fetch(`${API_BASE}/api/set-dns`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ dns_ip: ip })
        });
        const data = await res.json();
        
        if (data.success) {
            logToTerminal(`[+] Success: ${data.message}`);
            showToast("DNS Updated", `Switched primary DNS to ${ip} successfully.`, "success");
            await fetchSystemStatus();
        } else if (data.need_admin) {
            showToast("Privileges Required", "DNS change requires Administrator privileges.", "warning");
            showAdminModal(data.powershell_command);
        } else {
            logToTerminal(`[!] DNS update error: ${data.message}`);
            showToast("DNS Update Failed", data.message, "danger");
        }
    } catch (err) {
        logToTerminal(`[!] Set DNS request failed: ${err.message}`);
        showToast("Error", `Set DNS request error: ${err.message}`, "danger");
    }
}

// API - Set MTU size
async function setOptimalMtu() {
    const mtuVal = parseInt(document.getElementById("mtuVal").innerText) || 1500;
    try {
        logToTerminal(`[System] Sending request to configure subinterface MTU to ${mtuVal}...`);
        const res = await fetch(`${API_BASE}/api/set-mtu`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mtu: mtuVal })
        });
        const data = await res.json();
        
        if (data.success) {
            logToTerminal(`[+] Success: ${data.message}`);
            showToast("MTU Size Set", `Subinterface MTU configured to ${mtuVal} bytes.`, "success");
            await loadExistingReports();
        } else if (data.need_admin) {
            showToast("Privileges Required", "MTU adjustment requires Administrator privileges.", "warning");
            showAdminModal(data.powershell_command);
        } else {
            logToTerminal(`[!] MTU update error: ${data.message}`);
            showToast("MTU Update Failed", data.message, "danger");
        }
    } catch (err) {
        logToTerminal(`[!] Set MTU request failed: ${err.message}`);
        showToast("Error", `Set MTU request error: ${err.message}`, "danger");
    }
}

// API - Delete Wifi profile
async function deleteWifiProfile(profileName) {
    if (!confirm(`Are you sure you want to clean saved Wi-Fi profile '${profileName}'?`)) return;
    try {
        logToTerminal(`[System] Purging historical Wi-Fi profile: '${profileName}'...`);
        const res = await fetch(`${API_BASE}/api/delete-profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ profile: profileName })
        });
        const data = await res.json();
        if (data.success) {
            logToTerminal(`[+] Cleaned profile: '${profileName}'.`);
            showToast("Profile Removed", `Cleaned stale profile '${profileName}' successfully.`, "success");
            
            // Fast reload stale profile status
            await fetchSystemStatus();
            const checkRes = await fetch(`${API_BASE}/api/report-data`);
            if (checkRes.ok) {
                const r = await checkRes.json();
                r.stale_profiles = r.stale_profiles.filter(p => p !== profileName);
                r.all_profiles_count = Math.max(1, r.all_profiles_count - 1);
                updateUiWithReport(r, false);
            }
        } else {
            logToTerminal(`[!] Profile cleaning error: ${data.message}`);
            showToast("Removal Failed", data.message, "danger");
        }
    } catch (err) {
        logToTerminal(`[!] Request error: ${err.message}`);
    }
}

// Clean all stale Wi-Fi networks in batch
async function deleteAllStaleWifi() {
    if (!confirm("Would you like to purge all historical Wi-Fi networks to speed up connection profile scans?")) return;
    logToTerminal("[System] Initializing batch cleanup of stale Wi-Fi networks...");
    showToast("Batch Clean Active", "Cleaning up all stale profiles...", "info");
    
    const resReport = await fetch(`${API_BASE}/api/report-data`);
    if (!resReport.ok) return;
    const r = await resReport.json();
    const stale = r.stale_profiles || [];
    
    let cleaned = 0;
    for (const p of stale) {
        const res = await fetch(`${API_BASE}/api/delete-profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ profile: p })
        });
        const data = await res.json();
        if (data.success) cleaned++;
    }
    logToTerminal(`[+] Finished: Cleaned ${cleaned}/${stale.length} stale profiles.`);
    showToast("Batch Cleanup Complete", `Removed ${cleaned} profiles successfully.`, "success");
    await init();
}

// API - Kill noise background process
async function killProcess(pid, name) {
    if (!confirm(`Are you sure you want to terminate background process '${name}' (PID: ${pid})?`)) return;
    try {
        logToTerminal(`[System] Sending request to terminate suspect process PID ${pid}...`);
        const res = await fetch(`${API_BASE}/api/terminate-process`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pid: pid, name: name })
        });
        const data = await res.json();
        if (data.success) {
            logToTerminal(`[+] Success: ${data.message}`);
            showToast("Process Terminated", `Killed background process ${name}.`, "success");
            
            // Filter it out from the current UI list
            const resReport = await fetch(`${API_BASE}/api/report-data`);
            if (resReport.ok) {
                const r = await resReport.json();
                r.bandwidth_hogs = r.bandwidth_hogs.filter(h => h.pid !== pid);
                updateUiWithReport(r, false);
            }
        } else {
            logToTerminal(`[!] Process termination failed: ${data.message}`);
            showToast("Termination Failed", data.message, "danger");
        }
    } catch (err) {
        logToTerminal(`[!] Request error: ${err.message}`);
    }
}

// Reset Engine status (emergency log wipe & restart state)
async function resetEngine() {
    if (!confirm("Are you sure you want to clear log history and reset OptiNet UI state?")) return;
    try {
        const res = await fetch(`${API_BASE}/api/reset`, { method: "POST" });
        if (res.ok) {
            const terminal = document.getElementById("terminalLog");
            terminal.innerHTML = "[System Info] Logs cleared. OptiNet is ready to scan!";
            document.getElementById("engineStatusIndicator").innerText = "Idle / Ready";
            showToast("UI State Reset", "Logs and status reset successfully.", "info");
            await init();
        }
    } catch (err) {
        console.error(err);
    }
}

// ADMIN MODAL CONTROLS
function showAdminModal(command) {
    document.getElementById("adminCodeText").innerText = command;
    document.getElementById("adminModal").classList.add("active");
}

// Close Admin modal
function closeAdminModal() {
    document.getElementById("adminModal").classList.remove("active");
}

// Copy Admin command
function copyAdminCommand() {
    const text = document.getElementById("adminCodeText").innerText;
    navigator.clipboard.writeText(text).then(() => {
        logToTerminal("[+] Copied PowerShell Admin command to clipboard.");
        showToast("Command Copied", "Paste the command in your elevated PowerShell window.", "success");
        closeAdminModal();
    }).catch(err => {
        console.error("Copy error:", err);
    });
}

// Parallax 3D Card Tilt Mouse Tracker
function initCardTilt() {
    const cards = document.querySelectorAll(".card-panel");
    cards.forEach(card => {
        card.addEventListener("mousemove", e => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Centralize mouse coordinate percentages
            const xc = (x / rect.width) - 0.5;
            const yc = (y / rect.height) - 0.5;
            
            // Calculate dynamic rotation angles (maximum 8 degrees)
            const rx = -yc * 12;
            const ry = xc * 12;
            
            card.style.setProperty("--rx", `${rx}deg`);
            card.style.setProperty("--ry", `${ry}deg`);
        });
        
        card.addEventListener("mouseleave", () => {
            // Smoothly ease back to flat on mouse leave
            card.style.setProperty("--rx", "0deg");
            card.style.setProperty("--ry", "0deg");
        });
    });
}
