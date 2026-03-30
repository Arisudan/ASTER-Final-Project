const screenIds = ["loader", "face-auth", "face-enrollment", "face-auth-success", "main-dashboard"];
const spotifyState = {
  sdkReady: false,
  player: null,
  deviceId: "",
  token: "",
  connected: false,
  currentTrack: null,
  currentUser: "",
};

const uiState = {
  mode: "ambient",
  modeTimer: null,
  speed: 0,
  gear: "P",
  battery: 91,
  climateOn: false,
  lightsOn: false,
  shuffle: false,
  repeatMode: "off",
  voiceBusy: false,
  enrollmentOrigin: "auth",
};

let speedGauge = null;
let spotifyPollTimer = null;
let telemetryTimer = null;
let lastAnnouncedTrack = "";

function byId(id) {
  return document.getElementById(id);
}

function announce(message) {
  const region = byId("liveRegion");
  if (region) {
    region.textContent = message || "";
  }
}

function setScreenVisibility(id, visible) {
  const element = byId(id);
  if (!element) {
    return;
  }
  element.classList.toggle("screen--active", visible);
  element.classList.toggle("screen--hidden", !visible);
}

function hideAllScreens() {
  screenIds.forEach((id) => setScreenVisibility(id, false));
}

function showOnly(id) {
  hideAllScreens();
  setScreenVisibility(id, true);
}

function toggleMode(mode) {
  uiState.mode = mode === "driving" ? "driving" : "ambient";
  document.body.dataset.mode = uiState.mode;
  const modeValue = byId("modeValue");
  const modeToggleButton = byId("modeToggleButton");
  if (modeValue) {
    modeValue.textContent = uiState.mode === "driving" ? "Dark" : "Dark+";
  }
  if (modeToggleButton) {
    modeToggleButton.textContent = uiState.mode === "driving" ? "Dark+ Mode" : "Dark Mode";
    modeToggleButton.setAttribute("aria-label", `Switch to ${uiState.mode === "driving" ? "dark" : "deeper dark"} mode`);
  }

  const dashboard = byId("main-dashboard");
  if (dashboard) {
    dashboard.classList.toggle("dashboard--driving", uiState.mode === "driving");
    dashboard.classList.toggle("dashboard--ambient", uiState.mode === "ambient");
  }

  updateGearHighlight();
}

function scheduleAmbientMode(delay = 7000) {
  if (uiState.modeTimer) {
    window.clearTimeout(uiState.modeTimer);
  }
  uiState.modeTimer = window.setTimeout(() => toggleMode("ambient"), delay);
}

function hideLoader() {
  setScreenVisibility("loader", false);
  setScreenVisibility("face-auth", true);
  toggleMode("ambient");
  updateAuthStatus("Face authentication is starting...");
}

function hideFaceAuth() {
  setScreenVisibility("face-auth", false);
}

function hideFaceAuthSuccess() {
  setScreenVisibility("face-auth-success", true);
  window.setTimeout(() => {
    setScreenVisibility("face-auth-success", false);
  }, 1800);
}

function hideStart() {
  setScreenVisibility("main-dashboard", true);
  toggleMode("ambient");
  refreshAllState();
}

function showEnrollment(origin = "auth") {
  uiState.enrollmentOrigin = origin;
  setScreenVisibility("face-enrollment", true);
}

function hideEnrollment() {
  setScreenVisibility("face-enrollment", false);
}

function showSettings() {
  const drawer = byId("settingsDrawer");
  if (drawer) {
    drawer.classList.add("settings-drawer--open");
    drawer.setAttribute("aria-hidden", "false");
  }
  loadSettingsDrawer();
}

function hideSettings() {
  const drawer = byId("settingsDrawer");
  if (drawer) {
    drawer.classList.remove("settings-drawer--open");
    drawer.setAttribute("aria-hidden", "true");
  }
}

function updateAuthStatus(text) {
  const status = byId("auth-status");
  if (status) {
    status.textContent = text;
  }
  announce(text);
}

function updateEnrollmentStatus(text) {
  const status = byId("enrollment-status");
  if (status) {
    status.textContent = text;
  }
  announce(text);
}

