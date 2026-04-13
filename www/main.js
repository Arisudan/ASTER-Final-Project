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
  voiceCaptureSession: false,
  currentDirections: null,
  navigationActive: false,
  emotion: {
    stage: "Idle",
    confidence: 0,
    sampleCount: 0,
    sampleTarget: 0,
  },
};

const assistantWave = {
  instance: null,
  initialized: false,
  mode: "idle",
};

const legacyAssistantWave = {
  instance: null,
  initialized: false,
};

function showSiriWave() {
  const oval = byId("Oval");
  const siri = byId("SiriWave");
  if (oval) {
    oval.hidden = true;
  }
  if (siri) {
    siri.hidden = false;
  }
}

function ShowHood() {
  const oval = byId("Oval");
  const siri = byId("SiriWave");
  if (oval) {
    oval.hidden = false;
  }
  if (siri) {
    siri.hidden = true;
  }
}

function DisplayMessage(message) {
  const node = byId("legacySiriMessage");
  if (node) {
    node.textContent = String(message || "");
  }
}

function senderText(message) {
  if (!message) {
    return;
  }
  setAssistantHeardQuery(message);
}

function receiverText(message) {
  if (!message) {
    return;
  }
  setAssistantResponse(message);
}

function hideLoader() {
  const loader = byId("Loader");
  if (loader) {
    loader.classList.add("hidden");
  }
  setFaceAuthVisual("auth");
}

function hideFaceAuth() {
  setFaceAuthVisual("success");
}

function hideFaceAuthSuccess() {
  setFaceAuthVisual("greet");
}

function hideStart() {
  showScreen(SCREENS.dashboard);
  ShowHood();
}

function setSiriWaveVisualMode(mode) {
  const wave = byId("siriWave");
  if (!wave) {
    return;
  }
  wave.classList.remove("is-idle", "is-listening", "is-processing");
  wave.classList.add(`is-${mode}`);
}

function byId(id) {
  return document.getElementById(id);
}

function announce(message) {
  const live = byId("liveRegion");
  if (live) {
    live.textContent = message || "";
  }
}

function setAssistantResponse(text) {
  const responseText = String(text || "").trim();
  const replyEl = byId("jarvisReply");
  if (replyEl) {
    replyEl.textContent = responseText;
  }

  if (state.voiceCaptureSession && responseText && responseText.toLowerCase() !== "thinking...") {
    addVoiceMessage("assistant", responseText);
    state.voiceCaptureSession = false;
    state.voiceActive = false;
    updateVoiceUI();
    ShowHood();
  }
}

function setAssistantHeardQuery(text) {
  const heardText = String(text || "").trim();
  const queryEl = byId("hotwordQuery");
  if (queryEl) {
    queryEl.textContent = heardText || "Say your command";
  }

  if (state.voiceCaptureSession && heardText) {
    addVoiceMessage("user", heardText);
  }
}

function beginVoiceCaptureSession() {
  state.voiceCaptureSession = true;
  state.voiceActive = true;
  updateVoiceUI();
  addVoiceMessage("listening", "Listening...");
  showSiriWave();
}

function ensureSiriWave() {
  if (assistantWave.initialized) {
    return;
  }

  const container = byId("siriWave");
  if (!container) {
    return;
  }

  const SiriWaveCtor = window.SiriWave;
  if (typeof SiriWaveCtor !== "function") {
    return;
  }

  try {
    assistantWave.instance = new SiriWaveCtor({
      container,
      width: 640,
      height: 200,
      style: "ios9",
      autostart: true,
      speed: 0.09,
      amplitude: 0.09,
    });
    assistantWave.initialized = true;
    setSiriWaveVisualMode("idle");
  } catch (error) {
    assistantWave.instance = null;
    assistantWave.initialized = false;
  }
}

