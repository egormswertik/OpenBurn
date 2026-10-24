/**
 * OpenBurn Core Web Frontend
 * Clean-room architecture: Single Page Canvas CAM
 */

// §1.1 Layer Palette (30 Cut + 2 Tool layers)
const LAYER_PALETTE = [
  { index: 0, name: "C00", color: "#000000" },
  { index: 1, name: "C01", color: "#0000FF" },
  { index: 2, name: "C02", color: "#FF0000" },
  { index: 3, name: "C03", color: "#00E000" },
  { index: 4, name: "C04", color: "#D0D000" },
  { index: 5, name: "C05", color: "#FF8000" },
  { index: 6, name: "C06", color: "#00E0E0" },
  { index: 7, name: "C07", color: "#FF00FF" },
  { index: 8, name: "C08", color: "#B4B4B4" },
  { index: 9, name: "C09", color: "#0000A0" },
  { index: 10, name: "C10", color: "#A00000" },
  { index: 11, name: "C11", color: "#00A000" },
  { index: 12, name: "C12", color: "#A0A000" },
  { index: 13, name: "C13", color: "#C08000" },
  { index: 14, name: "C14", color: "#00A0FF" },
  { index: 15, name: "C15", color: "#A000A0" },
  { index: 16, name: "C16", color: "#808080" },
  { index: 17, name: "C17", color: "#7D87B9" },
  { index: 18, name: "C18", color: "#BB7784" },
  { index: 19, name: "C19", color: "#4A6FE3" },
  { index: 20, name: "C20", color: "#D33F6A" },
  { index: 21, name: "C21", color: "#8CD78C" },
  { index: 22, name: "C22", color: "#F0B98D" },
  { index: 23, name: "C23", color: "#F6C4E1" },
  { index: 24, name: "C24", color: "#FA9ED4" },
  { index: 25, name: "C25", color: "#500A78" },
  { index: 26, name: "C26", color: "#B45A00" },
  { index: 27, name: "C27", color: "#004754" },
  { index: 28, name: "C28", color: "#86FA88" },
  { index: 29, name: "C29", color: "#FFDB66" },
  { index: 30, name: "T1",  color: "#F68B1F" },
  { index: 31, name: "T2",  color: "#28A745" }
];

// App State
const state = {
  profile: { bed_width: 400, bed_height: 400, origin_corner: "Bottom-Left" },
  shapes: [],
  cutSettings: {}, // index -> CutSetting
  activeLayer: 0,
  activeTool: "select", // select, rect, ellipse, line
  selectedShapeIndex: -1,
  device: { connected: false, state: "Disconnected", port: null, x: 0, y: 0 },
  jogStep: 10,
  jobOrigin: 6, // 6 = Bottom-Left
  view: {
    zoom: 1.5,
    panX: 40,
    panY: 40,
    isPanning: false,
    panStartX: 0,
    panStartY: 0
  },
  drawing: {
    isDrawing: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0
  }
};

// DOM Elements
const canvas = document.getElementById("mainCanvas");
const ctx = canvas.getContext("2d");
const hudCoords = document.getElementById("hudCoords");
const hudZoom = document.getElementById("hudZoom");
const deviceStateText = document.getElementById("deviceStateText");
const statusDot = document.getElementById("statusDot");
const layerTableBody = document.getElementById("layerTableBody");
const paletteBar = document.getElementById("paletteBar");

// Initialize Default Layers
function initDefaultLayers() {
  LAYER_PALETTE.forEach(p => {
    state.cutSettings[p.index] = {
      Type: "Cut",
      Index: p.index,
      Name: p.name,
      Speed: 100,
      MaxPower: 20,
      MinPower: 10,
      NumPasses: 1,
      ZOffset: 0,
      ZStep: 0,
      LineInterval: 0.1,
      Output: true
    };
  });
}

