const STORAGE_KEY = "hookat-dating-state-v2";
const ANONYMOUS_USER_KEY = "hookat-anonymous-user-id";
const DEFAULT_PROFILE_IMAGE = "assets/default-avatar.png";

const seedProfiles = [
  {
    id: "maya",
    name: "Sloane",
    gender: "Women",
    age: 29,
    city: "Brooklyn",
    bio: "Direct, selective, and not here for vague intentions.",
    interests: ["verified", "tonight", "chemistry"],
    image: "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=82",
    likesUser: true,
  },
  {
    id: "noah",
    name: "Nico",
    gender: "Men",
    age: 32,
    city: "Queens",
    bio: "Clear plans, clean boundaries, no endless small talk.",
    interests: ["discreet", "consent", "nearby"],
    image: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=900&q=82",
    likesUser: false,
  },
  {
    id: "leah",
    name: "Raine",
    gender: "Women",
    age: 27,
    city: "Jersey City",
    bio: "Flirty first, honest always. I like people who say what they mean.",
    interests: ["chat first", "playful", "adult only"],
    image: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=900&q=82",
    likesUser: true,
  },
  {
    id: "eli",
    name: "Dante",
    gender: "Men",
    age: 31,
    city: "Hoboken",
    bio: "No pressure, no games, just mutual interest and respect.",
    interests: ["private", "respectful", "available"],
    image: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=900&q=82",
    likesUser: true,
  },
];

const starterMessages = {
  maya: [{ from: "maya", text: "Matched. What are you looking for tonight?" }],
  leah: [{ from: "leah", text: "I like clear energy. Chat first?" }],
  eli: [{ from: "eli", text: "Your profile is direct. I respect that." }],
};

const fallbackState = {
  currentUser: null,
  savedUser: null,
  profiles: seedProfiles,
  seen: [],
  liked: [],
  passed: [],
  reported: [],
  matches: [],
  messages: {},
  activeChat: null,
  bannedUsers: [],
  blockedUsers: [],
};

let state = loadState();
let apiConfig = { storageMode: "database", apiAvailable: false };
let isSubmitting = false;

const authView = document.querySelector("#auth-view");
const appView = document.querySelector("#app-view");
const screenTitle = document.querySelector("#screen-title");
const signOutButton = document.querySelector("#sign-out-button");
const authForm = document.querySelector("#auth-form");
const chatPeople = document.querySelector("#chat-people");
const chatTitle = document.querySelector("#chat-title");
const chatFilterTitle = document.querySelector("#chat-filter-title");
const messages = document.querySelector("#messages");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const photoInput = document.querySelector("#photo-input");
const photoPreview = document.querySelector("#photo-preview");
const storageModeNote = document.querySelector("#storage-mode-note");
const saveStatus = document.querySelector("#save-status");
let onboardingStep = 0;

function loadState() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return structuredClone(fallbackState);

  try {
    return { ...structuredClone(fallbackState), ...JSON.parse(stored) };
  } catch {
    return structuredClone(fallbackState);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function getAnonymousUserId() {
  const existing = localStorage.getItem(ANONYMOUS_USER_KEY);
  if (existing) return existing;
  const generated = crypto.randomUUID
    ? crypto.randomUUID()
    : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (char) =>
      (Number(char) ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(char) / 4)))).toString(16),
    );
  localStorage.setItem(ANONYMOUS_USER_KEY, generated);
  return generated;
}

function setSaveStatus(message, type = "") {
  if (!saveStatus) return;
  saveStatus.textContent = message;
  saveStatus.classList.toggle("success", type === "success");
  saveStatus.classList.toggle("error", type === "error");
}

function setSubmitting(value) {
  isSubmitting = value;
  const submitButton = authForm.querySelector('button[type="submit"]');
  if (submitButton) submitButton.disabled = value;
}

function syncStorageModeNote() {
  const isLocalDemo = apiConfig.storageMode === "local" || !apiConfig.apiAvailable;
  storageModeNote?.classList.toggle("hidden", !isLocalDemo);
}

async function loadApiConfig() {
  try {
    const response = await fetch("/api/config", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("Config request failed.");
    const payload = await response.json();
    apiConfig = {
      storageMode: payload.data?.storage_mode === "local" ? "local" : "database",
      apiAvailable: true,
    };
  } catch {
    apiConfig = { storageMode: "local", apiAvailable: false };
  }
  syncStorageModeNote();
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Anonymous-User-Id": getAnonymousUserId(),
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.success) {
    const message = payload?.error?.message || "Request failed.";
    throw new Error(message);
  }
  return payload.data;
}

