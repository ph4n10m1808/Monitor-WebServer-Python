let lastUpdateTime = null;
let updateInterval = 3000; // 3 seconds for stats
let isUpdating = false;

// Logs pagination
let currentLogPage = 1;
let logPageSize = 50;
let autoRefreshLogs = true;
let logsUpdateInterval = null;
let currentFilters = {};
let logsUpdateIntervalTime = 30000; // 30 seconds for logs auto-refresh

async function syncLogs() {
  try {
    const response = await fetch('/api/sync');
    const result = await response.json();
    if (result.success && result.count > 0) {
      console.log(`Synced ${result.count} new log entries`);
      return true;
    }
    return false;
  } catch (error) {
    console.error('Error syncing logs:', error);
    return false;
  }
}

async function fetchStats(timestamp = null) {
  let url;
  // if (timestamp) {
  //   // Fetch from specific timestamp
  //   url = `/api/stats/since/${timestamp}`;
  // } else if (lastUpdateTime) {
  //   // Fetch from last update time
  //   url = `/api/stats/since/${lastUpdateTime}`;
  // } else {
  //   // Initial fetch - get all stats
    url = "/api/stats";
  // }
  
  try {
    const r = await fetch(url);
    if (!r.ok) {
      throw new Error(`HTTP error! status: ${r.status}`);
    }
    const data = await r.json();
    console.log('Fetched stats from:', url, data);
    return data;
  } catch (error) {
    console.error('Error fetching stats:', error);
    throw error;
  }
}

async function fetchLogs(page = 1, limit = 50, filters = {}) {
  const params = new URLSearchParams({
    page: page.toString(),
    limit: limit.toString()
  });
  
  // Add filters to params
  if (filters.ip) params.append('ip', filters.ip);
  if (filters.ident) params.append('ident', filters.ident);
  if (filters.user) params.append('user', filters.user);
  if (filters.method) params.append('method', filters.method);
  if (filters.path) params.append('path', filters.path);
  if (filters.status) params.append('status', filters.status);
  if (filters.size_min) params.append('size_min', filters.size_min);
  if (filters.size_max) params.append('size_max', filters.size_max);
  if (filters.referer) params.append('referer', filters.referer);
  if (filters.agent) params.append('agent', filters.agent);
  
  const url = `/api/logs?${params.toString()}`;
  const r = await fetch(url);
  return r.json();
}

function formatTime(timeString) {
  if (!timeString) return '-';
  try {
    const date = new Date(timeString);
    return date.toLocaleString();
  } catch {
    return timeString;
  }
}

function getStatusClass(status) {
  if (!status) return '';
  const code = Math.floor(status / 100);
  return `status-${code}xx`;
}

