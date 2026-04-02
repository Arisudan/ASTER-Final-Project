const SCREENS = {
  startup: "startupScreen",
  auth: "authScreen",
  dashboard: "dashboardScreen",
  app: "appScreen",
};

const APP_NAMES = ["music", "maps", "calls", "camera", "emotion", "settings"];

const state = {
  currentScreen: SCREENS.startup,
  activeApp: "",
  pinInput: "",
  speed: 0,
  battery: 92,
  gear: "P",
  mode: "ambient",
  idleTimer: null,
  miniMap: null,
  fullMap: null,
  miniRoute: null,
  fullRoute: null,
  currentLocation: [13.0827, 80.2707],
  spotifyConnected: false,
  swipeStartX: 0,
};

function byId(id) {
  return document.getElementById(id);
}

function announce(message) {
  const live = byId("liveRegion");
  if (live) {
    live.textContent = message || "";
  }
}

function showToast(message) {
  announce(message);
  console.log(message);
}

function showScreen(screenId) {
  Object.values(SCREENS).forEach((id) => {
    const el = byId(id);
    if (!el) {
      return;
    }
    el.classList.toggle("screen--active", id === screenId);
  });
  state.currentScreen = screenId;
}

function setMode(mode) {
  state.mode = mode === "driving" ? "driving" : "ambient";
  document.body.dataset.mode = state.mode;
  const indicator = byId("modeIndicator");
  if (indicator) {
    indicator.textContent = state.mode === "driving" ? "Driving" : "Ambient";
  }
}

function pulseDrivingMode() {
  setMode("driving");
  if (state.idleTimer) {
    window.clearTimeout(state.idleTimer);
  }
  state.idleTimer = window.setTimeout(() => setMode("ambient"), 8000);
}

function updateVehicleSimulation() {
  if (state.currentScreen !== SCREENS.dashboard && state.currentScreen !== SCREENS.app) {
    return;
  }

  state.speed = Math.max(0, Math.min(120, state.speed + Math.floor(Math.random() * 9) - 3));
  state.battery = Math.max(20, state.battery - (state.speed > 0 ? 0.03 : 0.01));

  if (state.speed === 0) {
    state.gear = "P";
  } else if (state.speed < 15) {
    state.gear = "D";
  } else {
    state.gear = "D";
  }

  const speedValue = byId("speedValue");
  const batteryValue = byId("batteryValue");
  const gearValue = byId("gearValue");
  if (speedValue) speedValue.textContent = String(state.speed);
  if (batteryValue) batteryValue.textContent = String(Math.round(state.battery));
  if (gearValue) gearValue.textContent = state.gear;

  if (state.speed > 0) {
    setMode("driving");
  }
}

function setAuthStatus(text) {
  const authStatus = byId("authStatus");
  if (authStatus) {
    authStatus.textContent = text;
  }
  announce(text);
}

function updatePinDots() {
  const dots = Array.from(document.querySelectorAll("#pinDots span"));
  dots.forEach((dot, idx) => dot.classList.toggle("active", idx < state.pinInput.length));
}

function clearPin() {
  state.pinInput = "";
  updatePinDots();
}

function openApp(appName, options = {}) {
  const { syncBackend = true, autoStartCamera = true } = options;
  const name = String(appName || "").toLowerCase();
  if (!APP_NAMES.includes(name)) {
    return;
  }

  state.activeApp = name;
  const title = byId("activeAppTitle");
  if (title) {
    title.textContent = name === "emotion" ? "Emotion AI" : name.charAt(0).toUpperCase() + name.slice(1);
  }

  byId("appLauncher")?.classList.add("hidden");
  document.querySelectorAll(".app-pane").forEach((pane) => pane.classList.add("hidden"));
  byId(`app${name.charAt(0).toUpperCase() + name.slice(1)}`)?.classList.remove("hidden");

  showScreen(SCREENS.app);
  pulseDrivingMode();

  if (window.eel && syncBackend) {
    eel.openApp(name)().catch(() => undefined);
  }

  if (window.eel && name === "camera" && autoStartCamera) {
    eel.startBabyMonitoring()().then((response) => {
      if (response && response.ok === false && response.message) {
        showToast(response.message);
      }
    }).catch(() => undefined);
  }

  if (name === "emotion") {
    const emotionStatus = byId("emotionStatus");
    if (emotionStatus) {
      emotionStatus.textContent = "Capture 10 camera samples and map mood to Spotify.";
    }
  }
}

function closeApp(options = {}) {
  const { syncBackend = true, stopCamera = true } = options;
  state.activeApp = "";
  byId("appLauncher")?.classList.remove("hidden");
  document.querySelectorAll(".app-pane").forEach((pane) => pane.classList.add("hidden"));
  showScreen(SCREENS.dashboard);

  if (window.eel && syncBackend) {
    eel.closeApp()().catch(() => undefined);
  }

  if (window.eel && stopCamera) {
    eel.stopCamera()().then((response) => {
      if (response && response.ok === false && response.message) {
        showToast(response.message);
      }
    }).catch(() => undefined);
  }
}