function updateCommand(commandText, responseText) {
  const recognitionText = byId("recognitionText");
  const responseTextElement = byId("responseText");
  const voiceCommand = byId("voiceCommand");

  if (recognitionText) {
    recognitionText.textContent = commandText || "Awaiting voice command.";
  }
  if (responseTextElement) {
    responseTextElement.textContent = responseText || "System ready.";
  }
  if (voiceCommand && commandText) {
    voiceCommand.value = commandText;
  }

  const spoken = [commandText, responseText].filter(Boolean).join(". ");
  if (spoken) {
    announce(spoken);
  }
}

function showAlert(message) {
  announce(message);
  if (window.Swal) {
    window.Swal.fire({
      title: "ASTER",
      text: message,
      icon: "info",
      background: "#0a0e1a",
      color: "#f0f6ff",
      confirmButtonColor: "#00d4ff",
    });
    return;
  }

  console.log(message);
}

function triggerWakeAnimation(source) {
  const orb = byId("voiceOrb");
  if (!orb) {
    return;
  }

  orb.classList.add("voice-orb--active");
  window.setTimeout(() => {
    orb.classList.remove("voice-orb--active");
  }, 1600);

  showAlert(source ? `Wake word detected from ${source}.` : "Wake word detected.");
}

function updateClock() {
  const now = window.luxon ? window.luxon.DateTime.local() : new Date();
  const clock = byId("live-clock");
  const date = byId("live-date");

  if (clock) {
    clock.textContent = window.luxon
      ? now.toFormat("hh:mm:ss a")
      : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  if (date) {
    date.textContent = window.luxon
      ? now.toFormat("ccc, LLL dd yyyy")
      : new Date().toLocaleDateString([], { weekday: "short", month: "short", day: "numeric", year: "numeric" });
  }
}

async function refreshWeather() {
  try {
    const response = await fetch("https://wttr.in/?format=j1");
    const payload = await response.json();
    const current = payload.current_condition?.[0];
    if (current) {
      const weather = byId("autopilotValue");
      if (weather) {
        weather.textContent = `${current.temp_C}°C ${current.weatherDesc?.[0]?.value || "Clear"}`;
      }
    }
  } catch (error) {
    const weather = byId("autopilotValue");
    if (weather) {
      weather.textContent = "Standby";
    }
  }
}

function formatTime(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function initSpeedGauge() {
  const canvas = byId("speedGauge");
  if (!canvas || !window.Chart) {
    return;
  }

  speedGauge = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: ["Speed", "Remaining"],
      datasets: [
        {
          data: [0, 120],
          backgroundColor: ["#00d4ff", "rgba(255,255,255,0.06)"],
          borderWidth: 0,
          hoverOffset: 0,
          cutout: "78%",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      rotation: -120,
      circumference: 240,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    },
  });
}

function updateSpeedGauge(speed) {
  if (!speedGauge) {
    return;
  }
  const clamped = Math.max(0, Math.min(120, Math.round(speed)));
  speedGauge.data.datasets[0].data = [clamped, 120 - clamped];
  speedGauge.update("none");
}

function updateGearHighlight() {
  const gearStrip = byId("gearStrip");
  if (!gearStrip) {
    return;
  }
  gearStrip.querySelectorAll("span[data-gear]").forEach((element) => {
    element.classList.toggle("gear--active", element.getAttribute("data-gear") === uiState.gear);
  });
}

function setGear(gear) {
  uiState.gear = gear;
  updateGearHighlight();
}

function updateVehicleTelemetry() {
  const speedLabel = byId("speedValue");
  const battery = byId("batteryValue");
  const lightsState = byId("seatLightsState");
  const climateState = byId("climateState");

  if (uiState.mode === "driving") {
    uiState.speed = Math.min(116, Math.max(18, uiState.speed + Math.round(Math.random() * 10 - 2)));
    uiState.battery = Math.max(30, uiState.battery - 0.1);
    setGear("D");
  } else {
    uiState.speed = Math.max(0, uiState.speed - 12);
    setGear("P");
  }

  if (speedLabel) {
    speedLabel.textContent = String(uiState.speed);
  }
  if (battery) {
    battery.textContent = `${Math.round(uiState.battery)}%`;
  }
  if (lightsState) {
    lightsState.textContent = uiState.lightsOn ? "On" : "Off";
  }
  if (climateState) {
    climateState.textContent = uiState.climateOn ? "Auto" : "72°F";
  }

  updateSpeedGauge(uiState.speed);
}

function setSpotifyConnectionState(text) {
  const state = byId("spotifyConnectionState");
  if (state) {
    state.textContent = text || "Disconnected";
  }
}

function renderSpotifyTrack(track) {
  const payload = track || {};
  const title = byId("spotifyTrackTitle");
  const artist = byId("spotifyTrackArtist");
  const album = byId("spotifyTrackAlbum");
  const artwork = byId("spotifyArtwork");
  const fill = byId("spotifyProgressFill");
  const current = byId("spotifyProgressCurrent");
  const total = byId("spotifyProgressTotal");
  const playPause = byId("spotifyPlayPauseButton");
  const shuffle = byId("spotifyShuffleToggle");
  const repeat = byId("spotifyRepeatToggle");

  if (title) {
    title.textContent = payload.title || "Spotify not connected";
  }
  if (artist) {
    artist.textContent = payload.artist || "Sign in to start playback.";
  }
  if (album) {
    album.textContent = payload.album || "Web Playback SDK ready.";
  }
  if (artwork && payload.image) {
    artwork.src = payload.image;
    artwork.alt = payload.title || "Album cover";
  }

  const duration = Number(payload.duration_ms || 0);
  const progress = Number(payload.progress_ms || 0);
  const percent = duration > 0 ? Math.min(100, Math.max(0, (progress / duration) * 100)) : 0;

  if (fill) {
    fill.style.width = `${percent}%`;
  }
  if (current) {
    current.textContent = formatTime(progress);
  }
  if (total) {
    total.textContent = formatTime(duration);
  }
  if (playPause) {
    playPause.textContent = payload.is_playing ? "⏸" : "▶";
  }
  if (shuffle) {
    shuffle.checked = Boolean(payload.shuffle_state);
  }
  if (repeat) {
    repeat.checked = String(payload.repeat_state || "off") !== "off";
  }

  if (payload.device_name) {
    setSpotifyConnectionState(`${payload.device_name}`);
  }

  const announcement = [payload.title, payload.artist].filter(Boolean).join(" by ");
  if (announcement && announcement !== lastAnnouncedTrack) {
    lastAnnouncedTrack = announcement;
    announce(`Spotify ${announcement}`);
  }
}

function renderSettingsList(containerId, items, renderItem, emptyText) {
  const container = byId(containerId);
  if (!container) {
    return;
  }

  if (!items || !items.length) {
    container.innerHTML = `<div class="profile-item profile-item--empty">${emptyText}</div>`;
    return;
  }

  container.innerHTML = items.map(renderItem).join("");
}

async function refreshFaceProfiles() {
  try {
    const profiles = await eel.listFaceProfiles()();
    renderSettingsList(
      "faceProfilesList",
      profiles || [],
      (profile) => `
        <div class="profile-item" data-profile-id="${profile.id}">
          <div>
            <strong>${profile.name}</strong>
            <span>Enrolled ${profile.created_at || "Unknown"}</span>
          </div>
          <button type="button" class="profile-danger profile-delete-face">Delete</button>
        </div>
      `,
      "No face profiles enrolled yet.",
    );

    byId("faceProfilesList")?.querySelectorAll(".profile-delete-face").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest("[data-profile-id]");
        const profileId = row ? row.getAttribute("data-profile-id") : "";
        if (!profileId) {
          return;
        }
        const updated = await eel.deleteFaceProfile(Number(profileId))();
        refreshFaceProfiles();
        showAlert(`Deleted face profile ${profileId}.`);
        return updated;
      });
    });
  } catch (error) {
    renderSettingsList("faceProfilesList", [], () => "", "Unable to load face profiles.");
  }
}

