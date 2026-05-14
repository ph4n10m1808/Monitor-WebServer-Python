// ===== LOADING STATES & ERROR HANDLING =====

// Show loading overlay
function showLoading(containerId = null) {
  const container = containerId
    ? document.getElementById(containerId)
    : document.body;

  if (container) {
    let overlay = container.querySelector(".loading-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "loading-overlay";
      overlay.innerHTML = '<div class="spinner"></div>';
      container.style.position = "relative";
      container.appendChild(overlay);
    }
    requestAnimationFrame(() => overlay.classList.add("active"));
  }
}

// Hide loading overlay
function hideLoading(containerId = null) {
  const container = containerId
    ? document.getElementById(containerId)
    : document.body;

  if (container) {
    const overlay = container.querySelector(".loading-overlay");
    if (overlay) {
      overlay.classList.remove("active");
      setTimeout(() => overlay.remove(), 300);
    }
  }
}

// Show error message
function showError(message, containerId = null) {
  const container = containerId
    ? document.getElementById(containerId)
    : document.body;

  if (container) {
    const errorDiv = document.createElement("div");
    errorDiv.className = "error-message";
    errorDiv.innerHTML = `
      <span class="error-icon">⚠️</span>
      <span>${message}</span>
      <button class="retry-btn" onclick="location.reload()">Retry</button>
    `;
    container.insertBefore(errorDiv, container.firstChild);

    // Auto remove after 10 seconds
    setTimeout(() => errorDiv.remove(), 10000);
  }
}

// Create skeleton for charts
function createChartSkeleton(containerId) {
  const container = document.getElementById(containerId);
  if (container) {
    container.innerHTML = '<div class="skeleton skeleton-chart"></div>';
  }
}

// Create skeleton for list
function createListSkeleton(containerId, itemCount = 10) {
  const container = document.getElementById(containerId);
  if (container) {
    const items = Array(itemCount)
      .fill(0)
      .map(() => '<div class="skeleton skeleton-list-item"></div>')
      .join("");
    container.innerHTML = items;
  }
}

// Enhanced error handling for API calls
async function fetchWithRetry(url, options = {}, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`Attempt ${i + 1} failed:`, error);
      if (i === retries - 1) throw error;
      // Exponential backoff
      await new Promise((resolve) =>
        setTimeout(resolve, Math.pow(2, i) * 1000)
      );
    }
  }
}

// Replace existing fetch calls with retry logic
async function fetchStatsWithRetry() {
  try {
    showLoading("dashboardTab");
    const data = await fetchWithRetry("/api/stats");
    return data;
  } catch (error) {
    showError("Failed to load statistics. Please try again.", "dashboardTab");
    throw error;
  } finally {
    hideLoading("dashboardTab");
  }
}

async function fetchLogsWithRetry(page = 1, limit = 50, filters = {}) {
  try {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      ...filters,
    });

    const data = await fetchWithRetry(`/api/logs?${params}`);
    return data;
  } catch (error) {
    showError("Failed to load logs. Please try again.", "searchTab");
    throw error;
  }
}

// Export functions
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    showLoading,
    hideLoading,
    showError,
    createChartSkeleton,
    createListSkeleton,
    fetchWithRetry,
    fetchStatsWithRetry,
    fetchLogsWithRetry,
  };
}