function setActiveApp(appName) {
  if (!appName) {
    closeApp({ syncBackend: false, stopCamera: false });
    return;
  }
  openApp(appName, { syncBackend: false, autoStartCamera: appName === "camera" });
}

function openAppFromBackend(appName) {
  openApp(appName, { syncBackend: false, autoStartCamera: appName === "camera" });
}

function closeAppFromBackend() {
  closeApp({ syncBackend: false, stopCamera: false });
}

function updateCameraFrame(owner, frameDataUrl) {
  if (!frameDataUrl) {
    return;
  }

  if (owner === "face-auth") {
    const authFeed = byId("authCameraFeed");
    if (authFeed) {
      authFeed.src = frameDataUrl;
    }
  }

  if (owner === "baby-monitor") {
    const babyFeed = byId("babyCameraFeed");
    if (babyFeed) {
      babyFeed.src = frameDataUrl;
    }
  }
}

function onFaceAuthSuccess(userName) {
  setAuthStatus(`Welcome ${userName || "Driver"}. Access granted.`);
  showScreen(SCREENS.dashboard);
  byId("pinPanel")?.classList.add("hidden");
}

function onFaceAuthFailed(message) {
  setAuthStatus(message || "Face not recognized. Use PIN fallback.");
  byId("pinPanel")?.classList.remove("hidden");
}

function setEmotionResult(payload) {
  const status = byId("emotionStatus");
  if (!status) {
    return;
  }

  if (!payload || payload.ok === false) {
    status.textContent = payload?.message || "Emotion detection failed.";
    return;
  }

  status.textContent = `Emotion: ${payload.emotion}. Playing: ${payload.query}`;
}

function updateSpotifyUI(payload) {
  if (!payload) {
    return;
  }

  const track = payload.track || payload.state?.track || null;
  if (!track) {
    return;
  }

  const title = byId("trackTitle");
  const meta = byId("trackMeta");
  if (title) title.textContent = track.title || "Unknown track";
  if (meta) meta.textContent = `${track.artist || "Unknown artist"} ${track.album ? `- ${track.album}` : ""}`;
}

function setSpotifyState(payload) {
  updateSpotifyUI(payload || {});
}

function setNavigationResult(payload) {
  if (!payload) {
    return;
  }

  const navSummary = byId("navSummary");
  if (navSummary) {
    navSummary.textContent = payload.message || "Route updated.";
  }

  if (!payload.ok || !payload.route || !Array.isArray(payload.route)) {
    return;
  }

  drawRoute(payload.route);
}

function drawRoute(route) {
  if (!state.miniMap || !state.fullMap || !window.L) {
    return;
  }

  if (state.miniRoute) state.miniMap.removeLayer(state.miniRoute);
  if (state.fullRoute) state.fullMap.removeLayer(state.fullRoute);

  state.miniRoute = L.polyline(route, { color: "#d4af37", weight: 4 }).addTo(state.miniMap);
  state.fullRoute = L.polyline(route, { color: "#d4af37", weight: 5 }).addTo(state.fullMap);

  state.miniMap.fitBounds(state.miniRoute.getBounds(), { padding: [16, 16] });
  state.fullMap.fitBounds(state.fullRoute.getBounds(), { padding: [20, 20] });
}

function setupMaps() {
  if (!window.L) {
    return;
  }

  const miniMapContainer = byId("miniMap");
  const fullMapContainer = byId("fullMap");
  if (!miniMapContainer || !fullMapContainer) {
    return;
  }

  state.miniMap = L.map(miniMapContainer, { zoomControl: false }).setView(state.currentLocation, 13);
  state.fullMap = L.map(fullMapContainer).setView(state.currentLocation, 13);

  const tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const opts = { maxZoom: 19, attribution: "&copy; OpenStreetMap" };

  L.tileLayer(tileUrl, opts).addTo(state.miniMap);
  L.tileLayer(tileUrl, opts).addTo(state.fullMap);

  L.marker(state.currentLocation).addTo(state.miniMap);
  L.marker(state.currentLocation).addTo(state.fullMap);
}

function bindPinPad() {
  const pad = byId("pinPad");
  if (!pad) {
    return;
  }

  const digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
  digits.forEach((digit) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pin-digit";
    button.textContent = digit;
    button.addEventListener("click", () => {
      if (state.pinInput.length >= 4) return;
      state.pinInput += digit;
      updatePinDots();
    });
    pad.appendChild(button);
  });
}