function getMethodClass(method) {
  if (!method) return '';
  return `method-${method.toLowerCase()}`;
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '-';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function renderLogs(logsData) {
  const tbody = document.getElementById('logsTableBody');
  if (!tbody) return;
  
  if (!logsData.logs || logsData.logs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="loading-cell">
          <span>No log entries found</span>
        </td>
      </tr>
    `;
    return;
  }
  
  tbody.innerHTML = logsData.logs.map(log => {
    const statusClass = getStatusClass(log.status);
    const methodClass = getMethodClass(log.method);
    
    return `
      <tr>
        <td class="log-time">${formatTime(log.time)}</td>
        <td class="log-ip">${log.ip || '-'}</td>
        <td class="log-ident">${log.ident || '-'}</td>
        <td class="log-user">${log.user || '-'}</td>
        <td>
          <span class="log-method ${methodClass}">${log.method || '-'}</span>
        </td>
        <td class="log-path" title="${log.path || '-'}">${log.path || '-'}</td>
        <td>
          <span class="log-status ${statusClass}">${log.status || '-'}</span>
        </td>
        <td>${formatBytes(log.size)}</td>
        <td class="log-referer" title="${log.referer || '-'}">${log.referer || '-'}</td>
        <td class="log-agent" title="${log.agent || '-'}">${log.agent || '-'}</td>
      </tr>
    `;
  }).join('');
  
  // Update pagination
  updatePagination(logsData);
  
  // Update active filters display
  updateActiveFilters(logsData.filters || {});
}

function updateActiveFilters(filters) {
  const container = document.getElementById('activeFilters');
  if (!container) return;
  
  currentFilters = filters;
  
  // Clear existing badges
  container.innerHTML = '';
  
  // Add badges for active filters
  if (filters.ip) {
    container.innerHTML += `<span class="filter-badge">IP: ${filters.ip} <span class="remove" onclick="removeFilter('ip')">×</span></span>`;
  }
  if (filters.ident) {
    container.innerHTML += `<span class="filter-badge">Ident: ${filters.ident} <span class="remove" onclick="removeFilter('ident')">×</span></span>`;
  }
  if (filters.user) {
    container.innerHTML += `<span class="filter-badge">User: ${filters.user} <span class="remove" onclick="removeFilter('user')">×</span></span>`;
  }
  if (filters.method) {
    container.innerHTML += `<span class="filter-badge">Method: ${filters.method} <span class="remove" onclick="removeFilter('method')">×</span></span>`;
  }
  if (filters.path) {
    container.innerHTML += `<span class="filter-badge">Path: ${filters.path} <span class="remove" onclick="removeFilter('path')">×</span></span>`;
  }
  if (filters.status) {
    container.innerHTML += `<span class="filter-badge">Status: ${filters.status} <span class="remove" onclick="removeFilter('status')">×</span></span>`;
  }
  if (filters.size_min || filters.size_max) {
    const sizeText = filters.size_min && filters.size_max 
      ? `${filters.size_min} - ${filters.size_max}`
      : filters.size_min 
        ? `≥ ${filters.size_min}`
        : `≤ ${filters.size_max}`;
    container.innerHTML += `<span class="filter-badge">Size: ${sizeText} <span class="remove" onclick="removeFilter('size')">×</span></span>`;
  }
  if (filters.referer) {
    container.innerHTML += `<span class="filter-badge">Referer: ${filters.referer} <span class="remove" onclick="removeFilter('referer')">×</span></span>`;
  }
  if (filters.agent) {
    container.innerHTML += `<span class="filter-badge">Agent: ${filters.agent} <span class="remove" onclick="removeFilter('agent')">×</span></span>`;
  }
}

function removeFilter(filterName) {
  if (filterName === 'size') {
    document.getElementById('searchSizeMin').value = '';
    document.getElementById('searchSizeMax').value = '';
  } else {
    const field = document.getElementById(`search${filterName.charAt(0).toUpperCase() + filterName.slice(1)}`);
    if (field) field.value = '';
  }
  
  // Reapply search
  handleSearch(new Event('submit'));
}

function updatePagination(logsData) {
  const pageInfo = document.getElementById('pageInfo');
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');
  
  if (pageInfo) {
    pageInfo.textContent = `Page ${logsData.page} of ${logsData.pages || 1} (Total: ${logsData.total})`;
  }
  
  if (prevBtn) {
    prevBtn.disabled = logsData.page <= 1;
    prevBtn.style.opacity = logsData.page <= 1 ? '0.5' : '1';
    prevBtn.style.cursor = logsData.page <= 1 ? 'not-allowed' : 'pointer';
  }
  
  if (nextBtn) {
    nextBtn.disabled = logsData.page >= (logsData.pages || 1);
    nextBtn.style.opacity = logsData.page >= (logsData.pages || 1) ? '0.5' : '1';
    nextBtn.style.cursor = logsData.page >= (logsData.pages || 1) ? 'not-allowed' : 'pointer';
  }
}

function handleSearch(event) {
  event.preventDefault();
  
  const formData = new FormData(event.target);
  const filters = {
    ip: formData.get('ip')?.trim() || '',
    ident: formData.get('ident')?.trim() || '',
    user: formData.get('user')?.trim() || '',
    method: formData.get('method')?.trim() || '',
    path: formData.get('path')?.trim() || '',
    status: formData.get('status')?.trim() || '',
    size_min: formData.get('size_min')?.trim() || '',
    size_max: formData.get('size_max')?.trim() || '',
    referer: formData.get('referer')?.trim() || '',
    agent: formData.get('agent')?.trim() || ''
  };
  
  // Remove empty filters
  Object.keys(filters).forEach(key => {
    if (!filters[key]) delete filters[key];
  });
  
  currentFilters = filters;
  currentLogPage = 1; // Reset to first page
  loadLogs(1, logPageSize, filters);
}

function clearSearch() {
  document.getElementById('searchForm').reset();
  currentFilters = {};
  currentLogPage = 1;
  loadLogs();
}

async function loadLogs(page = null, limit = null, filters = null) {
  if (page !== null) {
    currentLogPage = page;
  }
  if (limit !== null) {
    logPageSize = limit;
  }
  if (filters !== null) {
    currentFilters = filters;
  }
  
  try {
    const logsData = await fetchLogs(currentLogPage, logPageSize, currentFilters);
    renderLogs(logsData);
  } catch (error) {
    console.error('Error loading logs:', error);
    const tbody = document.getElementById('logsTableBody');
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="loading-cell" style="color: var(--danger);">
            <span>Error loading logs: ${error.message}</span>
          </td>
        </tr>
      `;
    }
  }
}