async function refreshSettingsPresets() {
  try {
    const presets = await eel.listSettingsPresets()();
    renderSettingsList(
      "settingsPresetsList",
      presets || [],
      (preset) => `
        <div class="profile-item" data-preset-user="${preset.user_name}">
          <div>
            <strong>${preset.user_name}</strong>
            <span>Updated ${preset.updated_at || "Unknown"}</span>
          </div>
          <div class="profile-actions">
            <button type="button" class="profile-action profile-apply-preset">Apply</button>
            <button type="button" class="profile-danger profile-delete-preset">Delete</button>
          </div>
        </div>
      `,
      "No presets saved yet.",
    );

    byId("settingsPresetsList")?.querySelectorAll(".profile-apply-preset").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest("[data-preset-user]");
        const userName = row ? row.getAttribute("data-preset-user") : "";
        if (!userName) {
          return;
        }
        const applied = await eel.applySettingsPreset(userName)();
        populateSettingsForm(applied || {});
        showAlert(`Applied preset for ${userName}.`);
      });
    });

    byId("settingsPresetsList")?.querySelectorAll(".profile-delete-preset").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest("[data-preset-user]");
        const userName = row ? row.getAttribute("data-preset-user") : "";
        if (!userName) {
          return;
        }
        await eel.deleteSettingsPreset(userName)();
        refreshSettingsPresets();
        showAlert(`Deleted preset for ${userName}.`);
      });
    });
  } catch (error) {
    renderSettingsList("settingsPresetsList", [], () => "", "Unable to load presets.");
  }
}

