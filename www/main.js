const screenIds = ["loader", "face-auth", "face-auth-success", "start"];

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

function hideFaceAuthSuccess() {
  const successScreen = document.getElementById("face-auth-success");
  if (!successScreen) {
    return;
  }
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

function updateClock() {
  const now = new Date();
  const clockElement = document.getElementById("live-clock");
  const dateElement = document.getElementById("live-date");

  if (clockElement) {
    clockElement.textContent = now.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  if (dateElement) {
    dateElement.textContent = now.toLocaleDateString([], {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }
}

function updateDashboard(commandText, responseText) {
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
  if (voiceCommand) {
    voiceCommand.value = commandText || "";
  }
}

async function processVoiceCommand() {
  updateAuthStatus("Listening for your voice command...");
  try {
    const commandText = await eel.takecommand()();
    if (!commandText || commandText === "none") {
      updateDashboard("None", "No command detected.");
      return;
    }

    const responseText = await eel.allCommands(commandText)();
    updateDashboard(commandText, responseText);
  } catch (error) {
    updateDashboard("Error", "Voice capture failed.");
  }
}

function registerQuickActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const commandText = button.getAttribute("data-action") || "";
      const responseText = await eel.allCommands(commandText)();
      updateDashboard(commandText, responseText);
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
        updateDashboard(commandText, responseText);
      }
    });
  }
}

function exposeFunctions() {
  eel.expose(hideLoader);
  eel.expose(hideFaceAuth);
  eel.expose(hideFaceAuthSuccess);
  eel.expose(hideStart);
}

window.addEventListener("load", () => {
  exposeFunctions();
  updateClock();
  window.setInterval(updateClock, 1000);
  registerQuickActions();
  registerVoiceButton();
  showOnly("loader");
  updateDashboard("System startup", "Initializing Jarvis.");
  eel.init()();
});