function changePage(delta) {
  const newPage = currentLogPage + delta;
  if (newPage >= 1) {
    loadLogs(newPage);
  }
}

function toggleAutoRefresh() {
  autoRefreshLogs = !autoRefreshLogs;
  const text = document.getElementById('autoRefreshText');
  if (text) {
    text.textContent = autoRefreshLogs ? '⏸️ Pause Auto-refresh' : '▶️ Resume Auto-refresh';
  }
  
  if (autoRefreshLogs) {
    startLogsAutoRefresh();
  } else {
    stopLogsAutoRefresh();
  }
}

function startLogsAutoRefresh() {
  if (logsUpdateInterval) {
    clearInterval(logsUpdateInterval);
  }
//  // Auto-refresh logs every 30 seconds
//  logsUpdateInterval = setInterval(async () => {
//    if (autoRefreshLogs) {
//      // Sync logs from file first, then reload
//      await syncLogs();
//      loadLogs(); // Reload current page with current filters
//    }
//  }, logsUpdateIntervalTime);
}

function stopLogsAutoRefresh() {
  if (logsUpdateInterval) {
    clearInterval(logsUpdateInterval);
  }
}

function renderRPM(labels, data) {
  console.log('renderRPM called with labels:', labels, 'data:', data);
  
  // Check if Chart.js is loaded
  if (typeof Chart === 'undefined') {
    console.error('Chart.js is not loaded!');
    return;
  }
  
  const ctx = document.getElementById("rpmChart");
  if (!ctx) {
    console.error('rpmChart element not found!');
    return;
  }
  
  const chartCtx = ctx.getContext("2d");
  if (!chartCtx) {
    console.error('Could not get 2d context from canvas!');
    return;
  }
  
  // Ensure labels and data are arrays
  const safeLabels = Array.isArray(labels) && labels.length > 0 ? labels : ['No data'];
  const safeData = Array.isArray(data) && data.length > 0 ? data : [0];
  
  console.log('Safe labels:', safeLabels, 'Safe data:', safeData);
  
  // Always destroy existing chart to ensure clean state
  if (window.rpmChart) {
    try {
      window.rpmChart.destroy();
    } catch (e) {
      console.warn('Error destroying existing chart:', e);
    }
    window.rpmChart = null;
  }
  
  // Create new chart
  try {
    console.log('Creating new RPM chart with Chart.js version:', Chart.version || 'unknown');
    window.rpmChart = new Chart(chartCtx, {
      type: "line",
      data: {
        labels: safeLabels,
        datasets: [
          {
            label: "Requests per Minute",
            data: safeData,
            fill: true,
            borderColor: 'rgb(75, 192, 192)',
            backgroundColor: 'rgba(75, 192, 192, 0.2)',
            tension: 0.1,
            pointRadius: 4,
            pointHoverRadius: 6
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: {
          duration: 0
        },
        scales: {
          y: {
            beginAtZero: true,
            title: {
              display: true,
              text: 'Số lượng Request'
            },
            ticks: {
              stepSize: 1
            }
          },
          x: {
            title: {
              display: true,
              text: 'Thời gian (phút)'
            }
          }
        },
        plugins: {
          legend: {
            display: true,
            position: 'top'
          },
          tooltip: {
            mode: 'index',
            intersect: false,
            callbacks: {
              label: function(context) {
                return `Requests: ${context.parsed.y}`;
              }
            }
          }
        },
        interaction: {
          mode: 'nearest',
          axis: 'x',
          intersect: false
        }
      }
    });
    console.log('RPM chart created successfully');
  } catch (error) {
    console.error('Error creating RPM chart:', error);
    console.error('Error stack:', error.stack);
  }
}

function updateStatusIndicator(hasNewData) {
  const indicator = document.getElementById('statusIndicator');
  if (indicator) {
    const statusText = indicator.querySelector('.status-text');
    if (statusText) {
      statusText.textContent = hasNewData ? 'Live' : 'Idle';
    }
    indicator.className = hasNewData ? 'status-badge status-live' : 'status-badge status-idle';
  }
}

async function update() {
  if (isUpdating) return;
  isUpdating = true;
  
  try {
    const s = await fetchStats();
    const hasNewData = s.new_entries > 0 || !lastUpdateTime;
    
    if (s.latest_time) {
      lastUpdateTime = s.latest_time;
    }
    
    // Process and display stats data
    await processStatsData(s);
    
    updateStatusIndicator(hasNewData);
    
  } catch (error) {
    console.error('Error fetching stats:', error);
    // Hiển thị lỗi trên UI nếu cần
    const errorMsg = document.getElementById('errorMessage');
    if (errorMsg) {
      errorMsg.textContent = `Error loading stats: ${error.message}`;
      errorMsg.style.display = 'block';
    }
  } finally {
    isUpdating = false;
  }
}

// Function to load stats from a specific timestamp
async function loadStatsFromTimestamp(timestamp) {
  if (!timestamp) {
    console.error('Timestamp is required');
    return;
  }
  
  // Validate timestamp format
  try {
    new Date(timestamp);
  } catch (e) {
    console.error('Invalid timestamp format. Use ISO format like: 2025-12-13T02:00:03');
    return;
  }
  
  lastUpdateTime = null; // Reset to force fetch from specific timestamp
  const s = await fetchStats();
  
  // Update lastUpdateTime from response
  if (s.latest_time) {
    lastUpdateTime = s.latest_time;
  }
  
  // Process and display the data
  await processStatsData(s);
}

// Function to process and display stats data
async function processStatsData(s) {
  console.log('Processing stats data:', s);
  
  // Update RPM chart - Requests Per Minute
  const rpm = s.rpm || [];
  console.log('RPM data:', rpm, 'Length:', rpm.length);
  
  if (rpm && rpm.length > 0) {
    const labels = rpm.map((it) => {
      try {
        if (Array.isArray(it) && it.length >= 2) {
          const date = new Date(it[0]);
          if (isNaN(date.getTime())) {
            // If date parsing fails, try to format the string
            return it[0].substring(11, 16) || it[0]; // Extract HH:MM from ISO string
          }
          return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        }
        return it[0] || 'Unknown';
      } catch (err) {
        console.error('Error parsing RPM label:', it, err);
        return it[0] || 'Unknown';
      }
    });
    const data = rpm.map((it) => {
      if (Array.isArray(it) && it.length >= 2) {
        return parseInt(it[1]) || 0;
      }
      return 0;
    });
    console.log('RPM Labels:', labels);
    console.log('RPM Data:', data);
    renderRPM(labels, data);
  } else {
    console.warn('No RPM data available');
    renderRPM([], []);
  }
  
  // Update Top IPs (top 20)
  const topIpsElem = document.getElementById("topIps");
  if (!topIpsElem) {
    console.error('Element topIps not found!');
  } else {
    topIpsElem.innerHTML = "";
    const topIps = s.top_ips || [];
    console.log('Top IPs data:', topIps, 'Type:', typeof topIps, 'Is Array:', Array.isArray(topIps));
    
    if (Array.isArray(topIps) && topIps.length > 0) {
      topIps.forEach((it, index) => {
        try {
          const li = document.createElement("li");
          const ip = it[0] || it.ip || 'Unknown';
          const count = it[1] || it.count || 0;
          li.innerHTML = `<span class="ip">${ip}</span> <span class="count">${count}</span>`;
          topIpsElem.appendChild(li);
        } catch (err) {
          console.error('Error rendering IP item:', it, err);
        }
      });
    } else {
      const li = document.createElement("li");
      li.innerHTML = `<span style="color: #9ca3af;">No data available</span>`;
      topIpsElem.appendChild(li);
    }
  }
  
  // Update Top Paths (top 20)
  const topPathsElem = document.getElementById("topPaths");
  if (!topPathsElem) {
    console.error('Element topPaths not found!');
  } else {
    topPathsElem.innerHTML = "";
    const topPaths = s.top_paths || [];
    console.log('Top Paths data:', topPaths, 'Type:', typeof topPaths, 'Is Array:', Array.isArray(topPaths));
    
    if (Array.isArray(topPaths) && topPaths.length > 0) {
      topPaths.forEach((it, index) => {
        try {
          const li = document.createElement("li");
          const path = it[0] || it.path || 'Unknown';
          const count = it[1] || it.count || 0;
          li.innerHTML = `<span class="path">${path}</span> <span class="count">${count}</span>`;
          topPathsElem.appendChild(li);
        } catch (err) {
          console.error('Error rendering Path item:', it, err);
        }
      });
    } else {
      const li = document.createElement("li");
      li.innerHTML = `<span style="color: #9ca3af;">No data available</span>`;
      topPathsElem.appendChild(li);
    }
  }
  
  // Update Status Codes (dạng danh sách giống top IPs)
  const topStatusCodesElem = document.getElementById("topStatusCodes");
  if (!topStatusCodesElem) {
    console.error('Element topStatusCodes not found!');
  } else {
    topStatusCodesElem.innerHTML = "";
    const statusCodes = s.status || [];
    console.log('Status Codes data:', statusCodes, 'Type:', typeof statusCodes, 'Is Array:', Array.isArray(statusCodes));
    
    // Sắp xếp theo số lượng giảm dần
    const sortedStatusCodes = Array.isArray(statusCodes) ? [...statusCodes].sort((a, b) => {
      const countA = a[1] || a.count || 0;
      const countB = b[1] || b.count || 0;
      return countB - countA;
    }) : [];
    
    if (sortedStatusCodes.length > 0) {
      sortedStatusCodes.forEach((it, index) => {
        try {
          const li = document.createElement("li");
          const statusCode = it[0] || it.status || 'Unknown';
          const count = it[1] || it.count || 0;
          
          // Xác định màu sắc dựa trên status code
          const statusClass = getStatusClassForDisplay(statusCode);
          
          li.innerHTML = `<span class="status-code ${statusClass}">${statusCode}</span> <span class="count">${count}</span>`;
          topStatusCodesElem.appendChild(li);
        } catch (err) {
          console.error('Error rendering Status Code item:', it, err);
        }
      });
    } else {
      const li = document.createElement("li");
      li.innerHTML = `<span style="color: #9ca3af;">No data available</span>`;
      topStatusCodesElem.appendChild(li);
    }
  }
  
  // Update total entries
  const totalElem = document.getElementById('totalEntries');
  if (totalElem) {
    totalElem.textContent = s.total_entries || s.new_entries || 0;
  }
}

// Helper function to get status class for display
function getStatusClassForDisplay(statusCode) {
  if (!statusCode) return '';
  const code = parseInt(statusCode);
  if (isNaN(code)) return '';
  
  if (code >= 200 && code < 300) return 'status-2xx';
  if (code >= 300 && code < 400) return 'status-3xx';
  if (code >= 400 && code < 500) return 'status-4xx';
  if (code >= 500) return 'status-5xx';
  return '';
}

// Wait for Chart.js to be ready
function waitForChartJS(callback, maxAttempts = 50) {
  let attempts = 0;
  const checkChart = setInterval(() => {
    attempts++;
    if (typeof Chart !== 'undefined') {
      clearInterval(checkChart);
      console.log('Chart.js is ready!');
      callback();
    } else if (attempts >= maxAttempts) {
      clearInterval(checkChart);
      console.error('Chart.js failed to load after', maxAttempts, 'attempts');
      callback(); // Still try to proceed
    }
  }, 100);
}

// Tab Navigation Functions
function switchTab(tabName) {
  // Remove active class from all tabs and contents
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.remove('active');
  });
  
  // Add active class to selected tab and content
  const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
  const selectedContent = document.getElementById(`${tabName}Tab`);
  
  if (selectedBtn) {
    selectedBtn.classList.add('active');
  }
  if (selectedContent) {
    selectedContent.classList.add('active');
  }
  
  // If switching to dashboard, ensure charts are rendered
  if (tabName === 'dashboard' && typeof Chart !== 'undefined') {
    // Small delay to ensure DOM is ready
    setTimeout(() => {
      if (window.rpmChart) {
        window.rpmChart.resize();
      }
    }, 100);
  }
}

// Initial load
document.addEventListener('DOMContentLoaded', async function() {
  console.log('DOM Content Loaded');
  
  // Wait for Chart.js to be ready
  waitForChartJS(async () => {
    // Check for timestamp in URL parameter
    const urlParams = new URLSearchParams(window.location.search);
    const timestampParam = urlParams.get('since');
    const tabParam = urlParams.get('tab');
    
    // Set initial tab
    if (tabParam === 'search') {
      switchTab('search');
    } else {
      switchTab('dashboard');
    }
    
    // Sync logs from file when page loads
    await syncLogs();
    
    // Load stats from specific timestamp if provided, otherwise load normally
    if (timestampParam) {
      await loadStatsFromTimestamp(timestampParam);
    } else {
      update();
    }
    
    loadLogs();
    startLogsAutoRefresh();
    
    const statusText = document.getElementById('updateStatus');
    if (statusText) {
      setInterval(() => {
        const now = new Date();
        statusText.textContent = `Last update: ${now.toLocaleTimeString()}`;
      }, 1000);
    }
  });
});

// Set up polling interval for stats
setInterval(update, updateInterval);