function ensureLegacySiriWave() {
  if (legacyAssistantWave.initialized) {
    return;
  }

  const container = byId("legacySiriContainer");
  const SiriWaveCtor = window.SiriWave;
  if (!container || typeof SiriWaveCtor !== "function") {
    return;
  }

  try {
    legacyAssistantWave.instance = new SiriWaveCtor({
      container,
      width: Math.min(window.innerWidth * 0.9, 800),
      height: 200,
      style: "ios9",
      amplitude: 1,
      speed: 0.3,
      autostart: true,
    });
    legacyAssistantWave.initialized = true;
  } catch (error) {
    legacyAssistantWave.instance = null;
    legacyAssistantWave.initialized = false;
  }
}

function applySiriWaveMode(mode) {
  ensureSiriWave();
  if (!assistantWave.instance) {
    return;
  }

  if (mode === "listening") {
    assistantWave.instance.setSpeed(0.16);
    assistantWave.instance.setAmplitude(1.12);
  } else if (mode === "processing") {
    assistantWave.instance.setSpeed(0.11);
    assistantWave.instance.setAmplitude(0.52);
  } else {
    assistantWave.instance.setSpeed(0.09);
    assistantWave.instance.setAmplitude(0.1);
  }
  assistantWave.mode = mode;
  setSiriWaveVisualMode(mode);
}

function startWaveMeter() {
  applySiriWaveMode("listening");
}

function stopWaveMeter() {
  applySiriWaveMode("idle");
}

function setAssistantListeningState(mode) {
  const wave = byId("siriWave");
  if (!wave) {
    return;
  }

  if (mode === "listening") {
    startWaveMeter();
  } else if (mode === "processing") {
    applySiriWaveMode("processing");
  } else {
    stopWaveMeter();
  }
}

function setHotwordOverlayState(isActive, hotword = "jarvis") {
  const overlay = byId("hotwordOverlay");
  const label = byId("hotwordLabel");
  const query = byId("hotwordQuery");
  if (!overlay) {
    return;
  }

  if (isActive) {
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    if (label) {
      label.textContent = "ASTER ready";
    }
    if (query) {
      query.textContent = "Say your command";
    }
    setAssistantListeningState("listening");
    showSiriWave();
  } else {
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
    setAssistantListeningState("idle");
    stopWaveMeter();
    ShowHood();
  }
}