function populateSettingsForm(settings) {
  const applyValue = (id, value) => {
    const element = byId(id);
    if (element) {
      element.value = value ?? "";
    }
  };

  const applyChecked = (id, value) => {
    const element = byId(id);
    if (element) {
      const normalized = String(value ?? "").toLowerCase();
      element.checked = ["1", "true", "yes", "on"].includes(normalized);
    }
  };

  applyValue("assistantNameInput", settings.assistant_name);
  applyValue("speechRateInput", settings.speech_rate);
  applyChecked("wakeWordToggle", settings.wake_word_enabled);
  applyValue("defaultSpotifyVolumeInput", settings.spotify_volume || 65);
  applyValue("defaultSpotifyQueryInput", settings.default_spotify_query || "");
}

function collectSettingsPayload() {
  return {
    assistant_name: byId("assistantNameInput")?.value.trim() || "ASTER",
    speech_rate: byId("speechRateInput")?.value.trim() || "180",
    wake_word_enabled: Boolean(byId("wakeWordToggle")?.checked),
    spotify_volume: byId("defaultSpotifyVolumeInput")?.value.trim() || "65",
    default_spotify_query: byId("defaultSpotifyQueryInput")?.value.trim() || "",
  };
}

async function loadSettingsDrawer() {
  try {
    const [settings, user, spotify] = await Promise.all([
      eel.getSettings()(),
      eel.getCurrentUser()(),
      eel.getSpotifyState()(),
    ]);
    populateSettingsForm(settings || {});
    const spotifyStatus = byId("spotifyDeviceStatus");
    if (spotifyStatus) {
      spotifyStatus.textContent = user ? `Active user: ${user}` : "No face-authenticated user is active.";
    }
    setSpotifyConnectionState(spotify?.track?.device_name || spotify?.message || "Disconnected");
    await Promise.all([refreshFaceProfiles(), refreshSettingsPresets(), refreshSpotifyState()]);
  } catch (error) {
    const spotifyStatus = byId("spotifyDeviceStatus");
    if (spotifyStatus) {
      spotifyStatus.textContent = "Unable to load settings right now.";
    }
  }
}

async function saveSettings() {
  const payload = collectSettingsPayload();
  const updated = await eel.saveSettings(payload)();
  populateSettingsForm(updated || payload);
  showAlert("Settings saved.");
}

async function savePreset() {
  const payload = collectSettingsPayload();
  await eel.saveCurrentUserPreset(payload)();
  await refreshSettingsPresets();
  showAlert("Current user preset saved.");
}

function clearModeTimeout() {
  if (uiState.modeTimer) {
    window.clearTimeout(uiState.modeTimer);
    uiState.modeTimer = null;
  }
}

async function processVoiceCommand() {
  toggleMode("driving");
  clearModeTimeout();
  scheduleAmbientMode(8000);
  showAlert("Listening for your command.");
  try {
    await eel.takeCommand()();
    updateCommand("Listening...", "Command queued.");
  } catch (error) {
    updateCommand("Error", "Voice capture failed.");
  }
}

async function openMaps() {
  const response = await eel.allCommands("open maps")();
  updateCommand("open maps", response);
}