// Build Swatch Palette UI
function renderPalette() {
  paletteBar.innerHTML = "";
  LAYER_PALETTE.forEach(p => {
    const btn = document.createElement("button");
    btn.className = `swatch-btn ${p.index === state.activeLayer ? "selected" : ""}`;
    btn.style.backgroundColor = p.color;
    btn.textContent = p.index < 30 ? p.index : p.name;
    btn.title = `${p.name} (${p.color})`;
    btn.onclick = () => {
      state.activeLayer = p.index;
      if (state.selectedShapeIndex >= 0 && state.shapes[state.selectedShapeIndex]) {
        state.shapes[state.selectedShapeIndex].CutIndex = p.index;
        syncProjectToServer();
      }
      renderPalette();
      renderLayerTable();
      redrawCanvas();
    };
    paletteBar.appendChild(btn);
  });
}

// Render Layers in Dock
function renderLayerTable() {
  layerTableBody.innerHTML = "";
  // Find which layers are used in project
  const usedLayers = new Set(state.shapes.map(s => s.CutIndex));
  if (usedLayers.size === 0) usedLayers.add(state.activeLayer);

  Array.from(usedLayers).sort((a,b) => a - b).forEach(idx => {
    const pal = LAYER_PALETTE[idx] || { name: `C${idx}`, color: "#999" };
    const cs = state.cutSettings[idx] || { Type: "Cut", Speed: 100, MaxPower: 20, Output: true };
    const tr = document.createElement("tr");
    tr.className = `layer-row ${idx === state.activeLayer ? "active" : ""}`;
    tr.innerHTML = `
      <td><span class="layer-color-badge" style="background:${pal.color}"></span></td>
      <td><strong>${pal.name}</strong></td>
      <td>
        <select onchange="updateLayerType(${idx}, this.value)" style="background:#18181c; color:#fff; border:1px solid #333; font-size:11px; padding:2px;">
          <option value="Cut" ${cs.Type === "Cut" ? "selected" : ""}>Cut (Line)</option>
          <option value="Scan" ${cs.Type === "Scan" ? "selected" : ""}>Scan (Fill)</option>
          <option value="Scan+Cut" ${cs.Type === "Scan+Cut" ? "selected" : ""}>Scan+Cut</option>
          <option value="Image" ${cs.Type === "Image" ? "selected" : ""}>Image</option>
        </select>
      </td>
      <td><input type="number" value="${cs.Speed}" style="width:50px; background:#18181c; color:#fff; border:1px solid #333; font-size:11px; padding:2px;" onchange="updateLayerSpeed(${idx}, this.value)"></td>
      <td><input type="number" value="${cs.MaxPower}" style="width:45px; background:#18181c; color:#fff; border:1px solid #333; font-size:11px; padding:2px;" onchange="updateLayerPower(${idx}, this.value)"></td>
    `;
    layerTableBody.appendChild(tr);
  });
}

window.updateLayerType = function(idx, val) {
  if (state.cutSettings[idx]) state.cutSettings[idx].Type = val;
  syncProjectToServer();
};
window.updateLayerSpeed = function(idx, val) {
  if (state.cutSettings[idx]) state.cutSettings[idx].Speed = parseFloat(val);
  syncProjectToServer();
};
window.updateLayerPower = function(idx, val) {
  if (state.cutSettings[idx]) state.cutSettings[idx].MaxPower = parseFloat(val);
  syncProjectToServer();
};

// Canvas Coordinate Transforms
function screenToWorld(sx, sy) {
  const rect = canvas.getBoundingClientRect();
  const px = sx - rect.left;
  const py = sy - rect.top;
  const h = canvas.height;
  const wx = (px - state.view.panX) / state.view.zoom;
  // World Y is from bottom-up (laser bed coordinates)
  const wy = (h - py - state.view.panY) / state.view.zoom;
  return { x: wx, y: wy };
}