async function submitDashboardPrompt(prompt, source = "typed") {
  const query = String(prompt || "").trim();
  if (!query) {
    return;
  }

  const input = byId("jarvisChatInput");
  if (input) {
    input.value = "";
    input.disabled = true;
  }
  setAssistantResponse("Thinking...");

  try {
    const result = await eel.askDashboardAssistant(query, source)();
    const response = result?.response || "No response received.";
    setAssistantResponse(response);
  } catch (error) {
    setAssistantResponse("Unable to reach assistant right now.");
  } finally {
    if (input) {
      input.disabled = false;
      input.focus();
    }
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
    month.textContent = now.toLocaleDateString("en-US", { month: "long", year: "numeric" });
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

  if (state.voiceCaptureSession && String(text || "").includes("Voice command not detected")) {
    addVoiceMessage("system", "Voice command not detected.");
    state.voiceCaptureSession = false;
    state.voiceActive = false;
    updateVoiceUI();
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

function setFaceAuthVisual(stage) {
  const faceAuth = byId("FaceAuth");
  const faceAuthSuccess = byId("FaceAuthSuccess");
  const helloGreet = byId("HelloGreet");

  if (faceAuth) faceAuth.classList.toggle("hidden", stage !== "auth");
  if (faceAuthSuccess) faceAuthSuccess.classList.toggle("hidden", stage !== "success");
  if (helloGreet) helloGreet.classList.toggle("hidden", stage !== "greet");
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

  // Hide bottom nav for Spotify player
  const bottomNav = document.querySelector(".bottom-nav");
  if (name === "spotify" && bottomNav) {
    bottomNav.classList.add("hidden");
  } else if (bottomNav) {
    bottomNav.classList.remove("hidden");
  }

  showScreen(SCREENS.app);

  if (window.eel && syncBackend) {
    eel.openApp(name)().catch(() => undefined);
  }

  if (window.eel && name === "camera" && autoStartCamera) {
    eel.startBabyMonitoring()().then((response) => {
      if (response && response.ok === false && response.message) {
        showToast(response.message);
      }
      loadBabyRegionFromBackend();
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
  
  // Show bottom nav when returning to dashboard
  const bottomNav = document.querySelector(".bottom-nav");
  if (bottomNav) {
    bottomNav.classList.remove("hidden");
  }
  
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
  byId("authCard")?.classList.add("hidden");
  byId("pinPanel")?.classList.add("hidden");
  setFaceAuthVisual("success");
  announce(`Welcome ${userName || "Driver"}`);

  window.setTimeout(() => {
    setFaceAuthVisual("greet");
    window.setTimeout(() => {
      showScreen(SCREENS.dashboard);
      setFaceAuthVisual("auth");
    }, 1200);
  }, 900);
}

function onFaceAuthFailed(message) {
  setAuthStatus(message || "Face not recognized. Use PIN fallback.");
  setFaceAuthVisual("auth");
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
  const stageName = payload.stage === "monitoring"
    ? "Monitoring"
    : (payload.stage === "done" ? "Detected" : "Analyzing");
  const emotionLabel = String(payload.smoothed_emotion || payload.emotion || "neutral");
  const confidence = Number(payload.confidence || 0);
  const sampleCount = Number(payload.sample_count || 0);
  const sampleTarget = Number(payload.sample_target || 0);

  state.emotion = {
    stage: stageName,
    confidence,
    sampleCount,
    sampleTarget,
  };

  status.textContent = payload.message || `Emotion: ${emotionLabel}`;
  if (stageChip) stageChip.textContent = stageName;
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
  const wakeBadgeValue = byId("wakeBadgeValue");
  const moveBadgeValue = byId("moveBadgeValue");
  const outsideBadgeValue = byId("outsideBadgeValue");

  if (wakeBadge) {
    wakeBadge.classList.toggle("monitor-badge--active", Boolean(payload.wake_up));
  }
  if (wakeBadgeValue) {
    wakeBadgeValue.textContent = payload.wake_up ? "YES" : "NO";
  }

  if (moveBadge) {
    moveBadge.classList.toggle("monitor-badge--active", Boolean(payload.moving));
  }
  if (moveBadgeValue) {
    moveBadgeValue.textContent = payload.moving ? "YES" : "NO";
  }

  if (outsideBadge) {
    outsideBadge.classList.toggle("monitor-badge--alert", Boolean(payload.outside));
  }
  if (outsideBadgeValue) {
    outsideBadgeValue.textContent = payload.outside ? "OUTSIDE" : "INSIDE";
  }
}

function renderBabyRegionOverlay(points = [], isPending = false) {
  const overlay = byId("babyRegionOverlay");
  if (!overlay) {
    return;
  }

  const safePoints = Array.isArray(points)
    ? points.filter((pt) => Array.isArray(pt) && pt.length === 2)
    : [];

  if (!safePoints.length) {
    overlay.innerHTML = "";
    return;
  }

  const coords = safePoints
    .map((pt) => {
      const x = Math.max(0, Math.min(1, Number(pt[0] || 0)));
      const y = Math.max(0, Math.min(1, Number(pt[1] || 0)));
      return `${(x * 100).toFixed(2)},${(y * 100).toFixed(2)}`;
    })
    .join(" ");

  const pointDots = safePoints
    .map((pt) => {
      const x = Math.max(0, Math.min(1, Number(pt[0] || 0))) * 100;
      const y = Math.max(0, Math.min(1, Number(pt[1] || 0))) * 100;
      return `<circle class="region-overlay__point" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="1.2"></circle>`;
    })
    .join("");

  const polygonTag = safePoints.length >= 3
    ? `<polygon class="region-overlay__poly" points="${coords}" ${isPending ? 'stroke-dasharray="2 2"' : ""}></polygon>`
    : `<polyline class="region-overlay__poly" points="${coords}" fill="none" stroke-dasharray="2 2"></polyline>`;

  overlay.innerHTML = `${polygonTag}${pointDots}`;
}

function setRegionSelectionMode(enabled) {
  state.regionSelectionMode = Boolean(enabled);
  const frame = document.querySelector(".camera-frame--baby");
  const setRegionBtn = byId("setRegionBtn");
  frame?.classList.toggle("region-selection-active", state.regionSelectionMode);
  if (setRegionBtn) {
    setRegionBtn.textContent = state.regionSelectionMode ? "Cancel Region" : "Set Region";
  }

  if (!state.regionSelectionMode) {
    state.monitorRegionPoints = [];
  }
}

function getNormalizedImagePoint(event, image) {
  const rect = image.getBoundingClientRect();
  const naturalWidth = Number(image.naturalWidth || 0);
  const naturalHeight = Number(image.naturalHeight || 0);

  let renderedWidth = rect.width;
  let renderedHeight = rect.height;
  let offsetX = 0;
  let offsetY = 0;

  if (naturalWidth > 0 && naturalHeight > 0) {
    const imageRatio = naturalWidth / naturalHeight;
    const boxRatio = rect.width / rect.height;
    if (imageRatio > boxRatio) {
      renderedWidth = rect.width;
      renderedHeight = rect.width / imageRatio;
      offsetY = (rect.height - renderedHeight) / 2;
    } else {
      renderedHeight = rect.height;
      renderedWidth = rect.height * imageRatio;
      offsetX = (rect.width - renderedWidth) / 2;
    }
  }

  const insideX = event.clientX - rect.left - offsetX;
  const insideY = event.clientY - rect.top - offsetY;
  if (insideX < 0 || insideY < 0 || insideX > renderedWidth || insideY > renderedHeight) {
    return null;
  }

  const x = Math.max(0, Math.min(1, insideX / renderedWidth));
  const y = Math.max(0, Math.min(1, insideY / renderedHeight));
  return [x, y];
}

async function loadBabyRegionFromBackend() {
  try {
    const response = await eel.getBabyMonitorRegion()();
    if (response?.ok && Array.isArray(response.points)) {
      renderBabyRegionOverlay(response.points);
    }
  } catch (error) {
    // Keep UI responsive even when backend call fails.
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
  setVal("emotionConfidenceThresholdInput", data.emotion_confidence_threshold || 0.55);
  setVal("emotionSampleCountInput", data.emotion_sample_count || 10);
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
    await loadBabyRegionFromBackend();
  });

  byId("setRegionBtn")?.addEventListener("click", async () => {
    if (state.regionSelectionMode) {
      setRegionSelectionMode(false);
      await loadBabyRegionFromBackend();
      showToast("Region selection cancelled.");
      return;
    }

    setRegionSelectionMode(true);
    state.monitorRegionPoints = [];
    renderBabyRegionOverlay(state.monitorRegionPoints, true);
    showToast("Region selection enabled. Click 4 points on camera feed.");
  });

  byId("resetRegionBtn")?.addEventListener("click", async () => {
    const resetPolygon = [
      [0.08, 0.12],
      [0.92, 0.12],
      [0.92, 0.92],
      [0.08, 0.92],
    ];
    const response = await eel.setBabyMonitorRegion(resetPolygon)();
    setRegionSelectionMode(false);
    renderBabyRegionOverlay(response?.points || resetPolygon);
    showToast(response?.message || "Monitoring region reset.");
  });

  byId("babyRegionOverlay")?.addEventListener("click", async (event) => {
    if (!state.regionSelectionMode) {
      return;
    }

    const image = byId("babyCameraFeed");
    if (!image) {
      return;
    }

    const normalizedPoint = getNormalizedImagePoint(event, image);
    if (!normalizedPoint) {
      showToast("Click inside the visible camera image area.");
      return;
    }

    state.monitorRegionPoints.push(normalizedPoint);
    renderBabyRegionOverlay(state.monitorRegionPoints, true);

    if (state.monitorRegionPoints.length >= 4) {
      const response = await eel.setBabyMonitorRegion(state.monitorRegionPoints)();
      setRegionSelectionMode(false);
      renderBabyRegionOverlay(response?.points || state.monitorRegionPoints);
      showToast(response?.message || "Monitoring region saved.");
    } else {
      showToast(`Point ${state.monitorRegionPoints.length}/4 set.`);
    }
  });

  byId("stopCameraBtn")?.addEventListener("click", async () => {
    const response = await eel.stopCamera()();
    if (response && response.message) {
      showToast(response.message);
    }
    await loadBabyRegionFromBackend();
  });

  byId("startEmotionMonitorBtn")?.addEventListener("click", async () => {
    try {
      const response = await eel.startEmotionMonitoring()();
      showToast(response?.message || "Emotion camera monitoring started.");
    } catch (error) {
      showToast("Failed to start emotion monitoring.");
    }
  });

  byId("stopEmotionMonitorBtn")?.addEventListener("click", async () => {
    try {
      const response = await eel.stopEmotionMonitoring()();
      showToast(response?.message || "Emotion camera monitoring stopped.");
    } catch (error) {
      showToast("Failed to stop emotion monitoring.");
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
      emotion_confidence_threshold: byId("emotionConfidenceThresholdInput")?.value || "0.55",
      emotion_sample_count: byId("emotionSampleCountInput")?.value || "10",
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
        beginVoiceCaptureSession();
        setHotwordOverlayState(true, "jarvis");
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
  byId("startListeningBtn")?.addEventListener("click", async () => {
    beginVoiceCaptureSession();
    setHotwordOverlayState(true, "jarvis");
    try {
      await eel.takeCommand()();
    } catch (error) {
      setHotwordOverlayState(false, "");
      state.voiceCaptureSession = false;
      state.voiceActive = false;
      updateVoiceUI();
      addVoiceMessage("system", "Unable to start voice capture.");
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

  // Spotify search with debouncing and dropdown results
  let searchTimeout;
  byId("spotifyDetailQueryInput")?.addEventListener("input", async (event) => {
    const query = event.target.value.trim();
    clearTimeout(searchTimeout);
    
    const resultsContainer = byId("spxSearchResults");
    if (!query) {
      resultsContainer?.classList.add("hidden");
      return;
    }
    
    resultsContainer?.classList.remove("hidden");
    
    searchTimeout = setTimeout(async () => {
      try {
        // Call backend to search Spotify
        const response = await eel.searchSpotify(query)();
        if (response?.tracks) {
          renderSearchResults(response.tracks);
        }
      } catch (error) {
        console.error("Search error:", error);
      }
    }, 300); // Debounce by 300ms
  });

  // Hide search results when clicking outside
  document.addEventListener("click", (event) => {
    const searchWrapper = byId("spotifyDetailQueryInput");
    const resultsContainer = byId("spxSearchResults");
    if (!searchWrapper?.contains(event.target) && !resultsContainer?.contains(event.target)) {
      resultsContainer?.classList.add("hidden");
    }
  });

  // Progress bar scrubbing
  const progressBar = byId("spxProgress")?.parentElement;
  if (progressBar) {
    progressBar.addEventListener("click", async (event) => {
      const rect = progressBar.getBoundingClientRect();
      const percent = (event.clientX - rect.left) / rect.width;
      const track = document.querySelector('[id^="spxNowTitle"]');
      
      // Get current track duration
      const totalTimeEl = byId("spxTotalTime");
      const durationMs = parseDuration(totalTimeEl?.textContent || "0:00") * 1000;
      const seekMs = Math.max(0, Math.floor(durationMs * percent));
      
      try {
        await eel.seekTrack(seekMs)();
      } catch (error) {
        console.error("Seek error:", error);
      }
    });
  }

  // Real-time progress bar updates
  setInterval(() => {
    if (state.spotifyPlaying) {
      refreshSpotifyState();
    }
  }, 1000); // Update every second

  // Playlist selection - click playlist to show tracks
  byId("spxPlaylistLinks")?.addEventListener("click", async (event) => {
    const link = event.target.closest("a");
    if (!link) return;
    event.preventDefault();
    
    const playlistUri = link.getAttribute("data-uri") || "";
    const playlistName = link.getAttribute("data-query") || "";
    
    if (!playlistUri) {
      await playSpotifyByUri(playlistUri, playlistName);
      return;
    }
    
    try {
      // Fetch playlist tracks
      const response = await eel.getPlaylistTracks(playlistUri)();
      if (response?.tracks) {
        renderPlaylistView(playlistName, response.tracks, playlistUri);
      }
    } catch (error) {
      console.error("Playlist error:", error);
      await playSpotifyByUri(playlistUri, playlistName);
    }
  });

  // Back button from playlist view
  byId("spxBackToHome")?.addEventListener("click", () => {
    byId("spxPlaylistView")?.classList.add("hidden");
    byId("spxHomeContent")?.classList.remove("hidden");
  });

  // Volume slider real-time sync
  const volumeSlider = byId("spotifyDetailVolumeSlider");
  if (volumeSlider) {
    volumeSlider.addEventListener("input", (event) => {
      const volume = event.target.value;
      // Show volume percentage (optional visual feedback)
      const volDisplay = document.createElement("span");
      volDisplay.textContent = `${volume}%`;
      volDisplay.style.position = "absolute";
      volDisplay.style.color = "#1db954";
      volDisplay.style.fontSize = "0.8rem";
      
      eel.setSpotifyVolume(volume)().catch(() => undefined);
    });
  }

  const dashChatInput = byId("jarvisChatInput");
  dashChatInput?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    await submitDashboardPrompt(dashChatInput.value, "typed");
  });

  const legacyInput = byId("chatbox");
  const legacySend = byId("SendBtn");
  const legacyMic = byId("MicBtn");

  const toggleLegacyButtons = () => {
    if (!legacyInput || !legacySend || !legacyMic) {
      return;
    }
    const hasText = String(legacyInput.value || "").trim().length > 0;
    legacySend.hidden = !hasText;
    legacyMic.hidden = hasText;
  };

  legacyInput?.addEventListener("input", toggleLegacyButtons);
  legacyInput?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    const text = String(legacyInput.value || "").trim();
    if (!text) {
      return;
    }
    showSiriWave();
    await submitDashboardPrompt(text, "typed");
    legacyInput.value = "";
    toggleLegacyButtons();
  });

  legacySend?.addEventListener("click", async () => {
    const text = String(legacyInput?.value || "").trim();
    if (!text) {
      return;
    }
    showSiriWave();
    await submitDashboardPrompt(text, "typed");
    if (legacyInput) {
      legacyInput.value = "";
    }
    toggleLegacyButtons();
  });

  legacyMic?.addEventListener("click", async () => {
    beginVoiceCaptureSession();
    setHotwordOverlayState(true, "jarvis");
    await eel.takeCommand()();
  });

  document.addEventListener("keyup", async (event) => {
    if (event.key.toLowerCase() === "j" && event.metaKey) {
      beginVoiceCaptureSession();
      setHotwordOverlayState(true, "jarvis");
      await eel.takeCommand()();
    }
  });
}

// Helper function to parse duration string (M:SS or MM:SS)
function parseDuration(timeString) {
  const parts = timeString.split(":");
  const minutes = parseInt(parts[0], 10) || 0;
  const seconds = parseInt(parts[1], 10) || 0;
  return minutes * 60 + seconds;
}

// Render search results in dropdown
function renderSearchResults(tracks) {
  const grid = byId("spxTracksResults");
  if (!grid) return;
  
  if (!Array.isArray(tracks) || !tracks.length) {
    grid.innerHTML = "<p style='padding: 15px; color: #b3b3b3;'>No results found</p>";
    return;
  }
  
  grid.innerHTML = tracks
    .slice(0, 8) // Limit to 8 results
    .map((track) => {
      const trackName = track.name || track.title || "Untitled";
      const artistName = (track.artists || track.artist || []).toString().split(",")[0] || "Unknown Artist";
      const imageUrl = track.image || "https://picsum.photos/40/40?random=" + Math.random();
      const uri = track.uri || "";
      
      return `
        <div class="spx-result-item" data-uri="${uri}" data-query="${trackName} ${artistName}">
          <img src="${imageUrl}" alt="${trackName}" class="spx-result-img" />
          <div class="spx-result-info">
            <p class="spx-result-title">${trackName}</p>
            <p class="spx-result-subtitle">${artistName}</p>
          </div>
        </div>
      `;
    })
    .join("");
  
  // Add click handlers to results
  grid.querySelectorAll(".spx-result-item").forEach((item) => {
    item.addEventListener("click", async () => {
      const uri = item.getAttribute("data-uri");
      const query = item.getAttribute("data-query");
      byId("spxSearchResults")?.classList.add("hidden");
      await playSpotifyByUri(uri, query);
    });
  });
}

// Render playlist view with track list
function renderPlaylistView(playlistName, tracks, playlistUri) {
  const homeContent = byId("spxHomeContent");
  const playlistView = byId("spxPlaylistView");
  const playlistTitle = byId("spxPlaylistTitle");
  const tracksContainer = byId("spxPlaylistTracks");
  
  if (!playlistView || !tracksContainer) return;
  
  if (playlistTitle) {
    playlistTitle.textContent = playlistName;
  }
  
  if (!Array.isArray(tracks) || !tracks.length) {
    tracksContainer.innerHTML = "<p style='padding: 20px; color: #b3b3b3;'>No tracks in this playlist</p>";
    homeContent?.classList.add("hidden");
    playlistView.classList.remove("hidden");
    return;
  }
  
  tracksContainer.innerHTML = tracks
    .map((track, index) => {
      const trackName = track.name || track.title || "Untitled";
      const artistName = (Array.isArray(track.artists) ? track.artists.join(", ") : track.artist) || "Unknown Artist";
      const imageUrl = track.image || "https://picsum.photos/56/56?random=" + index;
      const duration = formatMs(track.duration_ms || 0);
      const uri = track.uri || "";
      
      return `
        <div class="spx-track-item" data-uri="${uri}" data-query="${trackName} ${artistName}">
          <img src="${imageUrl}" alt="${trackName}" class="spx-track-artwork" />
          <div class="spx-track-info">
            <p class="spx-track-name">${trackName}</p>
            <p class="spx-track-artists">${artistName}</p>
          </div>
          <span class="spx-track-duration">${duration}</span>
        </div>
      `;
    })
    .join("");
  
  // Add click handlers to tracks
  tracksContainer.querySelectorAll(".spx-track-item").forEach((item) => {
    item.addEventListener("click", async () => {
      const uri = item.getAttribute("data-uri");
      const query = item.getAttribute("data-query");
      await playSpotifyByUri(uri, query);
    });
  });
  
  homeContent?.classList.add("hidden");
  playlistView.classList.remove("hidden");
}

async function startupSequence() {
  showScreen(SCREENS.startup);
  setFaceAuthVisual("auth");
  updateDashboardDateTime();

  await new Promise((resolve) => window.setTimeout(resolve, 2400));
  showScreen(SCREENS.auth);
  setFaceAuthVisual("auth");
  setAuthStatus("Preparing face authentication...");

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
  eel.expose(setHotwordOverlayState);
  eel.expose(setAssistantListeningState);
  eel.expose(setAssistantHeardQuery);
  eel.expose(setAssistantResponse);
  eel.expose(DisplayMessage);
  eel.expose(ShowHood);
  eel.expose(showSiriWave);
  eel.expose(senderText);
  eel.expose(receiverText);
  eel.expose(hideLoader);
  eel.expose(hideFaceAuth);
  eel.expose(hideFaceAuthSuccess);
  eel.expose(hideStart);
}

function updateAutomotiveDashboard() {
  const currentSpeed = Math.min(120, Math.floor(Math.random() * 130));
  const rpm = Math.min(6500, Math.floor(Math.random() * 6800));
  const fuelLevel = 45 + Math.floor(Math.random() * 40);
  const coolantTemp = 80 + Math.floor(Math.random() * 15);
  const batteryVoltage = 12.0 + (Math.random() * 0.8);
  
  const speedValue = byId("dashSpeedValue");
  if (speedValue) {
    speedValue.textContent = currentSpeed;
  }
  
  const speedGaugeFill = byId("speedGaugeFill");
  if (speedGaugeFill) {
    const maxDasharray = 628;
    const speedPercent = currentSpeed / 180;
    const dasharray = maxDasharray * speedPercent;
    speedGaugeFill.setAttribute("stroke-dasharray", dasharray + " " + maxDasharray);
  }
  
  const rpmEl = byId("dashRPM");
  if (rpmEl) {
    rpmEl.textContent = rpm.toLocaleString();
  }
  
  const fuelEl = byId("dashFuel");
  if (fuelEl) {
    fuelEl.textContent = fuelLevel + "%";
  }
  
  const tempEl = byId("dashTemp");
  if (tempEl) {
    tempEl.textContent = coolantTemp + "°";
  }
  
  const batteryEl = byId("dashBattery");
  if (batteryEl) {
    batteryEl.textContent = batteryVoltage.toFixed(1) + "V";
  }
}

function initJarvisOrb() {
  const orbCore = byId("jarvisCore");
  if (!orbCore || orbCore.dataset.ready === "true") {
    return;
  }

  const particleCount = 220;
  for (let i = 0; i < particleCount; i += 1) {
    const particle = document.createElement("span");
    particle.className = "jarvis-particle";

    // Keep particles mostly inside a spherical silhouette.
    const radius = Math.sqrt(Math.random()) * 48;
    const theta = Math.random() * Math.PI * 2;
    const x = 50 + Math.cos(theta) * radius;
    const y = 50 + Math.sin(theta) * radius * 0.86;

    particle.style.left = `${x}%`;
    particle.style.top = `${y}%`;
    particle.style.setProperty("--particle-delay", `${(Math.random() * 4).toFixed(2)}s`);
    particle.style.setProperty("--drift-x", `${(Math.random() * 18 - 9).toFixed(2)}px`);
    particle.style.setProperty("--drift-y", `${(Math.random() * 18 - 9).toFixed(2)}px`);
    particle.style.opacity = (0.38 + Math.random() * 0.6).toFixed(2);
    orbCore.appendChild(particle);
  }

  const waveBars = Array.from(document.querySelectorAll(".siri-bar"));
  waveBars.forEach((bar, index) => {
    bar.style.setProperty("--bar-index", String(index));
  });

  orbCore.dataset.ready = "true";
}

window.addEventListener("DOMContentLoaded", async () => {
  initJarvisOrb();
  ensureLegacySiriWave();
  ShowHood();
  if (window.jQuery && typeof window.jQuery.fn?.textillate === "function") {
    window.jQuery(".siri-message").textillate({
      loop: true,
      sync: true,
      in: { effect: "fadeInUp", sync: true },
      out: { effect: "fadeInDown", sync: true },
    });
  }
  bindPinPad();
  bindUI();
  setupMaps();
  registerEelCallbacks();
  await startupSequence();
  await loadSettingsToUI();
  await refreshSpotifyState();
  await refreshBabyMonitorState();
  await loadBabyRegionFromBackend();
    updateAutomotiveDashboard();
  window.setInterval(updateDashboardDateTime, 30000);
    window.setInterval(updateAutomotiveDashboard, 1500);
  window.setInterval(refreshSpotifyState, 6000);
  window.setInterval(refreshBabyMonitorState, 2000);
});