function registerBottomBar() {
  byId("bottomHomeButton")?.addEventListener("click", () => {
    toggleMode("ambient");
    showOnly("main-dashboard");
  });

  byId("bottomVoiceButton")?.addEventListener("click", processVoiceCommand);

  byId("bottomMusicButton")?.addEventListener("click", async () => {
    toggleMode("driving");
    await playSpotifyWithFallback(byId("spotifySearchInput")?.value.trim() || undefined);
    scheduleAmbientMode(7000);
  });

  byId("bottomMapsButton")?.addEventListener("click", openMaps);

  byId("bottomSettingsButton")?.addEventListener("click", showSettings);
}

function registerSeatControls() {
  byId("homeButton")?.addEventListener("click", () => {
    toggleMode("ambient");
    showOnly("main-dashboard");
  });

  byId("voiceAssistButton")?.addEventListener("click", processVoiceCommand);

  byId("openMapsButton")?.addEventListener("click", openMaps);

  byId("connectSpotifyButton")?.addEventListener("click", connectSpotify);

  byId("spotifyPlayPauseButton")?.addEventListener("click", async () => {
    const isPlaying = Boolean(spotifyState.currentTrack?.is_playing);
    if (isPlaying) {
      applySpotifyResult(await eel.pauseSpotify()());
      return;
    }

    await playSpotifyWithFallback(byId("spotifySearchInput")?.value.trim() || undefined);
  });

  byId("spotifyNextButton")?.addEventListener("click", async () => {
    applySpotifyResult(await eel.nextTrack()());
  });

  byId("spotifyPrevButton")?.addEventListener("click", async () => {
    applySpotifyResult(await eel.prevTrack()());
  });

  byId("spotifySearchButton")?.addEventListener("click", async () => {
    const query = byId("spotifySearchInput")?.value.trim();
    if (!query) {
      showAlert("Enter a song or artist to search.");
      return;
    }
    await playSpotifyWithFallback(query);
  });

  byId("spotifyVolumeSlider")?.addEventListener("input", async (event) => {
    const value = event.target.value;
    applySpotifyResult(await eel.setSpotifyVolume(value)());
  });

  byId("spotifyShuffleToggle")?.addEventListener("change", async (event) => {
    applySpotifyResult(await eel.setSpotifyShuffle(event.target.checked)());
  });

  byId("spotifyRepeatToggle")?.addEventListener("change", async (event) => {
    applySpotifyResult(await eel.setSpotifyRepeat(event.target.checked ? "context" : "off")());
  });

  document.querySelectorAll("[data-seat-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.getAttribute("data-seat-action");
      if (action === "lights") {
        uiState.lightsOn = !uiState.lightsOn;
        const lightsState = byId("seatLightsState");
        if (lightsState) {
          lightsState.textContent = uiState.lightsOn ? "On" : "Off";
        }
        showAlert(`Interior lights ${uiState.lightsOn ? "enabled" : "disabled"}.`);
      } else if (action === "climate") {
        uiState.climateOn = !uiState.climateOn;
        const climateState = byId("climateState");
        if (climateState) {
          climateState.textContent = uiState.climateOn ? "Auto" : "72°F";
        }
        showAlert(`Climate ${uiState.climateOn ? "set to auto" : "set to comfort"}.`);
      } else if (action === "settings") {
        showSettings();
      }
    });
  });

  byId("micButton")?.addEventListener("click", processVoiceCommand);
}

function registerAuthControls() {
  byId("authEnrollButton")?.addEventListener("click", () => showEnrollment("auth"));
  byId("authSettingsButton")?.addEventListener("click", showSettings);
  byId("enrollmentCancel")?.addEventListener("click", () => {
    hideEnrollment();
    if (uiState.enrollmentOrigin === "settings") {
      showSettings();
      return;
    }
    setScreenVisibility("face-auth", true);
  });
  byId("enrollmentSubmit")?.addEventListener("click", async () => {
    const name = byId("enrollmentName")?.value.trim() || "";
    if (!name) {
      updateEnrollmentStatus("Enter a profile name before enrolling.");
      return;
    }

    updateEnrollmentStatus("Capturing face samples...");
    try {
      const result = await eel.enrollFace(name)();
      if (result === 1) {
        updateEnrollmentStatus(`Enrollment saved for ${name}.`);
        window.setTimeout(() => {
          hideEnrollment();
          if (uiState.enrollmentOrigin === "settings") {
            showSettings();
            refreshFaceProfiles();
          } else {
            setScreenVisibility("face-auth", true);
            updateAuthStatus("Face enrolled. Continue with authentication.");
          }
        }, 1000);
      } else {
        updateEnrollmentStatus("Enrollment failed. Try again with better lighting.");
      }
    } catch (error) {
      updateEnrollmentStatus("Enrollment failed.");
    }
  });

  byId("closeSettingsButton")?.addEventListener("click", hideSettings);
  byId("saveSettingsButton")?.addEventListener("click", saveSettings);
  byId("savePresetButton")?.addEventListener("click", savePreset);
  byId("refreshPresetsButton")?.addEventListener("click", refreshSettingsPresets);
  byId("openEnrollmentButton")?.addEventListener("click", () => showEnrollment("settings"));
}