function validateNameForSave(name) {
  const trimmed = name.trim();
  if (!trimmed) throw new Error("Name cannot be empty.");
  if (trimmed.length > 100) throw new Error("Name must be 100 characters or fewer.");
  if (/[<>\u0000-\u001f\u007f]/.test(trimmed)) throw new Error("Name contains unsupported characters.");
  return trimmed;
}

async function hashPassword(password) {
  if (!crypto.subtle) {
    let hash = 2166136261;
    for (const char of password) hash = (hash ^ char.charCodeAt(0)) * 16777619;
    return `local-demo-${(hash >>> 0).toString(16)}`;
  }
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(password));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function buildUserProfile(image, passwordHash) {
  return {
    email: document.querySelector("#email-input").value.trim(),
    passwordHash,
    name: validateNameForSave(document.querySelector("#name-input").value),
    age: Number(document.querySelector("#age-input").value),
    city: document.querySelector("#city-input").value.trim(),
    seeking: document.querySelector("#seeking-input").value,
    intent: document.querySelector("#intent-input").value,
    bio: document.querySelector("#bio-input").value.trim(),
    image: image || DEFAULT_PROFILE_IMAGE,
    adultConfirmed: document.querySelector("#adult-input").checked,
  };
}

function buildCriteriaPayload(user) {
  return {
    target_type: user.seeking || "Everyone",
    location: null,
    age_min: null,
    age_max: null,
    interests: [],
    required_conditions: {},
    preferred_conditions: user.intent ? { intent: user.intent } : {},
    free_text_requirement: user.bio || null,
  };
}

async function persistProfileAndCriteria(user) {
  const profileData = await apiFetch("/api/profiles", {
    method: "POST",
    body: {
      name: user.name,
      age: user.age,
      city: user.city,
      seeking: user.seeking,
      intent: user.intent,
      bio: user.bio,
      image_url: null,
    },
  });
  const profile = profileData.profile;
  const criteriaData = await apiFetch(`/api/profiles/${profile.id}/criteria`, {
    method: "POST",
    body: buildCriteriaPayload(user),
  });
  const criteria = criteriaData.criteria;
  const matchData = await apiFetch("/api/matches/search", {
    method: "POST",
    body: {
      profile_id: profile.id,
      criteria_id: criteria.id,
      limit: 20,
    },
  });

  return {
    profileId: profile.id,
    criteriaId: criteria.id,
    matches: (matchData.matches || []).map(mapApiMatchToProfile),
  };
}

function mapApiMatchToProfile(match) {
  const profile = match.profile || {};
  return {
    id: profile.id || match.profile_id,
    name: profile.name || "Match",
    gender: profile.gender || "Other",
    age: profile.age || "",
    city: profile.city || "",
    bio: profile.bio || "",
    interests: profile.interests || [],
    image: profile.image_url || DEFAULT_PROFILE_IMAGE,
    likesUser: true,
    score: match.score,
    structuredScore: match.structured_score,
    semanticScore: match.semantic_score,
    semanticSource: match.semantic_source,
  };
}

