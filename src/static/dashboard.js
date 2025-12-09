async function fetchStats() {
  const r = await fetch("/api/stats");
  return r.json();
}

function renderRPM(labels, data) {
  const ctx = document.getElementById("rpmChart").getContext("2d");
  if (window.rpmChart) window.rpmChart.destroy();
  window.rpmChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Requests",
          data: data,
          fill: true,
        },
      ],
    },
  });
}

function renderStatus(labels, data) {
  const ctx = document.getElementById("statusChart").getContext("2d");
  if (window.statusChart) window.statusChart.destroy();
  window.statusChart = new Chart(ctx, {
    type: "pie",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Status",
          data: data,
        },
      ],
    },
  });
}

async function update() {
  const s = await fetchStats();
  const rpm = s.rpm;
  const labels = rpm.map((it) => it[0]);
  const data = rpm.map((it) => it[1]);
  renderRPM(labels, data);

  const topIpsElem = document.getElementById("topIps");
  topIpsElem.innerHTML = "";
  s.top_ips.forEach((it) => {
    const li = document.createElement("li");
    li.textContent = `${it[0]} — ${it[1]}`;
    topIpsElem.appendChild(li);
  });

  const topPathsElem = document.getElementById("topPaths");
  topPathsElem.innerHTML = "";
  s.top_paths.forEach((it) => {
    const li = document.createElement("li");
    li.textContent = `${it[0]} — ${it[1]}`;
    topPathsElem.appendChild(li);
  });

  const statusLabels = s.status.map((it) => it[0]);
  const statusData = s.status.map((it) => it[1]);
  renderStatus(statusLabels, statusData);
}

update();
setInterval(update, 5000);