function worldToScreen(wx, wy) {
  const h = canvas.height;
  const sx = wx * state.view.zoom + state.view.panX;
  const sy = h - (wy * state.view.zoom + state.view.panY);
  return { x: sx, y: sy };
}

// Draw Everything
function redrawCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const bedW = state.profile.bed_width;
  const bedH = state.profile.bed_height;

  // 1. Draw Grid
  ctx.save();
  const origin = worldToScreen(0, 0);
  const bedTopRight = worldToScreen(bedW, bedH);

  // Bed boundary
  ctx.strokeStyle = "#383845";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#181820";
  ctx.fillRect(origin.x, bedTopRight.y, bedW * state.view.zoom, bedH * state.view.zoom);
  ctx.strokeRect(origin.x, bedTopRight.y, bedW * state.view.zoom, bedH * state.view.zoom);

  // Grid lines (10mm minor, 50mm major)
  ctx.beginPath();
  for (let x = 0; x <= bedW; x += 10) {
    const p1 = worldToScreen(x, 0);
    const p2 = worldToScreen(x, bedH);
    ctx.strokeStyle = (x % 50 === 0) ? "#2c2c3a" : "#20202a";
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
  }
  for (let y = 0; y <= bedH; y += 10) {
    const p1 = worldToScreen(0, y);
    const p2 = worldToScreen(bedW, y);
    ctx.strokeStyle = (y % 50 === 0) ? "#2c2c3a" : "#20202a";
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
  }
  ctx.stroke();

  // Coordinate Rulers/Axes
  ctx.beginPath();
  ctx.strokeStyle = "#ff4444"; // X axis (Red)
  ctx.lineWidth = 2;
  ctx.moveTo(origin.x, origin.y);
  ctx.lineTo(origin.x + 40, origin.y);
  ctx.strokeStyle = "#44ff44"; // Y axis (Green)
  ctx.moveTo(origin.x, origin.y);
  ctx.lineTo(origin.x, origin.y - 40);
  ctx.stroke();
  ctx.restore();

  // 2. Draw Shapes
  state.shapes.forEach((s, idx) => {
    ctx.save();
    const isSelected = idx === state.selectedShapeIndex;
    const pal = LAYER_PALETTE[s.CutIndex] || { color: "#ff0000" };
    ctx.strokeStyle = isSelected ? "#00e5ff" : pal.color;
    ctx.lineWidth = isSelected ? 2.5 : 1.5;

    const xf = s.XForm || [1, 0, 0, 1, 0, 0];
    const m11 = xf[0], m12 = xf[1], m21 = xf[2], m22 = xf[3], dx = xf[4], dy = xf[5];

    if (s.Type === "Rect") {
      const w = s.W || 20;
      const h = s.H || 10;
      // 4 corners transformed
      const corners = [
        { x: -w/2, y: -h/2 },
        { x:  w/2, y: -h/2 },
        { x:  w/2, y:  h/2 },
        { x: -w/2, y:  h/2 }
      ].map(pt => {
        const wx = m11 * pt.x + m21 * pt.y + dx;
        const wy = m12 * pt.x + m22 * pt.y + dy;
        return worldToScreen(wx, wy);
      });

      ctx.beginPath();
      ctx.moveTo(corners[0].x, corners[0].y);
      for (let i = 1; i < 4; i++) ctx.lineTo(corners[i].x, corners[i].y);
      ctx.closePath();
      ctx.stroke();

      // If Scan mode, fill subtle hatch preview
      const cs = state.cutSettings[s.CutIndex];
      if (cs && (cs.Type === "Scan" || cs.Type === "Scan+Cut")) {
        ctx.fillStyle = pal.color + "33"; // transparent
        ctx.fill();
      }
    } else if (s.Type === "Ellipse") {
      const rx = s.Rx || 10;
      const ry = s.Ry || 10;
      const center = worldToScreen(dx, dy);
      ctx.beginPath();
      ctx.ellipse(center.x, center.y, rx * state.view.zoom, ry * state.view.zoom, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else if (s.Type === "Path") {
      // Basic Path preview
      if (s.VertList) {
        const parts = s.VertList.split(/\s+/).filter(Boolean);
        ctx.beginPath();
        parts.forEach((v, vi) => {
          if (v.startsWith("V")) {
            const coords = v.substring(1).split("c")[0].split(" ");
            if (coords.length >= 2) {
              const pt = worldToScreen(parseFloat(coords[0]) + dx, parseFloat(coords[1]) + dy);
              if (vi === 0) ctx.moveTo(pt.x, pt.y);
              else ctx.lineTo(pt.x, pt.y);
            }
          }
        });
        ctx.stroke();
      }
    }
    ctx.restore();
  });

  // 3. Draw In-progress Interactive Shape
  if (state.drawing.isDrawing) {
    ctx.save();
    ctx.strokeStyle = "#ffff00";
    ctx.setLineDash([4, 4]);
    const p1 = worldToScreen(state.drawing.startX, state.drawing.startY);
    const p2 = worldToScreen(state.drawing.currentX, state.drawing.currentY);
    if (state.activeTool === "rect") {
      ctx.strokeRect(Math.min(p1.x, p2.x), Math.min(p1.y, p2.y), Math.abs(p2.x - p1.x), Math.abs(p2.y - p1.y));
    } else if (state.activeTool === "ellipse") {
      const cx = (p1.x + p2.x) / 2;
      const cy = (p1.y + p2.y) / 2;
      const rx = Math.abs(p2.x - p1.x) / 2;
      const ry = Math.abs(p2.y - p1.y) / 2;
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else if (state.activeTool === "line") {
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  // 4. Draw Laser Head Position
  const headPos = worldToScreen(state.device.x, state.device.y);
  ctx.save();
  ctx.strokeStyle = "#ff0055";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(headPos.x, headPos.y, 8, 0, Math.PI * 2);
  ctx.moveTo(headPos.x - 12, headPos.y);
  ctx.lineTo(headPos.x + 12, headPos.y);
  ctx.moveTo(headPos.x, headPos.y - 12);
  ctx.lineTo(headPos.x, headPos.y + 12);
  ctx.stroke();
  ctx.restore();
}

// Canvas Interaction (Pan, Zoom, Drawing)
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
  const mouse = screenToWorld(e.clientX, e.clientY);

  state.view.zoom = Math.max(0.2, Math.min(10.0, state.view.zoom * zoomFactor));
  const newMouseScreen = worldToScreen(mouse.x, mouse.y);
  state.view.panX += (e.clientX - canvas.getBoundingClientRect().left) - newMouseScreen.x;
  state.view.panY -= (e.clientY - canvas.getBoundingClientRect().top) - newMouseScreen.y;

  hudZoom.textContent = `${Math.round(state.view.zoom * 100)}%`;
  redrawCanvas();
});

canvas.addEventListener("mousedown", (e) => {
  if (e.button === 1 || e.shiftKey || state.activeTool === "pan") {
    // Middle button or Shift: Pan
    state.view.isPanning = true;
    state.view.panStartX = e.clientX - state.view.panX;
    state.view.panStartY = e.clientY - state.view.panY;
    return;
  }

  const w = screenToWorld(e.clientX, e.clientY);
  if (state.activeTool === "select") {
    // Hit test shapes
    state.selectedShapeIndex = -1;
    for (let i = state.shapes.length - 1; i >= 0; i--) {
      const s = state.shapes[i];
      const dx = (s.XForm && s.XForm[4]) || 0;
      const dy = (s.XForm && s.XForm[5]) || 0;
      const dist = Math.hypot(w.x - dx, w.y - dy);
      if (dist < 20) { // simple hit test
        state.selectedShapeIndex = i;
        state.activeLayer = s.CutIndex;
        renderPalette();
        renderLayerTable();
        break;
      }
    }
    redrawCanvas();
  } else {
    // Start drawing shape
    state.drawing.isDrawing = true;
    state.drawing.startX = w.x;
    state.drawing.startY = w.y;
    state.drawing.currentX = w.x;
    state.drawing.currentY = w.y;
  }
});

canvas.addEventListener("mousemove", (e) => {
  const w = screenToWorld(e.clientX, e.clientY);
  hudCoords.textContent = `X: ${w.x.toFixed(1)} mm, Y: ${w.y.toFixed(1)} mm`;

  if (state.view.isPanning) {
    state.view.panX = e.clientX - state.view.panStartX;
    state.view.panY = e.clientY - state.view.panStartY;
    redrawCanvas();
  } else if (state.drawing.isDrawing) {
    state.drawing.currentX = w.x;
    state.drawing.currentY = w.y;
    redrawCanvas();
  }
});

window.addEventListener("mouseup", () => {
  if (state.view.isPanning) {
    state.view.isPanning = false;
  }
  if (state.drawing.isDrawing) {
    state.drawing.isDrawing = false;
    const x1 = state.drawing.startX;
    const y1 = state.drawing.startY;
    const x2 = state.drawing.currentX;
    const y2 = state.drawing.currentY;
    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;
    const w = Math.abs(x2 - x1);
    const h = Math.abs(y2 - y1);

    if (w > 1 && h > 1) {
      if (state.activeTool === "rect") {
        state.shapes.push({
          Type: "Rect",
          CutIndex: state.activeLayer,
          W: w,
          H: h,
          Cr: 0,
          XForm: [1, 0, 0, 1, cx, cy]
        });
      } else if (state.activeTool === "ellipse") {
        state.shapes.push({
          Type: "Ellipse",
          CutIndex: state.activeLayer,
          Rx: w / 2,
          Ry: h / 2,
          XForm: [1, 0, 0, 1, cx, cy]
        });
      }
      syncProjectToServer();
      renderLayerTable();
      redrawCanvas();
    }
  }
});

// Resize Canvas
function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;
  redrawCanvas();
}
window.addEventListener("resize", resizeCanvas);

// REST API Operations
async function syncProjectToServer() {
  const settingsList = Object.values(state.cutSettings);
  try {
    await fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shapes: state.shapes,
        cut_settings: settingsList
      })
    });
  } catch (err) {
    console.error("Sync project error:", err);
  }
}