function readImageFile(input) {
  const file = input.files?.[0];
  if (!file) return Promise.resolve("");
  if (!file.type.startsWith("image/")) return Promise.reject(new Error("Please upload an image file."));

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The image could not be read."));
    reader.readAsDataURL(file);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setTitle(title) {
  screenTitle.textContent = title;
}

function showOnboardingStep(step) {
  onboardingStep = step;
  document.querySelectorAll(".onboarding-step").forEach((panel) => {
    panel.classList.toggle("hidden", Number(panel.dataset.step) !== onboardingStep);
  });

  document.querySelectorAll(".step-dot").forEach((dot) => {
    dot.classList.toggle("active", Number(dot.dataset.stepDot) === onboardingStep);
  });
}

function validateOnboardingStep(step) {
  if (step === 0) {
    const adultConfirmed = document.querySelector("#adult-input").checked;
    if (!adultConfirmed) alert("Please confirm you are 18+ to continue.");
    return adultConfirmed;
  }

  if (step === 1) {
    const fields = ["#email-input", "#password-input", "#name-input"].map((selector) =>
      document.querySelector(selector),
    );
    const allValid = fields.every((field) => field.checkValidity());
    const password = document.querySelector("#password-input").value;

    if (!allValid) {
      alert("Please complete your account details.");
      return false;
    }
    if (password.length < 8) {
      alert("Please use a password with at least 8 characters.");
      return false;
    }
  }

  if (step === 2) {
    const fields = ["#age-input", "#city-input"].map((selector) => document.querySelector(selector));
    const allValid = fields.every((field) => field.checkValidity());
    const age = Number(document.querySelector("#age-input").value);

    if (!allValid) {
      alert("Please complete your profile basics.");
      return false;
    }
    if (age < 18) {
      alert("HookAt is only for adults 18+.");
      return false;
    }
  }

  if (step === 4) {
    const seeking = document.querySelector("#seeking-input").value;
    const intent = document.querySelector("#intent-input").value;
    const bio = document.querySelector("#bio-input").value.trim();
    if (!seeking) {
      alert("Please choose who you want to meet.");
      return false;
    }
    if (!intent) {
      alert("Please choose what you are looking for.");
      return false;
    }
    if (!bio) {
      alert("Please add a short bio.");
      return false;
    }
  }

  return true;
}

function render() {
  if (state.currentUser && state.bannedUsers.includes("current-user")) {
    alert("This account has been banned by admin.");
    state.currentUser = null;
    saveState();
  }

  const isLoggedIn = Boolean(state.currentUser);
  document.body.classList.toggle("is-app-mode", isLoggedIn);
  authView.classList.toggle("hidden", isLoggedIn);
  appView.classList.toggle("hidden", !isLoggedIn);
  signOutButton.classList.toggle("hidden", !isLoggedIn);

  if (!isLoggedIn) {
    setTitle("Create your account");
    showOnboardingStep(onboardingStep);
    return;
  }

  setTitle(`Welcome, ${state.currentUser.name}`);
  renderChat();
}

function getAllowedGenders() {
  const seeking = state.currentUser?.seeking || "Everyone";
  if (seeking === "Women") return ["Women"];
  if (seeking === "Men") return ["Men"];
  if (seeking === "Other") return ["Other"];
  return ["Women", "Men", "Other"];
}

function getSeekingLabel() {
  const seeking = state.currentUser?.seeking || "Everyone";
  if (seeking === "Everyone") return "Both";
  return seeking;
}

function renderChat() {
  const allowedGenders = getAllowedGenders();
  const chatCandidates = state.profiles.filter((profile) => {
    const isAllowedGender = allowedGenders.includes(profile.gender || "Other");
    const isBanned = state.bannedUsers.includes(profile.id);
    const isBlocked = state.blockedUsers.includes(profile.id);
    return isAllowedGender && !isBanned && !isBlocked;
  });
  let activeProfile = chatCandidates.find((profile) => profile.id === state.activeChat) || chatCandidates[0];
  if (activeProfile) state.activeChat = activeProfile.id;
  if (chatFilterTitle) chatFilterTitle.textContent = `Showing: ${getSeekingLabel()}`;

  chatPeople.innerHTML = chatCandidates.length
    ? chatCandidates
      .map(
        (match) => `
          <button class="person-row ${state.activeChat === match.id ? "active" : ""}" data-chat="${match.id}" type="button">
            <img class="avatar" src="${match.image}" alt="${match.name}" />
            <span>
              <h4>${escapeHtml(match.name)}</h4>
              <p>${escapeHtml(match.age)} - ${escapeHtml(match.gender || "Other")} - ${escapeHtml(match.city)}</p>
              <em>${escapeHtml(match.interests.slice(0, 2).join(" / "))}</em>
            </span>
          </button>
        `,
      )
      .join("")
    : `<div class="empty-state"><h3>No users found</h3><p>No visible users match your preference.</p></div>`;

  chatTitle.innerHTML = activeProfile
    ? `<img class="chat-title-avatar" src="${activeProfile.image}" alt="${activeProfile.name}" /><span>${escapeHtml(activeProfile.name)}<small>${escapeHtml(activeProfile.city)}</small></span>`
    : "Choose a match";
  messageInput.disabled = !activeProfile;
  messageForm.querySelector("button").disabled = !activeProfile;

  const thread = state.messages[state.activeChat] || [];
  messages.innerHTML = activeProfile
    ? thread
        .map((message) => `<div class="message ${message.from === "me" ? "mine" : ""}">${escapeHtml(message.text)}</div>`)
        .join("")
    : `<div class="empty-state"><p>Select a match to start talking.</p></div>`;
  messages.scrollTop = messages.scrollHeight;
}

function findProfile(id) {
  return state.profiles.find((profile) => profile.id === id);
}

function seeProfile(id) {
  if (!state.seen.includes(id)) state.seen.push(id);
}

function likeProfile(id) {
  const profile = findProfile(id);
  if (!profile) return;

  seeProfile(id);
  if (!state.liked.includes(id)) state.liked.push(id);

  if (profile.likesUser && !state.matches.includes(id)) {
    state.matches.push(id);
    state.activeChat = id;
    state.messages[id] = state.messages[id] || starterMessages[id] || [];
    activateTab("chat");
  }

  saveState();
  render();
}

function passProfile(id) {
  seeProfile(id);
  if (!state.passed.includes(id)) state.passed.push(id);
  saveState();
  render();
}

function reportProfile(id) {
  seeProfile(id);
  if (!state.reported.includes(id)) state.reported.push(id);
  saveState();
  render();
}

function activateTab(tabName) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== `${tabName}-panel`);
  });
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isSubmitting) return;
  if (!validateOnboardingStep(0) || !validateOnboardingStep(1) || !validateOnboardingStep(2) || !validateOnboardingStep(4)) return;
  const age = Number(document.querySelector("#age-input").value);
  const password = document.querySelector("#password-input").value;

  if (age < 18) {
    alert("HookAt is only for adults 18+.");
    return;
  }

  if (password.length < 8) {
    alert("Please use a password with at least 8 characters.");
    return;
  }

  let image = "";
  try {
    setSubmitting(true);
    setSaveStatus("Saving...");
    image = await readImageFile(photoInput);
  } catch (error) {
    setSaveStatus(error.message, "error");
    setSubmitting(false);
    return;
  }

  try {
    const user = buildUserProfile(image, await hashPassword(password));
    const isLocalDemo = apiConfig.storageMode === "local" || !apiConfig.apiAvailable;
    if (!isLocalDemo) {
      const saved = await persistProfileAndCriteria(user);
      user.profileId = saved.profileId;
      user.criteriaId = saved.criteriaId;
      state.profiles = saved.matches;
    }
    state.currentUser = user;
    state.savedUser = { ...state.currentUser };
    saveState();
    setSaveStatus(isLocalDemo ? "Saved on this device only." : "Saved successfully.", "success");
    render();
  } catch (error) {
    setSaveStatus(`Save failed. ${error.message}`, "error");
  } finally {
    setSubmitting(false);
  }
});

