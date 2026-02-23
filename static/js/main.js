/**
 * Scraper API — Frontend Scripts
 * Minimal JS: Toasts, Copy-to-Clipboard, Chart.js
 */

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================

function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const icons = {
        success: `<svg class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
        error:   `<svg class="w-5 h-5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
        info:    `<svg class="w-5 h-5 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    };

    const bgMap = {
        success: "bg-white border-emerald-200",
        error:   "bg-white border-red-200",
        info:    "bg-white border-indigo-200",
    };

    const toast = document.createElement("div");
    toast.className = `pointer-events-auto flex items-start gap-3 px-4 py-3.5 rounded-xl shadow-lg border ${bgMap[type] || bgMap.info} toast-enter`;
    toast.innerHTML = `
        ${icons[type] || icons.info}
        <p class="text-sm text-slate-700 leading-snug flex-1">${message}</p>
        <button onclick="this.closest('.toast-enter, .toast-exit').remove()" class="p-0.5 rounded text-slate-400 hover:text-slate-600 shrink-0">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
    `;

    container.appendChild(toast);

    // Auto-dismiss after 5s
    setTimeout(() => {
        toast.classList.remove("toast-enter");
        toast.classList.add("toast-exit");
        setTimeout(() => toast.remove(), 350);
    }, 5000);
}

// ============================================================
// HTMX EVENT LISTENERS
// ============================================================

// Listen for custom HX-Trigger events from the server
document.body.addEventListener("showToast", function (evt) {
    if (evt.detail) {
        const message = evt.detail.message || "Operation completed";
        const type = evt.detail.type || "info";
        showToast(message, type);
    }
});

// Handle HTMX errors (network errors, timeouts, etc.)
document.body.addEventListener("htmx:responseError", function (evt) {
    const status = evt.detail.xhr?.status;
    if (status === 429) {
        showToast("Rate limit exceeded. Please wait a moment.", "error");
    } else if (status >= 500) {
        showToast("Server error. Please try again later.", "error");
    } else {
        showToast("Request failed. Check the URL and try again.", "error");
    }
});

document.body.addEventListener("htmx:sendError", function () {
    showToast("Network error. Check your connection.", "error");
});

// ============================================================
// COPY TO CLIPBOARD
// ============================================================

/**
 * Legacy copy — targets #result-text
 */
function copyResult() {
    copyToClipboard("result-text");
}

/**
 * Generic copy — copies the text content of any element by ID.
 * Used by the Alpine.js tabbed result card for JSON / HTML tabs.
 */
function copyToClipboard(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const text = el.innerText || el.textContent || el.value;
    navigator.clipboard.writeText(text).then(() => {
        showToast("Copied to clipboard!", "success");
    }).catch(() => {
        // Fallback for older browsers
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        showToast("Copied to clipboard!", "success");
    });
}

// ============================================================
// CHART.JS — Analytics Page
// ============================================================

function initCharts() {
    const data = window.statsData;
    if (!data) return;

    // --- Doughnut Chart: Requests per Endpoint ---
    const endpointCtx = document.getElementById("endpointChart");
    if (endpointCtx && data.endpoints) {
        const endpoints = data.endpoints;
        const labels = Object.keys(endpoints);
        const values = Object.values(endpoints);

        const colors = [
            "rgba(99, 102, 241, 0.85)",   // indigo
            "rgba(168, 85, 247, 0.85)",    // purple
            "rgba(245, 158, 11, 0.85)",    // amber
            "rgba(16, 185, 129, 0.85)",    // emerald
            "rgba(239, 68, 68, 0.85)",     // red
            "rgba(59, 130, 246, 0.85)",    // blue
        ];

        new Chart(endpointCtx, {
            type: "doughnut",
            data: {
                labels: labels.map(l => l.charAt(0).toUpperCase() + l.slice(1).replace("_", " ")),
                datasets: [{
                    data: values,
                    backgroundColor: colors.slice(0, labels.length),
                    borderWidth: 0,
                    hoverOffset: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 8,
                            font: { size: 12, family: "Inter, system-ui, sans-serif" },
                        },
                    },
                },
            },
        });
    }

    // --- Bar Chart: Top Domains ---
    const domainsCtx = document.getElementById("domainsChart");
    if (domainsCtx && data.top_domains && data.top_domains.length > 0) {
        const domainLabels = data.top_domains.map(d => d[0]);
        const domainValues = data.top_domains.map(d => d[1]);

        new Chart(domainsCtx, {
            type: "bar",
            data: {
                labels: domainLabels,
                datasets: [{
                    label: "Requests",
                    data: domainValues,
                    backgroundColor: "rgba(99, 102, 241, 0.15)",
                    borderColor: "rgba(99, 102, 241, 0.8)",
                    borderWidth: 1.5,
                    borderRadius: 8,
                    borderSkipped: false,
                    barPercentage: 0.6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: "y",
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: "rgba(0,0,0,0.04)", drawBorder: false },
                        ticks: {
                            font: { size: 11, family: "Inter, system-ui, sans-serif" },
                            precision: 0,
                        },
                    },
                    y: {
                        grid: { display: false },
                        ticks: {
                            font: { size: 12, family: "'SF Mono', 'Fira Code', monospace" },
                            color: "#475569",
                        },
                    },
                },
            },
        });
    } else if (domainsCtx) {
        // Empty state for domains chart
        domainsCtx.parentElement.innerHTML = `
            <div class="h-64 flex items-center justify-center">
                <p class="text-sm text-slate-400">No domain data available yet</p>
            </div>`;
    }
}

// ============================================================
// INIT ON PAGE LOAD
// ============================================================

document.addEventListener("DOMContentLoaded", function () {
    // Initialize charts if we're on the stats page
    if (window.statsData) {
        initCharts();
    }
});
