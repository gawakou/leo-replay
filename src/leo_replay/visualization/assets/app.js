(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("bundle-data").textContent);
  const world = JSON.parse(document.getElementById("world-data").textContent);
  const frames = data.frames || [];
  let index = 0;
  let timer = null;

  const mapSvg = document.getElementById("mapSvg");
  const timelineSvg = document.getElementById("timelineSvg");
  const slider = document.getElementById("timeSlider");
  const playButton = document.getElementById("playButton");
  const showCausal = document.getElementById("showCausal");
  const showRetrospective = document.getElementById("showRetrospective");
  const showTrails = document.getElementById("showTrails");
  const visibleOnly = document.getElementById("visibleOnly");
  const satelliteFilter = document.getElementById("satelliteFilter");

  const ns = "http://www.w3.org/2000/svg";
  const make = (name, attrs = {}) => {
    const el = document.createElementNS(ns, name);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
    return el;
  };
  const project = (lon, lat) => [((Number(lon) + 180) / 360) * 1000, ((90 - Number(lat)) / 180) * 520];
  const numeric = value =>
    value === null || value === undefined || value === "" ? NaN : Number(value);
  const fmt = (value, digits = 1, suffix = "") =>
    Number.isFinite(numeric(value)) ? `${numeric(value).toFixed(digits)}${suffix}` : "—";

  function geometryPath(geometry) {
    if (!geometry) return "";
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    let path = "";
    polygons.forEach(polygon => polygon.forEach(ring => {
      ring.forEach((point, i) => {
        const [x, y] = project(point[0], point[1]);
        path += `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      });
      path += "Z";
    }));
    return path;
  }

  function drawBaseMap() {
    mapSvg.replaceChildren();
    const defs = make("defs");
    const clip = make("clipPath", { id: "mapClip" });
    clip.appendChild(make("rect", { x: 0, y: 0, width: 1000, height: 520, rx: 10 }));
    defs.appendChild(clip);
    mapSvg.appendChild(defs);

    const grid = make("g", { "clip-path": "url(#mapClip)" });
    for (let lon = -180; lon <= 180; lon += 30) {
      const [x] = project(lon, 0);
      grid.appendChild(make("line", { x1: x, y1: 0, x2: x, y2: 520, class: "map-grid" }));
      const label = make("text", { x: x + 3, y: 514, class: "map-label" });
      label.textContent = `${Math.abs(lon)}°${lon < 0 ? "W" : lon > 0 ? "E" : ""}`;
      grid.appendChild(label);
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const [, y] = project(0, lat);
      grid.appendChild(make("line", { x1: 0, y1: y, x2: 1000, y2: y, class: "map-grid" }));
      const label = make("text", { x: 5, y: y - 4, class: "map-label" });
      label.textContent = `${Math.abs(lat)}°${lat < 0 ? "S" : lat > 0 ? "N" : ""}`;
      grid.appendChild(label);
    }
    mapSvg.appendChild(grid);

    const landGroup = make("g", { "clip-path": "url(#mapClip)" });
    (world.features || []).forEach(feature => {
      landGroup.appendChild(make("path", { d: geometryPath(feature.geometry), class: "map-land" }));
    });
    mapSvg.appendChild(landGroup);
  }

  function markerTitle(group, text) {
    const title = make("title");
    title.textContent = text;
    group.appendChild(title);
  }

  function trailFor(catId, mode, currentIndex) {
    const points = [];
    for (let i = 0; i <= currentIndex; i += 1) {
      const satellite = (frames[i].satellites || []).find(item => item.norad_cat_id === catId);
      const position = satellite && satellite[mode];
      if (position) points.push(project(position.longitude_deg, position.latitude_deg));
    }
    return points.length > 1 ? points.map(point => point.join(",")).join(" ") : "";
  }

  function renderMap(frame) {
    drawBaseMap();
    const content = make("g", { "clip-path": "url(#mapClip)" });
    const filtered = (frame.satellites || []).filter(satellite => {
      if (!visibleOnly.checked) return true;
      return satellite.visibility && satellite.visibility.visible;
    });

    if (showTrails.checked) {
      filtered.forEach(satellite => {
        if (showCausal.checked) {
          const points = trailFor(satellite.norad_cat_id, "causal", index);
          if (points) content.appendChild(make("polyline", { points, class: "causal-trail" }));
        }
        if (showRetrospective.checked) {
          const points = trailFor(satellite.norad_cat_id, "retrospective", index);
          if (points) content.appendChild(make("polyline", { points, class: "retro-trail" }));
        }
      });
    }

    filtered.forEach(satellite => {
      const causal = satellite.causal;
      const retro = satellite.retrospective;
      if (showCausal.checked && showRetrospective.checked && causal && retro) {
        const [x1, y1] = project(causal.longitude_deg, causal.latitude_deg);
        const [x2, y2] = project(retro.longitude_deg, retro.latitude_deg);
        content.appendChild(make("line", { x1, y1, x2, y2, class: "delta-line" }));
      }
      if (showCausal.checked && causal) {
        const [x, y] = project(causal.longitude_deg, causal.latitude_deg);
        const group = make("g");
        markerTitle(group, `${satellite.object_name} · causal · ${fmt(causal.height_km, 1, " km")}`);
        group.appendChild(make("circle", { cx: x, cy: y, r: 5.5, class: "causal-marker" }));
        content.appendChild(group);
      }
      if (showRetrospective.checked && retro) {
        const [x, y] = project(retro.longitude_deg, retro.latitude_deg);
        const group = make("g");
        markerTitle(group, `${satellite.object_name} · retrospective · ${fmt(retro.height_km, 1, " km")}`);
        group.appendChild(make("rect", { x: x - 4.8, y: y - 4.8, width: 9.6, height: 9.6, transform: `rotate(45 ${x} ${y})`, class: "retro-marker" }));
        content.appendChild(group);
      }
    });

    const [sx, sy] = project(data.site.longitude_deg, data.site.latitude_deg);
    const siteGroup = make("g");
    markerTitle(siteGroup, `${data.site.name} · ${data.site.latitude_deg}, ${data.site.longitude_deg}`);
    siteGroup.appendChild(make("path", { d: `M${sx},${sy-9} L${sx+3},${sy-3} L${sx+9},${sy-3} L${sx+4},${sy+1} L${sx+6},${sy+8} L${sx},${sy+4} L${sx-6},${sy+8} L${sx-4},${sy+1} L${sx-9},${sy-3} L${sx-3},${sy-3} Z`, class: "site-marker" }));
    content.appendChild(siteGroup);
    mapSvg.appendChild(content);
  }

  function metricSeries(key) {
    return frames.map(frame => {
      const c = frame.communication || {};
      if (key === "delay") return Number.isFinite(numeric(c.rtt_ms)) ? numeric(c.rtt_ms) : numeric(c.delay_ms);
      return numeric(c[key]);
    });
  }

  function pathFor(values, x, y, width, height) {
    const finite = values.filter(Number.isFinite);
    if (!finite.length) return "";
    const min = Math.min(...finite);
    const max = Math.max(...finite);
    const span = max - min || 1;
    let started = false;
    return values.map((value, i) => {
      if (!Number.isFinite(value)) return null;
      const px = x + (values.length === 1 ? 0 : (i / (values.length - 1)) * width);
      const py = y + height - ((value - min) / span) * height;
      const command = started ? "L" : "M";
      started = true;
      return `${command}${px.toFixed(2)},${py.toFixed(2)}`;
    }).filter(Boolean).join(" ");
  }

  function renderTimeline() {
    timelineSvg.replaceChildren();
    const x = 60, width = 1000;
    const lanes = [
      { key: "delay", y: 18, height: 58, cls: "timeline-delay", label: "Delay / RTT", color: "#f4c95d" },
      { key: "rate_mbit", y: 92, height: 58, cls: "timeline-rate", label: "Throughput", color: "#6dd6a8" },
      { key: "loss_pct", y: 166, height: 45, cls: "timeline-loss", label: "Loss", color: "#ff7d91" }
    ];
    (data.events || []).forEach(event => {
      const total = Math.max(0.0001, frames[frames.length - 1].elapsed_sec - frames[0].elapsed_sec);
      const start = x + ((event.start_sec - frames[0].elapsed_sec) / total) * width;
      const end = x + ((event.end_sec - frames[0].elapsed_sec) / total) * width;
      timelineSvg.appendChild(make("rect", { x: Math.max(x, start), y: 10, width: Math.max(2, end - start), height: 205, class: "timeline-event" }));
    });
    lanes.forEach(lane => {
      timelineSvg.appendChild(make("line", { x1: x, y1: lane.y + lane.height, x2: x + width, y2: lane.y + lane.height, class: "timeline-axis" }));
      const label = make("text", { x: 4, y: lane.y + 15, class: "timeline-legend", fill: lane.color });
      label.textContent = lane.label;
      timelineSvg.appendChild(label);
      const values = metricSeries(lane.key);
      const d = pathFor(values, x, lane.y, width, lane.height);
      if (d) timelineSvg.appendChild(make("path", { d, class: lane.cls }));
    });
    for (let i = 0; i <= 5; i += 1) {
      const gx = x + (i / 5) * width;
      timelineSvg.appendChild(make("line", { x1: gx, y1: 10, x2: gx, y2: 215, class: "timeline-grid" }));
      const label = make("text", { x: gx - 8, y: 235, class: "timeline-label" });
      const elapsed = frames[0].elapsed_sec + (i / 5) * (frames[frames.length - 1].elapsed_sec - frames[0].elapsed_sec);
      label.textContent = `${elapsed.toFixed(1)} s`;
      timelineSvg.appendChild(label);
    }
    const cursorX = x + (frames.length === 1 ? 0 : (index / (frames.length - 1)) * width);
    timelineSvg.appendChild(make("line", { x1: cursorX, y1: 7, x2: cursorX, y2: 218, class: "timeline-cursor" }));
  }

  function renderTable(frame) {
    const query = satelliteFilter.value.trim().toLowerCase();
    const body = document.getElementById("satelliteTable");
    body.replaceChildren();
    (frame.satellites || []).filter(satellite => {
      return !query || satellite.object_name.toLowerCase().includes(query) || satellite.norad_cat_id.toLowerCase().includes(query);
    }).forEach(satellite => {
      const tr = document.createElement("tr");
      const visible = satellite.visibility && satellite.visibility.visible;
      const flags = satellite.flags || [];
      tr.innerHTML = `
        <td><span class="sat-name"></span><span class="sat-id"></span></td>
        <td>${visible ? '<span class="pill visible">Visible</span>' : '<span class="pill">Unknown / no</span>'}</td>
        <td>${satellite.visibility ? fmt(satellite.visibility.elevation_deg, 1, "°") : "—"}</td>
        <td>${satellite.causal ? fmt(satellite.causal.absolute_epoch_distance_sec / 3600, 2, " h") : "—"}</td>
        <td>${satellite.retrospective ? fmt(satellite.retrospective.absolute_epoch_distance_sec / 3600, 2, " h") : "—"}</td>
        <td>${fmt(satellite.position_delta_km, 2, " km")}</td>
        <td class="flags-cell"></td>`;
      tr.querySelector(".sat-name").textContent = satellite.object_name;
      tr.querySelector(".sat-id").textContent = `NORAD ${satellite.norad_cat_id}`;
      const flagsCell = tr.querySelector(".flags-cell");
      flags.forEach(flag => {
        const pill = document.createElement("span");
        pill.className = "pill flag";
        pill.textContent = flag;
        flagsCell.appendChild(pill);
      });
      body.appendChild(tr);
    });
  }

  function renderDetails(frame) {
    document.getElementById("currentTimestamp").textContent = frame.timestamp_utc;
    const c = frame.communication || {};
    const delay = Number.isFinite(numeric(c.rtt_ms)) ? `${fmt(c.rtt_ms, 1, " ms")} RTT` : `${fmt(c.delay_ms, 1, " ms")} delay`;
    document.getElementById("metricDelay").textContent = delay;
    document.getElementById("metricRate").textContent = fmt(c.rate_mbit, 1, " Mbps");
    document.getElementById("metricLoss").textContent = fmt(c.loss_pct, 2, "%");
    document.getElementById("metricVisible").textContent = `${frame.summary.visible_count} / ${frame.summary.satellite_count}`;
    document.getElementById("activeEvent").textContent = frame.events.length ? frame.events.map(event => event.event_type).join(", ") : (c.note || "None");
    document.getElementById("maximumDelta").textContent = fmt(data.summary.maximum_causal_retrospective_position_delta_km, 2, " km");
    document.getElementById("frameNumber").textContent = String(index + 1);
    document.getElementById("frameTotal").textContent = String(frames.length);
    document.getElementById("timeCaption").textContent = `${data.timeline.start_utc} → ${data.timeline.end_utc} · ${data.summary.satellite_count} satellites`;
  }

  function render() {
    if (!frames.length) return;
    index = Math.max(0, Math.min(index, frames.length - 1));
    slider.value = String(index);
    const frame = frames[index];
    renderMap(frame);
    renderTimeline();
    renderDetails(frame);
    renderTable(frame);
  }

  function togglePlay() {
    if (timer) {
      clearInterval(timer);
      timer = null;
      playButton.textContent = "Play";
      return;
    }
    playButton.textContent = "Pause";
    timer = setInterval(() => {
      index = (index + 1) % frames.length;
      render();
    }, 650);
  }

  document.getElementById("pageTitle").textContent = data.title;
  document.getElementById("siteBox").textContent = `${data.site.name} · ${data.site.latitude_deg.toFixed(4)}°, ${data.site.longitude_deg.toFixed(4)}° · ${fmt(data.site.elevation_m, 0, " m")}`;
  document.getElementById("bundleFooter").textContent = `${data.generator} · generated ${data.generated_at_utc}`;
  slider.max = String(Math.max(0, frames.length - 1));
  slider.addEventListener("input", () => { index = Number(slider.value); render(); });
  playButton.addEventListener("click", togglePlay);
  [showCausal, showRetrospective, showTrails, visibleOnly].forEach(control => control.addEventListener("change", render));
  satelliteFilter.addEventListener("input", () => renderTable(frames[index]));
  document.addEventListener("keydown", event => {
    if (event.key === "ArrowRight") { index = Math.min(frames.length - 1, index + 1); render(); }
    if (event.key === "ArrowLeft") { index = Math.max(0, index - 1); render(); }
    if (event.key === " ") { event.preventDefault(); togglePlay(); }
  });
  render();
})();