async function loadProjectFromServer() {
  try {
    const res = await fetch("/api/project");
    if (res.ok) {
      const data = await res.json();
      state.shapes = data.shapes || [];
      if (data.cut_settings && data.cut_settings.length > 0) {
        data.cut_settings.forEach(cs => {
          state.cutSettings[cs.Index] = cs;
        });
      }
      renderLayerTable();
      redrawCanvas();
    }
  } catch (err) {
    console.warn("Could not load initial project:", err);
  }
}

// Laser Controls
async function deviceConnect() {
  let defaultPort = "COM6";
  try {
    const pRes = await fetch("/api/device/ports");
    if (pRes.ok) {
      const pData = await pRes.json();
      if (pData.ports && pData.ports.length > 0) {
        const usbPort = pData.ports.find(p => p.description.includes("CH340") || p.description.includes("USB"));
        defaultPort = usbPort ? usbPort.port : pData.ports[0].port;
      }
    }
  } catch(e) {}

  const port = prompt("Enter Serial Port:", defaultPort);
  if (!port) return;
  const res = await fetch("/api/device/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ port })
  });
  if (res.ok) {
    state.device.connected = true;
    state.device.state = "Idle";
    updateDeviceHUD();
  } else {
    const err = await res.json();
    alert(`Connection failed: ${err.message}`);
  }
}

