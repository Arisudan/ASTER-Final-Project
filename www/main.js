const SCREENS = {
  startup: "startupScreen",
  auth: "authScreen",
  dashboard: "dashboardScreen",
  app: "appScreen",
};

const APP_NAMES = ["music", "spotify", "maps", "calls", "camera", "emotion", "settings"];

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
  spotifyPlaying: false,
  authenticated: false,
  spotifyUser: null,
  spotifyPlaylists: [],
  spotifySavedTracks: [],
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

function setCallsStatus(text) {
  const status = byId("callsStatus");
  if (status) {
    status.textContent = text || "";
  }
}

function setDeviceList(devices) {
  const list = byId("deviceList");
  if (!list) {
    return;
  }

  if (!Array.isArray(devices) || devices.length === 0) {
    list.innerHTML = "<div class=\"device-row\">No active Android devices found.</div>";
    return;
  }

  list.innerHTML = devices
    .map((device) => `<div class=\"device-row\">${device.serial || "unknown"} - ${device.status || "unknown"}</div>`)
    .join("");
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

function showFaceAuthPanel() {
  byId("authCard")?.classList.remove("hidden");
  byId("pinPanel")?.classList.add("hidden");
}

function showPinPanel() {
  byId("authCard")?.classList.add("hidden");
  byId("pinPanel")?.classList.remove("hidden");
}

function setAuthenticated(isAuth) {
  state.authenticated = isAuth;
  const navEl = document.querySelector(".bottom-nav");
  if (navEl) {
    if (isAuth) {
      navEl.classList.remove("hidden");
    } else {
      navEl.classList.add("hidden");
    }
  }
}

async function loadSpotifyDetailAndOpen() {
  try {
    const userResponse = await eel.getSpotifyUserProfile()();
    const playlistsResponse = await eel.getSpotifyUserPlaylists()();
    const savedResponse = await eel.getSpotifyUserSavedTracks()();
    const recentResponse = await eel.getSpotifyRecentlyPlayed()();

    renderSpotifyUserCard(userResponse.user);
    renderPlaylistsList(playlistsResponse.playlists || []);
    renderSavedTracksList(savedResponse.tracks || []);
    renderRecentTracksList(recentResponse.tracks || []);

    openApp("spotify", { syncBackend: false });
  } catch (error) {
    showToast("Unable to load Spotify account details.");
    console.error("Spotify detail loading error:", error);
  }
}

function renderSpotifyUserCard(user) {
  const card = byId("spotifyUserCard");
  if (!card || !user) return;

  const image = user.images && user.images[0] ? user.images[0].url : "";
  card.innerHTML = `
    <div style="display: flex; align-items: center; gap: 12px;">
      ${image ? `<img src="${image}" style="width: 64px; height: 64px; border-radius: 50%; object-fit: cover;" alt="User" />` : ""}
      <div class="spotify-account-info">
        <h5>${user.display_name || "Unknown User"}</h5>
        <p>${user.email || ""}</p>
        <p>${user.followers || 0} followers ${user.premium ? "• Premium" : ""}</p>
      </div>
    </div>
  `;
}

function renderPlaylistsList(playlists) {
  const container = byId("playlistsList");
  if (!container) return;

  if (!playlists || playlists.length === 0) {
    container.innerHTML = "<p style=\"padding: 16px; opacity: 0.7;\">No playlists found.</p>";
    return;
  }

  container.innerHTML = playlists
    .map(
      (p) => `
      <div class="playlist-item">
        ${p.image ? `<img src="${p.image}" alt="${p.name}" />` : '<div style="width: 48px; height: 48px; border-radius: 8px; background: rgba(29, 185, 84, 0.2);"></div>'}
        <div class="playlist-item-info">
          <h6>${p.name}</h6>
          <p class="playlist-count">${p.tracks_total} tracks</p>
          <p>${p.description ? p.description.substring(0, 50) + (p.description.length > 50 ? "..." : "") : "No description"}</p>
        </div>
      </div>
    `
    )
    .join("");
}

function renderSavedTracksList(tracks) {
  const container = byId("savedTracksList");
  if (!container) return;

  if (!tracks || tracks.length === 0) {
    container.innerHTML = "<p style=\"padding: 16px; opacity: 0.7;\">No saved tracks found.</p>";
    return;
  }

  container.innerHTML = tracks
    .map(
      (t) => `
      <div class="track-item">
        ${t.image ? `<img src="${t.image}" alt="${t.name}" />` : '<div style="width: 48px; height: 48px; border-radius: 8px; background: rgba(29, 185, 84, 0.2);"></div>'}
        <div class="track-item-info">
          <h6>${t.name}</h6>
          <p>${t.artists}</p>
          <p style="font-size: 0.75rem; opacity: 0.6;">${t.album}</p>
        </div>
      </div>
    `
    )
    .join("");
}

function renderRecentTracksList(tracks) {
  const container = byId("recentTracksList");
  if (!container) return;

  if (!tracks || tracks.length === 0) {
    container.innerHTML = "<p style=\"padding: 16px; opacity: 0.7;\">No recently played tracks found.</p>";
    return;
  }

  container.innerHTML = tracks
    .map(
      (t) => `
      <div class="track-item">
        ${t.image ? `<img src="${t.image}" alt="${t.name}" />` : '<div style="width: 48px; height: 48px; border-radius: 8px; background: rgba(29, 185, 84, 0.2);"></div>'}
        <div class="track-item-info">
          <h6>${t.name}</h6>
          <p>${t.artists}</p>
          <p style="font-size: 0.75rem; opacity: 0.6;">${t.album}</p>
        </div>
      </div>
    `
    )
    .join("");
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

  if (name === "maps") {
    refreshMapSizes();
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
  setAuthenticated(true);
  showScreen(SCREENS.dashboard);
  showFaceAuthPanel();
}

function onFaceAuthFailed(message) {
  setAuthStatus(message || "Face not recognized. Use PIN fallback.");
  showFaceAuthPanel();
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
  state.spotifyPlaying = Boolean(track.is_playing);

  const playButton = byId("playPauseBtn");
  const fullPlayButton = byId("musicPlayBtn");
  if (playButton) {
    playButton.textContent = state.spotifyPlaying ? "Resume" : "Play";
  }
  if (fullPlayButton) {
    fullPlayButton.textContent = state.spotifyPlaying ? "Resume" : "Play";
  }
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

function refreshMapSizes() {
  window.setTimeout(() => {
    if (state.miniMap) {
      state.miniMap.invalidateSize();
    }
    if (state.fullMap) {
      state.fullMap.invalidateSize();
    }
  }, 180);
}

async function runNavigation(sourceId) {
  const place = byId(sourceId)?.value || "";
  if (!place.trim()) {
    setNavigationResult({ ok: false, message: "Enter a destination to navigate." });
    return;
  }
  const response = await eel.navigateTo(place)();
  setNavigationResult(response);
}

async function refreshAndroidDevices() {
  const response = await eel.getAndroidDevices()();
  if (response && response.ok === false) {
    setCallsStatus(response.message || "Unable to read Android device status.");
    setDeviceList([]);
    return;
  }
  setCallsStatus(response.message || "Device list refreshed.");
  setDeviceList(response.devices || []);
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
  byId("showPinBtn")?.addEventListener("click", showPinPanel);
  byId("pinBackBtn")?.addEventListener("click", showFaceAuthPanel);
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
  byId("expandMusicBtn")?.addEventListener("click", () => loadSpotifyDetailAndOpen());
  byId("expandMapBtn")?.addEventListener("click", () => openApp("maps"));

  byId("playPauseBtn")?.addEventListener("click", async () => {
    const result = state.spotifyPlaying ? await eel.pauseSpotify()() : await eel.playSpotify("")();
    updateSpotifyUI(result);
  });
  byId("prevBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.prevTrack()()));
  byId("nextBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.nextTrack()()));

  byId("musicPlayQueryBtn")?.addEventListener("click", async () => {
    const query = byId("musicQueryInput")?.value || "";
    updateSpotifyUI(await eel.playSpotify(query)());
  });
  byId("musicPlayBtn")?.addEventListener("click", async () => {
    const result = state.spotifyPlaying ? await eel.pauseSpotify()() : await eel.playSpotify("")();
    updateSpotifyUI(result);
  });
  byId("musicPrevBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.prevTrack()()));
  byId("musicNextBtn")?.addEventListener("click", async () => updateSpotifyUI(await eel.nextTrack()()));

  byId("volumeSlider")?.addEventListener("input", (event) => {
    eel.setSpotifyVolume(event.target.value)().catch(() => undefined);
  });

  byId("mapSearchBtn")?.addEventListener("click", () => runNavigation("mapSearchInput"));
  byId("mapFullSearchBtn")?.addEventListener("click", () => runNavigation("mapFullSearchInput"));
  byId("mapSearchInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runNavigation("mapSearchInput");
    }
  });
  byId("mapFullSearchInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runNavigation("mapFullSearchInput");
    }
  });

  byId("spotifyConnectBtn")?.addEventListener("click", async () => {
    const response = await eel.connectSpotify()();
    showToast(response?.message || "Spotify response received.");
    await refreshSpotifyState();
  });
  byId("musicConnectBtn")?.addEventListener("click", async () => {
    const response = await eel.connectSpotify()();
    showToast(response?.message || "Spotify response received.");
    await refreshSpotifyState();
  });
  byId("spotifyPauseBtn")?.addEventListener("click", async () => {
    const response = await eel.pauseSpotify()();
    showToast(response?.message || "Spotify paused.");
    updateSpotifyUI(response);
  });
  byId("musicPauseBtn")?.addEventListener("click", async () => {
    const response = await eel.pauseSpotify()();
    showToast(response?.message || "Spotify paused.");
    updateSpotifyUI(response);
  });

  byId("refreshDevicesBtn")?.addEventListener("click", refreshAndroidDevices);
  byId("openDialerBtn")?.addEventListener("click", async () => {
    const response = await eel.openDialer()();
    setCallsStatus(response?.message || "Dialer response received.");
  });
  byId("dialNumberBtn")?.addEventListener("click", async () => {
    const number = byId("callNumberInput")?.value || "";
    const response = await eel.dialNumber(number)();
    setCallsStatus(response?.message || "Call response received.");
  });
  byId("endCallBtn")?.addEventListener("click", async () => {
    const response = await eel.endCall()();
    setCallsStatus(response?.message || "End call response received.");
  });

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
        if (nav === "maps") {
          refreshMapSizes();
        }
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

  // Spotify detail tab switching
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabName = btn.getAttribute("data-tab");
      if (!tabName) return;

      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));

      btn.classList.add("active");
      const content = byId(`${tabName}TracksList`) || byId(`${tabName}List`);
      if (content) {
        content.classList.remove("hidden");
      }
    });
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
  await refreshAndroidDevices();
  refreshMapSizes();
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
  await refreshSpotifyState();
  window.setInterval(updateVehicleSimulation, 1000);
  window.setInterval(refreshSpotifyState, 6000);
});