function bindUI() {
  byId("retryFaceBtn")?.addEventListener("click", async () => {
    const response = await eel.startFaceAuth()();
    if (response && response.ok === false && response.message) {
      setAuthStatus(response.message);
    }
  });
  byId("showPinBtn")?.addEventListener("click", () => byId("pinPanel")?.classList.remove("hidden"));
  byId("pinClearBtn")?.addEventListener("click", clearPin);

  byId("pinSubmitBtn")?.addEventListener("click", async () => {
    if (state.pinInput.length !== 4) {
      setAuthStatus("Enter 4-digit PIN");
      return;
    }
    const response = await eel.verifyPIN(state.pinInput)();
    if (response?.ok) {
      onFaceAuthSuccess(response.user || "Driver");
      clearPin();
    } else {
      setAuthStatus(response?.message || "Invalid PIN. Retry.");
      clearPin();
    }
  });

  document.querySelectorAll("[data-open-app]").forEach((element) => {
    element.addEventListener("click", () => openApp(element.getAttribute("data-open-app")));
  });

  byId("backToDashboard")?.addEventListener("click", closeApp);
  byId("expandMusicBtn")?.addEventListener("click", () => openApp("music"));
  byId("expandMapBtn")?.addEventListener("click", () => openApp("maps"));

  byId("playPauseBtn")?.addEventListener("click", async () => {
    const result = await eel.playSpotify("")();
    updateSpotifyUI(result);
  });
  byId("prevBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.prevTrack()()));
  byId("nextBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.nextTrack()()));

  byId("musicPlayQueryBtn")?.addEventListener("click", async () => {
    const query = byId("musicQueryInput")?.value || "";
    updateSpotifyUI(await eel.playSpotify(query)());
  });
  byId("musicPlayBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.playSpotify("")()));
  byId("musicPrevBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.prevTrack()()));
  byId("musicNextBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.nextTrack()()));

  byId("volumeSlider")?.addEventListener("input", (event) => {
    eel.setSpotifyVolume(event.target.value)().catch(() => undefined);
  });

  const runNavigation = async (sourceId) => {
    const place = byId(sourceId)?.value || "";
    if (!place.trim()) {
      return;
    }
    const response = await eel.navigateTo(place)();
    setNavigationResult(response);
  };

  byId("mapSearchBtn")?.addEventListener("click", () => runNavigation("mapSearchInput"));
  byId("mapFullSearchBtn")?.addEventListener("click", () => runNavigation("mapFullSearchInput"));

  byId("startBabyBtn")?.addEventListener("click", async () => {
    const response = await eel.startBabyMonitoring()();
    if (response && response.message) {
      showToast(response.message);
    }
  });

  byId("stopCameraBtn")?.addEventListener("click", async () => {
    const response = await eel.stopCamera()();
    if (response && response.message) {
      showToast(response.message);
    }
  });

  byId("startEmotionBtn")?.addEventListener("click", async () => {
    const response = await eel.startEmotionDetection()();
    if (response && response.message) {
      showToast(response.message);
    }
  });

  byId("saveSettingsBtn")?.addEventListener("click", async () => {
    const cameraIndex = byId("cameraIndexInput")?.value || "0";
    await eel.saveSettings({ driver_monitor_camera_index: String(cameraIndex) })();
    showToast("Settings saved.");
  });

  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nav = button.getAttribute("data-nav");
      if (nav === "home") {
        closeApp();
        return;
      }
      if (nav === "voice") {
        pulseDrivingMode();
        await eel.takeCommand()();
        return;
      }
      if (APP_NAMES.includes(nav || "")) {
        openApp(nav);
      }
    });
  });

  const appShell = byId("appScreen");
  appShell?.addEventListener("touchstart", (event) => {
    state.swipeStartX = event.changedTouches[0].clientX;
  });
  appShell?.addEventListener("touchend", (event) => {
    const delta = event.changedTouches[0].clientX - state.swipeStartX;
    if (Math.abs(delta) < 60 || !state.activeApp) {
      return;
    }
    const idx = APP_NAMES.indexOf(state.activeApp);
    if (idx === -1) {
      return;
    }
    const nextIndex = delta < 0 ? (idx + 1) % APP_NAMES.length : (idx - 1 + APP_NAMES.length) % APP_NAMES.length;
    openApp(APP_NAMES[nextIndex]);
  });

  document.querySelectorAll("[data-action='toggle-lights'], [data-action='toggle-climate']").forEach((button) => {
    button.addEventListener("click", pulseDrivingMode);
  });
}

async function startupSequence() {
  showScreen(SCREENS.startup);
  setMode("ambient");

  await new Promise((resolve) => window.setTimeout(resolve, 2400));
  showScreen(SCREENS.auth);
  setAuthStatus("Starting camera scan...");

  await eel.init()();
  const response = await eel.startFaceAuth()();
  if (response && response.ok === false && response.message) {
    setAuthStatus(response.message);
  }
}

async function refreshSpotifyState() {
  try {
    const statePayload = await eel.getSpotifyState()();
    updateSpotifyUI(statePayload);
  } catch (error) {
    // Ignore connectivity failures and keep UI responsive.
  }
}

function registerEelCallbacks() {
  eel.expose(setAuthStatus);
  eel.expose(updateCameraFrame);
  eel.expose(onFaceAuthSuccess);
  eel.expose(onFaceAuthFailed);
  eel.expose(setSpotifyState);
  eel.expose(setNavigationResult);
  eel.expose(openAppFromBackend);
  eel.expose(closeAppFromBackend);
  eel.expose(setActiveApp);
  eel.expose(setEmotionResult);
}

window.addEventListener("DOMContentLoaded", async () => {
  bindPinPad();
  bindUI();
  setupMaps();
  registerEelCallbacks();
  await startupSequence();
  window.setInterval(updateVehicleSimulation, 1000);
  window.setInterval(refreshSpotifyState, 6000);
});