photoInput.addEventListener("change", async () => {
  let image = "";
  try {
    image = await readImageFile(photoInput);
  } catch (error) {
    alert(error.message);
    photoInput.value = "";
    return;
  }

  photoPreview.innerHTML = image
    ? `<div class="upload-image" style="background-image: url('${image}')"></div><span>Photo selected</span>`
    : "No photo selected";
});

signOutButton.addEventListener("click", () => {
  state.currentUser = null;
  state.activeChat = null;
  saveState();
  render();
});

document.addEventListener("click", (event) => {
  const actionButton = event.target.closest("[data-action]");
  const chatButton = event.target.closest("[data-chat]");
  const tabButton = event.target.closest("[data-tab]");
  const nextStepButton = event.target.closest("[data-next-step]");
  const previousStepButton = event.target.closest("[data-previous-step]");

  if (nextStepButton) {
    if (validateOnboardingStep(onboardingStep)) showOnboardingStep(Number(nextStepButton.dataset.nextStep));
  }

  if (previousStepButton) showOnboardingStep(Number(previousStepButton.dataset.previousStep));

  if (chatButton) {
    state.activeChat = chatButton.dataset.chat;
    saveState();
    render();
  }
});

messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || !state.activeChat) return;

  state.messages[state.activeChat] = state.messages[state.activeChat] || [];
  state.messages[state.activeChat].push({ from: "me", text });
  messageInput.value = "";
  saveState();
  renderChat();
});

async function initializeApp() {
  await loadApiConfig();
  render();
}

initializeApp();
