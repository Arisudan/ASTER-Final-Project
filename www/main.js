const screenIds = ["loader", "face-auth", "face-auth-success", "face-enrollment", "start"];
let statsChart = null;

function setScreenVisibility(id, visible) {
  const element = document.getElementById(id);
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

function hideLoader() {
  setScreenVisibility("loader", false);
  setScreenVisibility("face-auth", true);
  updateAuthStatus("Face authentication is starting...");
}

function hideFaceAuth() {
  setScreenVisibility("face-auth", false);
}

function showEnrollment() {
  hideAllScreens();
  setScreenVisibility("face-enrollment", true);
}

function hideEnrollment() {
  setScreenVisibility("face-enrollment", false);
}

function hideFaceAuthSuccess() {
  setScreenVisibility("face-auth-success", true);
  window.setTimeout(() => {
    setScreenVisibility("face-auth-success", false);
  }, 2000);
}

function hideStart() {
  setScreenVisibility("start", true);
}

function updateAuthStatus(text) {
  const authStatus = document.getElementById("auth-status");
  if (authStatus) {
    authStatus.textContent = text;
  }
}

function updateEnrollmentStatus(text) {
  const enrollmentStatus = document.getElementById("enrollment-status");
  if (enrollmentStatus) {
    enrollmentStatus.textContent = text;
  }
}

function updateClock() {
  const now = window.luxon ? window.luxon.DateTime.local() : new Date();
  const clockElement = document.getElementById("live-clock");
  const dateElement = document.getElementById("live-date");

  if (clockElement) {
    clockElement.textContent = window.luxon
      ? now.toFormat("hh:mm:ss a")
      : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  if (dateElement) {
    dateElement.textContent = window.luxon
      ? now.toFormat("ccc, LLL dd yyyy")
      : new Date().toLocaleDateString([], { weekday: "short", month: "short", day: "numeric", year: "numeric" });
  }
}

async function refreshWeather() {
  const weatherValue = document.getElementById("weather-value");
  if (!weatherValue) {
    return;
  }

  try {
    const response = await fetch("https://wttr.in/?format=j1");
    const payload = await response.json();
    const current = payload.current_condition[0];
    const temp = current.temp_C;
    const description = current.weatherDesc[0].value;
    weatherValue.textContent = `${temp}°C ${description}`;
  } catch (error) {
    weatherValue.textContent = "Weather offline";
  }
}

function initChart() {
  const chartCanvas = document.getElementById("statsChart");
  if (!chartCanvas || !window.Chart) {
    return;
  }

  const labels = ["-5", "-4", "-3", "-2", "-1", "Now"];
  statsChart = new Chart(chartCanvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "CPU",
          data: [20, 24, 18, 28, 32, 26],
          borderColor: "#00d4ff",
          backgroundColor: "rgba(0, 212, 255, 0.12)",
          tension: 0.35,
          fill: true,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ab0c9" } },
        y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ab0c9", stepSize: 20, callback: (value) => `${value}%` } },
      },
    },
  });

  window.setInterval(() => {
    if (!statsChart) {
      return;
    }
    const cpu = Math.max(8, Math.min(96, Math.round(18 + Math.random() * 22)));
    const memory = Math.max(24, Math.min(96, Math.round(32 + Math.random() * 20)));
    const network = Math.random() > 0.75 ? "Boost" : "Normal";
    const cpuMetric = document.getElementById("cpuMetric");
    const memoryMetric = document.getElementById("memoryMetric");
    const networkMetric = document.getElementById("networkMetric");

    if (cpuMetric) {
      cpuMetric.textContent = `${cpu}%`;
    }
    if (memoryMetric) {
      memoryMetric.textContent = `${memory}%`;
    }
    if (networkMetric) {
      networkMetric.textContent = network;
    }

    statsChart.data.datasets[0].data = [cpu - 8, cpu - 5, cpu - 2, cpu, cpu + 1, cpu];
    statsChart.update("none");
  }, 4000);
}

function updateCommand(commandText, responseText) {
  const commandStatus = document.getElementById("command-status");
  const responseStatus = document.getElementById("response-status");
  const lastCommand = document.getElementById("last-command");
  const lastResponse = document.getElementById("last-response");
  const voiceCommand = document.getElementById("voiceCommand");

  if (commandStatus) {
    commandStatus.textContent = commandText || "Awaiting voice command";
  }
  if (responseStatus) {
    responseStatus.textContent = responseText || "System ready.";
  }
  if (lastCommand) {
    lastCommand.textContent = commandText || "None";
  }
  if (lastResponse) {
    lastResponse.textContent = responseText || "Waiting for input";
  }
  if (voiceCommand && commandText) {
    voiceCommand.value = commandText;
  }
}