async function startJob() {
  const res = await fetch("/api/job/start", { method: "POST" });
  if (!res.ok) {
    const err = await res.json();
    alert(`Cannot start job: ${err.message}`);
  }
}

async function pauseJob() {
  const nextAction = state.device.state === "Hold" ? "resume" : "pause";
  await fetch("/api/job/pause", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: nextAction })
  });
}

async function stopJob() {
  await fetch("/api/job/stop", { method: "POST" });
}

async function jogLaser(dx, dy) {
  const step = state.jogStep;
  await fetch("/api/jog", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ x: dx * step, y: dy * step })
  });
}

async function homeLaser() {
  await fetch("/api/home", { method: "POST" });
}

async function zeroLaser() {
  await fetch("/api/zero", { method: "POST" });
}

function updateDeviceHUD() {
  deviceStateText.textContent = state.device.state;
  statusDot.className = `status-dot ${state.device.state.toLowerCase()}`;
}

// G-Code Preview Modal
async function openPreview() {
  await syncProjectToServer();
  const res = await fetch("/api/preview", { method: "POST" });
  if (res.ok) {
    const data = await res.json();
    document.getElementById("gcodeViewer").value = data.gcode;
    document.getElementById("gcodeLinesCount").textContent = `${data.lines_count} lines`;
    document.getElementById("previewModal").style.display = "flex";
  } else {
    alert("Preview generation failed.");
  }
}

