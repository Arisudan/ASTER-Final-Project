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
  regionSelectionMode: false,
  monitorRegionPoints: [],
  lightsOn: false,
  brightness: 0,
  temperature: 22,
  voiceActive: false,
  voiceTranscript: [],
  currentDirections: null,
  navigationActive: false,
  emotion: {
    stage: "Idle",
    confidence: 0,
    sampleCount: 0,
    sampleTarget: 0,
  },
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

function handleSpotifyAction(response, fallbackMessage = "Spotify response received.") {
  if (response?.message) {
    showToast(response.message);
  } else {
    showToast(fallbackMessage);
  }

  if (response?.ok === false) {
    return;
  }

  updateSpotifyUI(response);
}

async function playSpotifyByQuery(query) {
  const text = String(query || "").trim();
  const response = await eel.playSpotify(text)();
  handleSpotifyAction(response, text ? `Playing ${text}` : "Resuming Spotify playback.");
}

async function playSpotifyByUri(uri, fallbackQuery = "") {
  const target = String(uri || "").trim();
  if (target) {
    const response = await eel.playSpotifyUri(target)();
    handleSpotifyAction(response, "Playing selected item.");
    return;
  }
  await playSpotifyByQuery(fallbackQuery);
}

function formatMs(ms) {
  const total = Math.max(0, Math.floor((Number(ms) || 0) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function updateDashboardDateTime() {
  const now = new Date();
  const dayNumber = byId("dashDateNumber");
  const month = byId("dashDateMonth");
  const weekday = byId("dashWeekday");
  const clock = byId("dashClock");

  if (dayNumber) {
    dayNumber.textContent = String(now.getDate());
  }
  if (month) {
    month.textContent = now.toLocaleDateString("en-US", { month: "long" });
  }
  if (weekday) {
    weekday.textContent = now.toLocaleDateString("en-US", { weekday: "long" });
  }
  if (clock) {
    clock.textContent = now.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).toLowerCase();
  }
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

async function submitPin() {
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
    const stateResponse = await eel.getSpotifyState()();
    const userResponse = await eel.getSpotifyUserProfile()();
    const playlistsResponse = await eel.getSpotifyUserPlaylists()();
    const savedResponse = await eel.getSpotifyUserSavedTracks()();
    const recentResponse = await eel.getSpotifyRecentlyPlayed()();

    state.spotifyUser = userResponse?.user || null;
    state.spotifyPlaylists = playlistsResponse?.playlists || [];
    state.spotifySavedTracks = savedResponse?.tracks || [];

    renderSpotifyUserCard(userResponse?.user || null);
    renderPlaylistsList(playlistsResponse.playlists || []);
    renderRecentTracksList(recentResponse.tracks || []);
    renderSavedTracksList(savedResponse.tracks || []);
    updateSpotifyUI(stateResponse || {});

    openApp("spotify", { syncBackend: false });
  } catch (error) {
    showToast("Unable to load Spotify account details.");
    console.error("Spotify detail loading error:", error);
  }
}

function renderSpotifyUserCard(user) {
  const heading = document.querySelector(".spx-content-header h2");
  if (heading) {
    heading.textContent = user?.display_name ? `Good evening, ${user.display_name}` : "Good evening";
  }
}

function _spotifyCardTemplate(item) {
  const title = item?.title || item?.name || "Untitled";
  const subtitle = item?.artist || item?.artists || item?.subtitle || "Spotify";
  const image = item?.cover || item?.image || "https://picsum.photos/300/300?random=300";
  const query = `${title} ${subtitle}`.replace(/"/g, "&quot;");
  const uri = (item?.uri || "").replace(/"/g, "&quot;");
  return `
    <div class="spx-card" data-query="${query}" data-uri="${uri}">
      <img src="${image}" alt="${title} cover" />
      <p class="spx-card-title">${title}</p>
      <p class="spx-card-subtitle">${subtitle}</p>
    </div>
  `;
}

function renderPlaylistsList(playlists) {
  const linksContainer = byId("spxPlaylistLinks");
  const madeForYouGrid = byId("spxMadeForYouGrid");
  if (!linksContainer || !madeForYouGrid) return;

  const list = Array.isArray(playlists) ? playlists : [];
  if (!list.length) {
    linksContainer.innerHTML = "<a href='#'>No playlists yet</a>";
    madeForYouGrid.innerHTML = "";
    return;
  }

  linksContainer.innerHTML = list
    .slice(0, 8)
    .map((p) => `<a href="#" data-query="${(p.name || "").replace(/"/g, "&quot;")}" data-uri="${(p.uri || "").replace(/"/g, "&quot;")}">${p.name || "Playlist"}</a>`)
    .join("");

  madeForYouGrid.innerHTML = list
    .slice(0, 8)
    .map((p) =>
      _spotifyCardTemplate({
        title: p.name,
        subtitle: p.description || `${p.tracks_total || 0} tracks`,
        image: p.image,
        uri: p.uri,
      })
    )
    .join("");
}

function renderSavedTracksList(tracks) {
  const madeForYouGrid = byId("spxMadeForYouGrid");
  if (!madeForYouGrid) return;

  const list = Array.isArray(tracks) ? tracks : [];
  if (!list.length) {
    return;
  }

  // Blend saved tracks into "Made for you" to make section richer.
  const existing = madeForYouGrid.innerHTML;
  const extra = list
    .slice(0, 4)
    .map((t) =>
      _spotifyCardTemplate({
        title: t.name,
        subtitle: t.artists,
        image: t.image,
        uri: t.uri,
      })
    )
    .join("");
  madeForYouGrid.innerHTML = existing + extra;
}

function renderRecentTracksList(tracks) {
  const container = byId("spxRecentlyPlayedGrid");
  if (!container) return;

  const list = Array.isArray(tracks) ? tracks : [];
  if (!list.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = list
    .slice(0, 12)
    .map(
      (t) =>
        _spotifyCardTemplate({
          title: t.name,
          subtitle: t.artists,
          image: t.image,
          uri: t.uri,
        })
    )
    .join("");
}

function openApp(appName, options = {}) {
  const { syncBackend = true, autoStartCamera = true } = options;
  const name = String(appName || "").toLowerCase();
  if (!APP_NAMES.includes(name)) {
    return;
  }

  const appPaneMap = {
    music: "appMusic",
    spotify: "appSpotifyDetail",
    maps: "appMaps",
    calls: "appCalls",
    camera: "appCamera",
    emotion: "appEmotion",
    settings: "appSettings",
  };

  const appTitleMap = {
    music: "Music",
    spotify: "Spotify Account",
    maps: "Maps",
    calls: "Calls",
    camera: "Baby Monitoring",
    emotion: "Emotion AI",
    settings: "Settings",
  };

  state.activeApp = name;
  const title = byId("activeAppTitle");
  if (title) {
    title.textContent = appTitleMap[name] || name.charAt(0).toUpperCase() + name.slice(1);
  }

  byId("appLauncher")?.classList.add("hidden");
  document.querySelectorAll(".app-pane").forEach((pane) => pane.classList.add("hidden"));
  byId(appPaneMap[name])?.classList.remove("hidden");

  showScreen(SCREENS.app);

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
      emotionStatus.textContent = "Capture camera samples and map mood to Spotify.";
    }
    const stageChip = byId("emotionStageChip");
    const confidenceChip = byId("emotionConfidenceChip");
    const sampleChip = byId("emotionSamplesChip");
    const detail = byId("emotionDetail");
    if (stageChip) stageChip.textContent = "Idle";
    if (confidenceChip) confidenceChip.textContent = "Confidence: --";
    if (sampleChip) sampleChip.textContent = "Samples: 0/0";
    if (detail) detail.textContent = "Live camera preview will update while the mood is being analyzed.";
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

  if (owner === "emotion") {
    const emotionFeed = byId("emotionCameraFeed");
    if (emotionFeed) {
      emotionFeed.src = frameDataUrl;
    }
  }
}

function onFaceAuthSuccess(userName) {
  setAuthStatus(`Welcome ${userName || "Driver"}. Access granted.`);
  setAuthenticated(true);
  showScreen(SCREENS.dashboard);
  showFaceAuthPanel();
  announce(`Welcome ${userName || "Driver"}`);
}

function onFaceAuthFailed(message) {
  setAuthStatus(message || "Face not recognized. Use PIN fallback.");
  showFaceAuthPanel();
}

function setEmotionResult(payload) {
  const status = byId("emotionStatus");
  const stageChip = byId("emotionStageChip");
  const confidenceChip = byId("emotionConfidenceChip");
  const sampleChip = byId("emotionSamplesChip");
  const detail = byId("emotionDetail");
  if (!status) {
    return;
  }

  if (!payload || payload.ok === false) {
    const message = payload?.message || "Emotion detection failed.";
    status.textContent = message;
    if (stageChip) stageChip.textContent = "Error";
    if (confidenceChip) confidenceChip.textContent = "Confidence: --";
    if (sampleChip) sampleChip.textContent = "Samples: 0/0";
    if (detail) detail.textContent = message;
    return;
  }

  const stage = payload.stage === "done" ? "Detected" : "Analyzing";
  const emotionLabel = String(payload.smoothed_emotion || payload.emotion || "neutral");
  const confidence = Number(payload.confidence || 0);
  const sampleCount = Number(payload.sample_count || 0);
  const sampleTarget = Number(payload.sample_target || 0);

  state.emotion = {
    stage,
    confidence,
    sampleCount,
    sampleTarget,
  };

  status.textContent = payload.message || `Emotion: ${emotionLabel}`;
  if (stageChip) stageChip.textContent = stage;
  if (confidenceChip) confidenceChip.textContent = `Confidence: ${Math.round(confidence * 100)}%`;
  if (sampleChip) sampleChip.textContent = `Samples: ${sampleCount}/${sampleTarget || "?"}`;
  if (detail) {
    const autoplayText = payload.stage === "done"
      ? (payload.message || payload.spotify?.message || "Emotion analysis completed.")
      : `Live emotion: ${emotionLabel}.`;
    detail.textContent = autoplayText;
  }
}

function setBabyMonitorState(payload) {
  if (!payload) {
    return;
  }

  const status = byId("babyMonitorStatus");
  if (status) {
    status.textContent = payload.message || "Baby monitor active.";
  }

  const wakeBadge = byId("wakeBadge");
  const moveBadge = byId("moveBadge");
  const outsideBadge = byId("outsideBadge");

  if (wakeBadge) {
    wakeBadge.textContent = `Wake: ${payload.wake_up ? "YES" : "NO"}`;
    wakeBadge.classList.toggle("monitor-badge--active", Boolean(payload.wake_up));
  }
  if (moveBadge) {
    moveBadge.textContent = `Movement: ${payload.moving ? "YES" : "NO"}`;
    moveBadge.classList.toggle("monitor-badge--active", Boolean(payload.moving));
  }
  if (outsideBadge) {
    outsideBadge.textContent = `Region: ${payload.outside ? "OUTSIDE" : "INSIDE"}`;
    outsideBadge.classList.toggle("monitor-badge--alert", Boolean(payload.outside));
  }
}

function activateSpotifyTab(tabName) {
  // Retained as no-op for backward compatibility with older flows.
  return tabName;
}

function updateSettingsInputs(settings) {
  const data = settings || {};
  const setVal = (id, value) => {
    const el = byId(id);
    if (!el || value === undefined || value === null) return;
    el.value = String(value);
  };

  setVal("securityPinInput", data.security_pin || "");
  setVal("faceTimeoutInput", data.face_auth_timeout_seconds || 24);
  setVal("wakeWordEnabledInput", data.wake_word_enabled || "true");
  setVal("speechRateInput", data.speech_rate || 180);
  setVal("emotionAutoPlayEnabledInput", data.emotion_auto_play_enabled || "true");
  setVal("emotionConfidenceThresholdInput", data.emotion_confidence_threshold || 0.6);
  setVal("emotionSampleCountInput", data.emotion_sample_count || 12);
  setVal("emotionSampleIntervalInput", data.emotion_sample_interval_seconds || 0.18);
  setVal("spotifyAutoConnectInput", data.spotify_auto_connect || "false");
  setVal("androidSerialInput", data.android_device_serial || "");
  setVal("babyDlEnabledInput", data.baby_monitor_dl_enabled || "true");
  setVal("babyEyeThresholdInput", data.baby_eye_ear_threshold || 0.18);
  setVal("babyMotionThresholdInput", data.baby_motion_threshold || 0.012);
  setVal("babyOutsideFramesInput", data.baby_outside_frames || 8);
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
  const detailPlayButton = byId("spotifyDetailPlayPauseBtn");
  if (playButton) {
    playButton.textContent = state.spotifyPlaying ? "Resume" : "Play";
  }
  if (fullPlayButton) {
    fullPlayButton.textContent = state.spotifyPlaying ? "Resume" : "Play";
  }
  if (detailPlayButton) {
    detailPlayButton.innerHTML = state.spotifyPlaying
      ? '<i class="fas fa-pause-circle"></i>'
      : '<i class="fas fa-play-circle"></i>';
  }

  const spxTitle = byId("spxNowTitle");
  const spxArtist = byId("spxNowArtist");
  const spxArt = byId("spxNowArt");
  const currentTime = byId("spxCurrentTime");
  const totalTime = byId("spxTotalTime");
  const progress = byId("spxProgress");

  if (spxTitle) spxTitle.textContent = track.title || "Song Title";
  if (spxArtist) spxArtist.textContent = track.artist || "Artist Name";
  if (spxArt && track.image) spxArt.src = track.image;
  if (currentTime) currentTime.textContent = formatMs(track.progress_ms || 0);
  if (totalTime) totalTime.textContent = formatMs(track.duration_ms || 0);
  if (progress) {
    const ratio = track.duration_ms ? Math.max(0, Math.min(100, (100 * (track.progress_ms || 0)) / track.duration_ms)) : 0;
    progress.style.width = `${ratio}%`;
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

  // Show turn-by-turn directions
  if (payload.destination) {
    const dest = payload.destination.name || "Destination";
    const distance = payload.route.length * 1.2; // Rough distance estimate in km
    showDirections({
      destination: dest,
      total_distance: `${(distance / 1000).toFixed(1)} km`,
      eta: "~" + Math.ceil(distance / 60) + " min",
      current_instruction: `Start towards ${dest}`,
      next_instruction: "Follow the route on map",
    });
  }
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

function updateLightsUI() {
  const btn = byId("lightsToggleBtn");
  const slider = byId("brightnessSlider");
  const status = byId("lightsStatus");
  const value = byId("brightnessValue");

  if (btn) btn.textContent = state.lightsOn ? "Turn Off" : "Turn On";
  if (slider) slider.value = state.brightness;
  if (value) value.textContent = `${state.brightness}%`;
  if (status) {
    status.textContent = state.lightsOn ? "ON" : "OFF";
    status.style.background = state.lightsOn ? "rgba(29, 185, 84, 0.2)" : "rgba(255, 255, 255, 0.1)";
    status.style.color = state.lightsOn ? "#1db954" : "var(--text-muted)";
  }
}

function updateClimateUI() {
  const slider = byId("temperatureSlider");
  const status = byId("climateStatus");
  const value = byId("tempValue");

  if (slider) slider.value = state.temperature;
  if (status) status.textContent = `${state.temperature}°C`;
  if (value) value.textContent = `${state.temperature}°C`;
}

function updateVoiceUI() {
  const btn = byId("startListeningBtn");
  const dot = byId("voiceStatus");

  if (btn) btn.textContent = state.voiceActive ? "Stop Listening" : "Start Listening";
  if (dot) {
    dot.classList.toggle("active", state.voiceActive);
  }
}

function addVoiceMessage(type, message) {
  const transcript = byId("voiceTranscript");
  if (!transcript) return;

  const messageEl = document.createElement("p");
  messageEl.className = `transcript-message ${type}`;
  messageEl.textContent = message;

  transcript.appendChild(messageEl);
  transcript.scrollTop = transcript.scrollHeight;

  state.voiceTranscript.push({ type, message, timestamp: Date.now() });
}

function showDirections(directions) {
  if (!directions) return;

  state.currentDirections = directions;
  state.navigationActive = true;

  const panel = byId("directionsPanel");
  if (panel) panel.classList.remove("hidden");

  const currentInst = byId("currentInstruction");
  const currentDist = byId("currentDistance");
  const nextInst = byId("nextInstruction");
  const etaDisplay = byId("etaDisplay");
  const totalDist = byId("totalDistanceDisplay");

  if (currentInst) currentInst.textContent = directions.current_instruction || "Navigate...";
  if (currentDist) currentDist.textContent = directions.current_distance || "—";
  if (nextInst) nextInst.textContent = directions.next_instruction || "Continue";
  if (etaDisplay) etaDisplay.textContent = directions.eta || "—";
  if (totalDist) totalDist.textContent = directions.total_distance || "—";
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
    await submitPin();
  });

  document.addEventListener("keydown", async (event) => {
    const pinPanel = byId("pinPanel");
    if (!pinPanel || pinPanel.classList.contains("hidden")) {
      return;
    }

    if (/^\d$/.test(event.key)) {
      if (state.pinInput.length < 4) {
        state.pinInput += event.key;
        updatePinDots();
      }
      return;
    }

    if (event.key === "Backspace") {
      state.pinInput = state.pinInput.slice(0, -1);
      updatePinDots();
      return;
    }

    if (event.key === "Enter") {
      await submitPin();
      return;
    }

    if (event.key === "Escape") {
      showFaceAuthPanel();
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
    handleSpotifyAction(result, "Spotify updated.");
  });
  byId("prevBtn")?.addEventListener("click", async () => handleSpotifyAction(await eel.prevTrack()(), "Previous track."));
  byId("nextBtn")?.addEventListener("click", async () => handleSpotifyAction(await eel.nextTrack()(), "Next track."));

  byId("musicPlayQueryBtn")?.addEventListener("click", async () => {
    const query = byId("musicQueryInput")?.value || "";
    await playSpotifyByQuery(query);
  });
  byId("musicPlayBtn")?.addEventListener("click", async () => {
    const result = state.spotifyPlaying ? await eel.pauseSpotify()() : await eel.playSpotify("")();
    handleSpotifyAction(result, "Spotify updated.");
  });
  byId("musicPrevBtn")?.addEventListener("click", async () => handleSpotifyAction(await eel.prevTrack()(), "Previous track."));
  byId("musicNextBtn")?.addEventListener("click", async () => handleSpotifyAction(await eel.nextTrack()(), "Next track."));

  byId("spotifyDetailPlayBtn")?.addEventListener("click", async () => {
    const query = byId("spotifyDetailQueryInput")?.value || "";
    await playSpotifyByQuery(query);
  });
  byId("spotifyDetailConnectBtn")?.addEventListener("click", async () => {
    const response = await eel.connectSpotify()();
    showToast(response?.message || "Spotify response received.");
    await refreshSpotifyState();
    await loadSpotifyDetailAndOpen();
  });
  byId("spotifyDetailPlayPauseBtn")?.addEventListener("click", async () => {
    const result = state.spotifyPlaying ? await eel.pauseSpotify()() : await eel.playSpotify("")();
    handleSpotifyAction(result, "Spotify updated.");
  });
  byId("spotifyDetailPrevBtn")?.addEventListener("click", async () => handleSpotifyAction(await eel.prevTrack()(), "Previous track."));
  byId("spotifyDetailNextBtn")?.addEventListener("click", async () => handleSpotifyAction(await eel.nextTrack()(), "Next track."));
  byId("spotifyDetailVolumeSlider")?.addEventListener("input", (event) => {
    eel.setSpotifyVolume(event.target.value)().catch(() => undefined);
  });

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

  byId("setRegionBtn")?.addEventListener("click", () => {
    state.regionSelectionMode = true;
    state.monitorRegionPoints = [];
    showToast("Region selection enabled. Click 4 points on baby camera feed.");
  });

  byId("resetRegionBtn")?.addEventListener("click", async () => {
    const resetPolygon = [
      [0.08, 0.12],
      [0.92, 0.12],
      [0.92, 0.92],
      [0.08, 0.92],
    ];
    await eel.setBabyMonitorRegion(resetPolygon)();
    showToast("Monitoring region reset.");
  });

  byId("babyCameraFeed")?.addEventListener("click", async (event) => {
    if (!state.regionSelectionMode) {
      return;
    }

    const image = event.currentTarget;
    const rect = image.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    state.monitorRegionPoints.push([x, y]);

    if (state.monitorRegionPoints.length >= 4) {
      await eel.setBabyMonitorRegion(state.monitorRegionPoints)();
      state.regionSelectionMode = false;
      showToast("Monitoring region saved.");
    } else {
      showToast(`Point ${state.monitorRegionPoints.length}/4 set.`);
    }
  });

  byId("stopCameraBtn")?.addEventListener("click", async () => {
    const response = await eel.stopCamera()();
    if (response && response.message) {
      showToast(response.message);
    }
  });

  byId("startEmotionBtn")?.addEventListener("click", async () => {
    console.log("Emotion detection button clicked");
    try {
      if (!window.eel) {
        showToast("Error: Eel backend not available");
        console.error("Eel not available");
        return;
      }
      console.log("Calling startEmotionDetection...");
      const response = await eel.startEmotionDetection()();
      console.log("Response received:", response);
      if (response && response.message) {
        showToast(response.message);
      } else {
        showToast("Emotion detection started");
      }
    } catch (error) {
      console.error("Error starting emotion detection:", error);
      showToast("Error: " + (error.message || "Failed to start emotion detection"));
    }
  });

  byId("saveSettingsBtn")?.addEventListener("click", async () => {
    const payload = {
      security_pin: byId("securityPinInput")?.value || "2468",
      face_auth_timeout_seconds: byId("faceTimeoutInput")?.value || "24",
      wake_word_enabled: byId("wakeWordEnabledInput")?.value || "true",
      speech_rate: byId("speechRateInput")?.value || "180",
      emotion_auto_play_enabled: byId("emotionAutoPlayEnabledInput")?.value || "true",
      emotion_confidence_threshold: byId("emotionConfidenceThresholdInput")?.value || "0.60",
      emotion_sample_count: byId("emotionSampleCountInput")?.value || "12",
      emotion_sample_interval_seconds: byId("emotionSampleIntervalInput")?.value || "0.18",
      spotify_auto_connect: byId("spotifyAutoConnectInput")?.value || "false",
      android_device_serial: byId("androidSerialInput")?.value || "",
      baby_monitor_dl_enabled: byId("babyDlEnabledInput")?.value || "true",
      baby_eye_ear_threshold: byId("babyEyeThresholdInput")?.value || "0.18",
      baby_motion_threshold: byId("babyMotionThresholdInput")?.value || "0.012",
      baby_outside_frames: byId("babyOutsideFramesInput")?.value || "8",
    };
    await eel.saveSettings(payload)();
    showToast("Settings saved.");
  });

  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nav = button.getAttribute("data-nav");
      if (nav === "home") {
        closeApp();
        return;
      }
      if (nav === "launcher") {
        state.activeApp = "";
        byId("activeAppTitle").textContent = "Apps";
        byId("appLauncher")?.classList.remove("hidden");
        document.querySelectorAll(".app-pane").forEach((pane) => pane.classList.add("hidden"));
        showScreen(SCREENS.app);
        return;
      }
      if (nav === "navigation") {
        openApp("maps");
        refreshMapSizes();
        return;
      }
      if (nav === "contacts") {
        openApp("calls");
        return;
      }
      if (nav === "voice") {
        await eel.takeCommand()();
        return;
      }
      if (nav === "music") {
        await loadSpotifyDetailAndOpen();
        announce("Opened spotify");
        return;
      }
      if (APP_NAMES.includes(nav || "")) {
        openApp(nav);
        if (nav === "maps") {
          refreshMapSizes();
        }
      }
      announce(`Opened ${nav}`);
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

  // Lights control
  byId("lightsToggleBtn")?.addEventListener("click", () => {
    state.lightsOn = !state.lightsOn;
    if (state.lightsOn) {
      state.brightness = Math.max(20, state.brightness);
    } else {
      state.brightness = 0;
    }
    updateLightsUI();
  });

  byId("brightnessSlider")?.addEventListener("input", (e) => {
    state.brightness = parseInt(e.target.value);
    if (state.brightness > 0) {
      state.lightsOn = true;
    }
    updateLightsUI();
  });

  // Climate control
  byId("temperatureSlider")?.addEventListener("input", (e) => {
    state.temperature = parseInt(e.target.value);
    updateClimateUI();
  });

  byId("tempUp")?.addEventListener("click", () => {
    if (state.temperature < 30) {
      state.temperature += 1;
      updateClimateUI();
    }
  });

  byId("tempDown")?.addEventListener("click", () => {
    if (state.temperature > 16) {
      state.temperature -= 1;
      updateClimateUI();
    }
  });

  // Voice assistant
  byId("startListeningBtn")?.addEventListener("click", () => {
    state.voiceActive = !state.voiceActive;
    updateVoiceUI();
    if (state.voiceActive) {
      addVoiceMessage("listening", "Listening...");
      setTimeout(() => {
        addVoiceMessage("assistant", "Hello! I'm ready to help. What can I do for you?");
        state.voiceActive = false;
        updateVoiceUI();
      }, 2000);
    }
  });

  // Map directions
  byId("closeDirectionsBtn")?.addEventListener("click", () => {
    state.navigationActive = false;
    byId("directionsPanel")?.classList.add("hidden");
  });

  ["spxRecentlyPlayedGrid", "spxMadeForYouGrid"].forEach((id) => {
    byId(id)?.addEventListener("click", async (event) => {
      const row = event.target.closest(".spx-card");
      if (!row) return;
      const query = row.getAttribute("data-query") || "";
      const uri = row.getAttribute("data-uri") || "";
      await playSpotifyByUri(uri, query);
    });
  });

  byId("spxPlaylistLinks")?.addEventListener("click", async (event) => {
    const link = event.target.closest("a");
    if (!link) return;
    event.preventDefault();
    const query = link.getAttribute("data-query") || "";
    const uri = link.getAttribute("data-uri") || "";
    await playSpotifyByUri(uri, query);
  });

  byId("spotifyDetailQueryInput")?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    const query = byId("spotifyDetailQueryInput")?.value || "";
    if (!query.trim()) return;
    await playSpotifyByQuery(query);
  });
}

async function startupSequence() {
  showScreen(SCREENS.startup);
  updateDashboardDateTime();

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

async function loadSettingsToUI() {
  try {
    const settings = await eel.getSettings()();
    updateSettingsInputs(settings || {});
    if (String(settings?.spotify_auto_connect || "false").toLowerCase() === "true") {
      await eel.connectSpotify()();
    }
  } catch (error) {
    showToast("Unable to load settings.");
  }
}

async function refreshBabyMonitorState() {
  try {
    const statePayload = await eel.getBabyMonitorState()();
    setBabyMonitorState(statePayload);
  } catch (error) {
    // Keep UI responsive if camera system is not ready.
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
  eel.expose(setBabyMonitorState);
  eel.expose(showDirections);
}

window.addEventListener("DOMContentLoaded", async () => {
  bindPinPad();
  bindUI();
  setupMaps();
  registerEelCallbacks();
  await startupSequence();
  await loadSettingsToUI();
  await refreshSpotifyState();
  await refreshBabyMonitorState();
  window.setInterval(updateDashboardDateTime, 30000);
  window.setInterval(refreshSpotifyState, 6000);
  window.setInterval(refreshBabyMonitorState, 2000);
});