function showAlert(message) {
  if (window.Swal) {
    window.Swal.fire({
      title: "JARVIS",
      text: message,
      icon: "info",
      background: "#0a0e1a",
      color: "#e9f6ff",
      confirmButtonColor: "#00d4ff",
    });
    return;
  }

  console.log(message);
}

function triggerWakeAnimation(source) {
  const orb = document.querySelector(".orb");
  if (!orb) {
    return;
  }

  orb.classList.add("orb--wake");
  window.setTimeout(() => {
    orb.classList.remove("orb--wake");
  }, 1800);

  const status = source ? `Wake word detected from ${source}` : "Wake word detected";
  showAlert(status);
}

async function processVoiceCommand() {
  showAlert("Listening for your command");
  try {
    await eel.takeCommand()();
    updateCommand("Listening...", "Command queued.");
  } catch (error) {
    updateCommand("Error", "Voice capture failed.");
  }
}

function registerQuickActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const commandText = button.getAttribute("data-action") || "";
      const responseText = await eel.allCommands(commandText)();
      updateCommand(commandText, responseText);
    });
  });
}

function registerVoiceButton() {
  const micButton = document.getElementById("micButton");
  const voiceCommand = document.getElementById("voiceCommand");

  if (micButton) {
    micButton.addEventListener("click", processVoiceCommand);
  }

  if (voiceCommand) {
    voiceCommand.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        const commandText = voiceCommand.value.trim();
        if (!commandText) {
          return;
        }
        const responseText = await eel.allCommands(commandText)();
        updateCommand(commandText, responseText);
      }
    });
  }
}

function registerEnrollmentControls() {
  const enrollButton = document.getElementById("enrollButton");
  const enrollmentCancel = document.getElementById("enrollmentCancel");
  const faceEnrollButton = document.getElementById("faceEnrollButton");

  if (enrollButton) {
    enrollButton.addEventListener("click", showEnrollment);
  }

  if (faceEnrollButton) {
    faceEnrollButton.addEventListener("click", showEnrollment);
  }

  if (enrollmentCancel) {
    enrollmentCancel.addEventListener("click", () => {
      hideEnrollment();
      setScreenVisibility("face-auth", true);
    });
  }

  const enrollmentSubmit = document.getElementById("enrollmentSubmit");
  if (enrollmentSubmit) {
    enrollmentSubmit.addEventListener("click", async () => {
      const enrollmentName = document.getElementById("enrollmentName");
      const name = enrollmentName ? enrollmentName.value.trim() : "";
      if (!name) {
        updateEnrollmentStatus("Enter a name before enrolling.");
        return;
      }

      updateEnrollmentStatus("Capturing face profile...");
      try {
        const result = await eel.enrollFace(name)();
        if (result === 1) {
          updateEnrollmentStatus(`Enrollment saved for ${name}. Returning to authentication.`);
          window.setTimeout(() => {
            hideEnrollment();
            setScreenVisibility("face-auth", true);
            updateAuthStatus("Face enrolled. Continue with authentication.");
          }, 1500);
        } else {
          updateEnrollmentStatus("Enrollment failed. Try again with better lighting.");
        }
      } catch (error) {
        updateEnrollmentStatus("Enrollment failed.");
      }
    });
  }
}

function exposeFunctions() {
  eel.expose(hideLoader);
  eel.expose(hideFaceAuth);
  eel.expose(showEnrollment);
  eel.expose(hideEnrollment);
  eel.expose(hideFaceAuthSuccess);
  eel.expose(hideStart);
  eel.expose(updateCommand);
  eel.expose(triggerWakeAnimation);
  eel.expose(showAlert);
}

window.addEventListener("load", () => {
  exposeFunctions();
  if (window.AOS) {
    window.AOS.init({ once: true, duration: 650, easing: "ease-out-cubic" });
  }
  updateClock();
  window.setInterval(updateClock, 1000);
  refreshWeather();
  window.setInterval(refreshWeather, 5 * 60 * 1000);
  initChart();
  registerQuickActions();
  registerVoiceButton();
  registerEnrollmentControls();
  showOnly("loader");
  updateCommand("System startup", "Initializing Jarvis.");
  eel.init()();
});