function closePreview() {
  document.getElementById("previewModal").style.display = "none";
}

function downloadGcode() {
  const text = document.getElementById("gcodeViewer").value;
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "output.gcode";
  a.click();
  URL.revokeObjectURL(url);
}

// File Upload Handler
document.getElementById("fileInput").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/file/upload", {
    method: "POST",
    body: formData
  });
  if (res.ok) {
    await loadProjectFromServer();
  } else {
    alert("File upload failed");
  }
});

// SSE Live Updates
function initSSE() {
  const es = new EventSource("/api/events");
  es.addEventListener("state_changed", (e) => {
    const d = JSON.parse(e.data);
    state.device.state = d.state;
    updateDeviceHUD();
  });
  es.addEventListener("position", (e) => {
    const d = JSON.parse(e.data);
    state.device.x = d.x;
    state.device.y = d.y;
    redrawCanvas();
  });
}

// Generators & Modals logic
let laserFireActive = false;

window.toggleGeneratorsMenu = function() {
  const menu = document.getElementById("generatorsDropdown");
  menu.style.display = menu.style.display === "block" ? "none" : "block";
};

document.addEventListener("click", (e) => {
  const menu = document.getElementById("generatorsDropdown");
  if (menu && !e.target.closest(".dropdown")) {
    menu.style.display = "none";
  }
});

window.closeModals = function() {
  document.querySelectorAll(".modal-backdrop").forEach(m => m.style.display = "none");
};

window.openMaterialTestDialog = function() {
  document.getElementById("generatorsDropdown").style.display = "none";
  document.getElementById("materialTestModal").style.display = "flex";
};

window.submitMaterialTest = async function() {
  const min_power = document.getElementById("matMinPower").value;
  const max_power = document.getElementById("matMaxPower").value;
  const p_steps = document.getElementById("matPSteps").value;
  const min_speed = document.getElementById("matMinSpeed").value;
  const max_speed = document.getElementById("matMaxSpeed").value;
  const s_steps = document.getElementById("matSSteps").value;
  const mode = document.getElementById("matMode").value;

  const res = await fetch("/api/tools/material-test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_power, max_power, p_steps, min_speed, max_speed, s_steps, mode })
  });
  if (res.ok) {
    closeModals();
    await loadProjectFromServer();
  }
};

window.openFocusTestDialog = function() {
  document.getElementById("generatorsDropdown").style.display = "none";
  document.getElementById("focusTestModal").style.display = "flex";
};

