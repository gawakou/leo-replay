const SVG_NS = "http://www.w3.org/2000/svg";

let latest = {
  running: false,
  protocol: "UDP",
  rate_mbps: 0,
  delay_ms: 0,
  loss_pct: 0,
  state: "IDLE"
};

const packetLayer = document.getElementById("packetLayer");
let packets = [];
let lastSpawn = 0;

document.getElementById("startBtn").addEventListener("click", async () => {
  await fetch("/api/start", { method: "POST" });
});

document.getElementById("stopBtn").addEventListener("click", async () => {
  await fetch("/api/stop", { method: "POST" });
});

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    latest = await res.json();
    updateDashboard(latest);
  } catch (e) {
    console.error(e);
  }
}

function updateDashboard(s) {
  document.getElementById("target").textContent = s.target;
  document.getElementById("protocol").textContent = s.protocol;
  document.getElementById("timeSec").textContent = s.time_sec.toFixed ? s.time_sec.toFixed(1) : s.time_sec;
  document.getElementById("durationSec").textContent = s.duration_sec;
  document.getElementById("rate").textContent = s.rate_mbps;
  document.getElementById("delay").textContent = s.delay_ms;
  document.getElementById("loss").textContent = s.loss_pct;

  const state = s.state || "IDLE";
  const stateLower = state.toLowerCase();

  const badge = document.getElementById("statusBadge");
  badge.textContent = state;
  badge.className = "badge " + stateLower;

  const stateBox = document.getElementById("stateText");
  stateBox.textContent = state;
  stateBox.className = "state-box " + stateLower;

  const serverIf = document.getElementById("serverIf");
  if (state === "NORMAL") {
    serverIf.setAttribute("class", "if-normal");
  } else if (state === "DEGRADED") {
    serverIf.setAttribute("class", "if-degraded");
  } else if (state === "CONGESTED") {
    serverIf.setAttribute("class", "if-congested");
  } else {
    serverIf.setAttribute("class", "if-idle");
  }
}

function createPacket(protocol) {
  const isTcp = protocol === "TCP";
  let el;

  if (isTcp) {
    el = document.createElementNS(SVG_NS, "rect");
    el.setAttribute("width", "14");
    el.setAttribute("height", "14");
    el.setAttribute("rx", "2");
    el.setAttribute("class", "packet-tcp");
  } else {
    el = document.createElementNS(SVG_NS, "circle");
    el.setAttribute("r", "7");
    el.setAttribute("class", "packet-udp");
  }

  packetLayer.appendChild(el);

  return {
    el,
    x: 170,
    y: 120 + (Math.random() - 0.5) * 26,
    alive: true,
    protocol
  };
}

function setPacketPosition(p) {
  if (p.protocol === "TCP") {
    p.el.setAttribute("x", p.x - 7);
    p.el.setAttribute("y", p.y - 7);
  } else {
    p.el.setAttribute("cx", p.x);
    p.el.setAttribute("cy", p.y);
  }
}

function removePacket(p) {
  p.alive = false;
  if (p.el && p.el.parentNode) {
    p.el.parentNode.removeChild(p.el);
  }
}

function animatePackets(timestamp) {
  if (!lastSpawn) {
    lastSpawn = timestamp;
  }

  const running = latest.running === true;

  if (running) {
    const rate = Math.max(1, Number(latest.rate_mbps || 1));
    const delay = Math.max(0, Number(latest.delay_ms || 0));

    // rateが高いほど出現間隔を短くする
    const spawnInterval = Math.max(120, 700 - rate * 35);

    if (timestamp - lastSpawn > spawnInterval) {
      packets.push(createPacket(latest.protocol || "UDP"));
      lastSpawn = timestamp;
    }

    // delayが大きいほど遅くする
    const speed = Math.max(1.2, 5.5 - delay / 16.0);

    packets.forEach(p => {
      if (!p.alive) return;

      p.x += speed;

      // lossがある場合、ルータ後段で確率的に消す
      const loss = Number(latest.loss_pct || 0);
      if (p.x > 550 && p.x < 700 && Math.random() < loss / 1000.0) {
        removePacket(p);
        return;
      }

      if (p.x > 735) {
        removePacket(p);
        return;
      }

      setPacketPosition(p);
    });
  }

  packets = packets.filter(p => p.alive);

  requestAnimationFrame(animatePackets);
}

setInterval(fetchStatus, 1000);
fetchStatus();
requestAnimationFrame(animatePackets);