function registerSettingsControls() {
  byId("settingsDrawer")?.addEventListener("click", (event) => {
    if (event.target && event.target.id === "settingsDrawer") {
      hideSettings();
    }
  });
}

function registerSpotifyControls() {
  byId("connectSpotifyButton")?.addEventListener("click", connectSpotify);
}

function registerModeToggleControls() {
  byId("modeToggleButton")?.addEventListener("click", () => {
    toggleMode(uiState.mode === "driving" ? "ambient" : "driving");
  });
}

function applySpotifyResult(result) {
  if (!result) {
    return;
  }

  if (result.state) {
    spotifyState.currentTrack = result.state.track || null;
    renderSpotifyTrack(spotifyState.currentTrack || result.state.track || {});
  }

  if (result.ok === false && result.message) {
    showAlert(result.message);
  }

  if (result.message) {
    const spotifyStatus = byId("spotifyDeviceStatus");
    if (spotifyStatus) {
      spotifyStatus.textContent = result.message;
    }
  }
}

async function connectSpotify() {
  showAlert("Connecting Spotify...");
  try {
    const result = await eel.connectSpotify()();
    applySpotifyResult(result);
    if (result?.ok) {
      spotifyState.token = await eel.getSpotifyAccessToken()();
      spotifyState.connected = true;
      setSpotifyConnectionState("Connected");
      initializeSpotifyPlayer();
      await refreshSpotifyState();
    }
  } catch (error) {
    showAlert("Spotify connection failed.");
  }
}

async function ensureSpotifyReady() {
  if (spotifyState.connected && spotifyState.token) {
    return await waitForSpotifyDevice();
  }

  try {
    const result = await eel.connectSpotify()();
    applySpotifyResult(result);
    if (!result?.ok) {
      return false;
    }

    spotifyState.token = await eel.getSpotifyAccessToken()();
    spotifyState.connected = true;
    setSpotifyConnectionState("Connected");
    initializeSpotifyPlayer();
    await refreshSpotifyState();
    return await waitForSpotifyDevice();
  } catch (error) {
    return false;
  }
}

async function waitForSpotifyDevice(timeoutMs = 8000) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    if (spotifyState.player && spotifyState.deviceId) {
      return true;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }

  return Boolean(spotifyState.deviceId);
}

async function playSpotifyWithFallback(query) {
  const ready = await ensureSpotifyReady();
  if (!ready) {
    showAlert("Spotify is still starting. Open Spotify or wait for the web player, then try again.");
    return;
  }

  let result = await eel.playSpotify(query)();
  if (result?.ok === false && String(result.message || "").includes("No active Spotify device")) {
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    result = await eel.playSpotify(query)();
  }

  applySpotifyResult(result);
}

async function refreshSpotifyState() {
  try {
    const state = await eel.getSpotifyState()();
    spotifyState.currentTrack = state?.track || null;
    spotifyState.connected = Boolean(state?.connected);
    renderSpotifyTrack(spotifyState.currentTrack || state?.track || {});
    setSpotifyConnectionState(spotifyState.connected ? "Connected" : "Disconnected");
    if (state?.message) {
      const spotifyStatus = byId("spotifyDeviceStatus");
      if (spotifyStatus) {
        spotifyStatus.textContent = state.message;
      }
    }
  } catch (error) {
    setSpotifyConnectionState("Disconnected");
  }
}

function refreshAllState() {
  refreshSpotifyState();
  updateVehicleTelemetry();
}