window.submitFocusTest = async function() {
  const min_z = document.getElementById("focMinZ").value;
  const max_z = document.getElementById("focMaxZ").value;
  const steps = document.getElementById("focSteps").value;

  const res = await fetch("/api/tools/focus-test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_z, max_z, steps })
  });
  if (res.ok) {
    closeModals();
    await loadProjectFromServer();
  }
};

window.openGridArrayDialog = function() {
  document.getElementById("generatorsDropdown").style.display = "none";
  document.getElementById("gridArrayModal").style.display = "flex";
};

window.submitGridArray = async function() {
  const rows = document.getElementById("arrayRows").value;
  const cols = document.getElementById("arrayCols").value;
  const dx = document.getElementById("arrayDx").value;
  const dy = document.getElementById("arrayDy").value;

  const res = await fetch("/api/tools/array/grid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, cols, dx, dy })
  });
  if (res.ok) {
    closeModals();
    await loadProjectFromServer();
  }
};

window.openCircularArrayDialog = function() {
  document.getElementById("generatorsDropdown").style.display = "none";
  document.getElementById("circularArrayModal").style.display = "flex";
};

window.submitCircularArray = async function() {
  const count = document.getElementById("circCount").value;
  const radius = document.getElementById("circRadius").value;
  const rotate = document.getElementById("circRotate").value;

  const res = await fetch("/api/tools/array/circular", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count, radius, rotate })
  });
  if (res.ok) {
    closeModals();
    await loadProjectFromServer();
  }
};

window.toggleLaserFire = async function() {
  laserFireActive = !laserFireActive;
  const btn = document.getElementById("btnFireLaser");
  if (laserFireActive) {
    btn.style.background = "#e63946";
    btn.style.color = "#fff";
    btn.textContent = "🔥 LASER ON (2%)";
    await fetch("/api/laser/fire", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ power: 2.0, enable: true })
    });
  } else {
    btn.style.background = "#4a121a";
    btn.style.color = "#ff9999";
    btn.textContent = "🔥 Laser Fire (2%)";
    await fetch("/api/laser/fire", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enable: false })
    });
  }
};

window.saveProjectFile = function() {
  window.open("/api/file/download?format=lbrn2", "_blank");
};

// Console Terminal
window.executeConsoleInput = function() {
  const input = document.getElementById("consoleInput");
  const cmd = input.value.trim();
  if (!cmd) return;
  sendConsoleCommand(cmd);
  input.value = "";
};

window.sendConsoleCommand = async function(cmd) {
  const log = document.getElementById("consoleLog");
  log.textContent += `> ${cmd}\n`;
  log.scrollTop = log.scrollHeight;

  const res = await fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: cmd })
  });
  if (res.ok) {
    const data = await res.json();
    if (data.reply) {
      log.textContent += `< ${data.reply}\n`;
      log.scrollTop = log.scrollHeight;
    }
  }
};

// Tool Selection
window.setTool = function(tool) {
  state.activeTool = tool;
  document.querySelectorAll(".tool-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`tool-${tool}`)?.classList.add("active");
};

window.setJogStep = function(step) {
  state.jogStep = step;
  document.querySelectorAll(".jog-step-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`step-${step}`)?.classList.add("active");
};

window.setOriginPoint = function(pt) {
  state.jobOrigin = pt;
  document.querySelectorAll(".origin-dot").forEach((d, i) => {
    d.classList.toggle("active", i === pt);
  });
};

// Bind Top Actions
document.getElementById("btnConnect").onclick = deviceConnect;
document.getElementById("btnPreview").onclick = openPreview;
document.getElementById("btnStart").onclick = startJob;
document.getElementById("btnPause").onclick = pauseJob;
document.getElementById("btnStop").onclick = stopJob;
document.getElementById("btnHome").onclick = homeLaser;
document.getElementById("btnZero").onclick = zeroLaser;

// Boot
initDefaultLayers();
renderPalette();
renderLayerTable();
resizeCanvas();
loadProjectFromServer();
initSSE();