function initializeSpotifyPlayer() {
  if (!spotifyState.sdkReady || spotifyState.player || !spotifyState.token) {
    return;
  }

  if (!window.Spotify) {
    showAlert("Spotify Web Playback SDK is unavailable.");
    return;
  }

  const player = new window.Spotify.Player({
    name: "ASTER",
    getOAuthToken: (callback) => {
      eel.getSpotifyAccessToken()().then((token) => callback(token || spotifyState.token || ""));
    },
    volume: 0.7,
  });

  player.addListener("initialization_error", ({ message }) => showAlert(`Spotify initialization error: ${message}`));
  player.addListener("authentication_error", ({ message }) => showAlert(`Spotify authentication error: ${message}`));
  player.addListener("account_error", ({ message }) => showAlert(`Spotify account error: ${message}`));
  player.addListener("playback_error", ({ message }) => showAlert(`Spotify playback error: ${message}`));
  player.addListener("ready", ({ device_id }) => {
    spotifyState.deviceId = device_id;
    setSpotifyConnectionState("Web Player Ready");
    announce("Spotify web player ready.");
    eel.transferSpotifyPlayback(device_id)();
  });
  player.addListener("not_ready", () => {
    setSpotifyConnectionState("Device offline");
  });
  player.addListener("player_state_changed", (state) => {
    if (!state) {
      return;
    }
    const current = state.track_window?.current_track;
    spotifyState.currentTrack = current
      ? {
          title: current.name,
          artist: current.artists.map((artist) => artist.name).join(", "),
          album: current.album?.name || "",
          image: current.album?.images?.[0]?.url || "",
          duration_ms: state.duration,
          progress_ms: state.position,
          is_playing: !state.paused,
          shuffle_state: state.shuffle,
          repeat_state: state.repeat_mode,
          device_name: "ASTER",
        }
      : spotifyState.currentTrack;
    renderSpotifyTrack(spotifyState.currentTrack || {});
  });

  player.connect().then((success) => {
    if (success) {
      spotifyState.player = player;
      showAlert("Spotify Web Playback SDK connected.");
    }
  });
}

function registerExternalSpotifySDK() {
  window.onSpotifyWebPlaybackSDKReady = () => {
    spotifyState.sdkReady = true;
    initializeSpotifyPlayer();
  };
}

function exposeFunctions() {
  eel.expose(hideLoader);
  eel.expose(hideFaceAuth);
  eel.expose(hideFaceAuthSuccess);
  eel.expose(hideStart);
  eel.expose(showEnrollment);
  eel.expose(hideEnrollment);
  eel.expose(showSettings);
  eel.expose(hideSettings);
  eel.expose(toggleMode);
  eel.expose(updateCommand);
  eel.expose(triggerWakeAnimation);
  eel.expose(showAlert);
}

function startLoops() {
  updateClock();
  window.setInterval(updateClock, 1000);
  refreshWeather();
  window.setInterval(refreshWeather, 5 * 60 * 1000);
  updateVehicleTelemetry();
  telemetryTimer = window.setInterval(updateVehicleTelemetry, 2600);
  spotifyPollTimer = window.setInterval(refreshSpotifyState, 4000);
}

function registerVoiceSearchField() {
  const voiceCommand = byId("voiceCommand");
  voiceCommand?.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      const text = voiceCommand.value.trim();
      if (!text) {
        return;
      }
      toggleMode("driving");
      scheduleAmbientMode(8000);
      const result = await eel.allCommands(text)();
      updateCommand(text, result);
    }
  });
}

function registerQuickSearchShortcuts() {
  byId("spotifySearchInput")?.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const query = byId("spotifySearchInput")?.value.trim();
      if (!query) {
        return;
      }
      await playSpotifyWithFallback(query);
    }
  });
}

window.addEventListener("load", async () => {
  exposeFunctions();
  registerExternalSpotifySDK();

  if (window.AOS) {
    window.AOS.init({ once: true, duration: 700, easing: "ease-out-cubic" });
  }

  toggleMode("ambient");
  setGear("P");
  initSpeedGauge();
  registerAuthControls();
  registerSeatControls();
  registerSettingsControls();
  registerModeToggleControls();
  registerBottomBar();
  registerSpotifyControls();
  registerVoiceSearchField();
  registerQuickSearchShortcuts();
  startLoops();

  showOnly("loader");
  updateCommand("System startup", "Initializing ASTER.");
  try {
    await eel.init()();
  } catch (error) {
    showAlert("Unable to start the assistant backend.");
  }
});