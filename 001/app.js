const STORAGE_KEY = "hookat-dating-state-v2";
const DEFAULT_PROFILE_IMAGE =
  "https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=900&q=82";

const seedProfiles = [
  {
    id: "maya",
    name: "Sloane",
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
};

let state = loadState();

const authView = document.querySelector("#auth-view");
const appView = document.querySelector("#app-view");
const screenTitle = document.querySelector("#screen-title");
const signOutButton = document.querySelector("#sign-out-button");
const authForm = document.querySelector("#auth-form");
const profileStage = document.querySelector("#profile-stage");
const matchList = document.querySelector("#match-list");
const chatPeople = document.querySelector("#chat-people");
const chatTitle = document.querySelector("#chat-title");
const messages = document.querySelector("#messages");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const profileForm = document.querySelector("#profile-form");
const photoInput = document.querySelector("#photo-input");
const editPhotoInput = document.querySelector("#edit-photo-input");
const profilePreview = document.querySelector("#profile-preview");
const photoPreview = document.querySelector("#photo-preview");
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
    const fields = ["#email-input", "#password-input", "#name-input", "#age-input", "#city-input"].map((selector) =>
      document.querySelector(selector),
    );
    const allValid = fields.every((field) => field.checkValidity());
    const age = Number(document.querySelector("#age-input").value);
    const password = document.querySelector("#password-input").value;

    if (!allValid) {
      alert("Please complete your account details.");
      return false;
    }
    if (age < 18) {
      alert("HookAt is only for adults 18+.");
      return false;
    }
    if (password.length < 8) {
      alert("Please use a password with at least 8 characters.");
      return false;
    }
  }

  if (step === 3) {
    const intent = document.querySelector("#intent-input").value;
    const bio = document.querySelector("#bio-input").value.trim();
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
  renderDiscover();
  renderMatches();
  renderChat();
  renderProfile();
}

function getNextProfile() {
  return state.profiles.find((profile) => !state.seen.includes(profile.id) && !state.reported.includes(profile.id));
}

function renderDiscover() {
  const profile = getNextProfile();

  if (!profile) {
    profileStage.innerHTML = `
      <div class="empty-state">
        <h3>No more profiles tonight</h3>
        <p>Check matches or refine your profile. New members can be added when the backend is connected.</p>
      </div>
    `;
    return;
  }

  profileStage.innerHTML = `
    <article class="profile-card">
      <div class="profile-photo" style="background-image: url('${profile.image}')">
        <div class="profile-name">
          <h3>${escapeHtml(profile.name)}, ${escapeHtml(profile.age)}</h3>
          <p>${escapeHtml(profile.city)}</p>
        </div>
      </div>
      <div class="profile-details">
        <p>${escapeHtml(profile.bio)}</p>
        <div class="chips">${profile.interests.map((interest) => `<span class="chip">${escapeHtml(interest)}</span>`).join("")}</div>
        <div class="profile-actions">
          <button class="pass-button" data-action="pass" data-id="${profile.id}" type="button">Pass</button>
          <button class="like-button" data-action="like" data-id="${profile.id}" type="button">Like</button>
          <button class="report-button" data-action="report" data-id="${profile.id}" type="button">Report</button>
        </div>
      </div>
    </article>
  `;
}

function renderMatches() {
  const matches = state.matches.map((id) => findProfile(id)).filter(Boolean);

  if (!matches.length) {
    matchList.innerHTML = `<div class="empty-state"><h3>No matches yet</h3><p>Like profiles in Discover to start a conversation.</p></div>`;
    return;
  }

  matchList.innerHTML = matches
    .map(
      (match) => `
        <article class="match-row">
          <img class="avatar" src="${match.image}" alt="${match.name}" />
          <div>
            <h4>${escapeHtml(match.name)}</h4>
            <p>${escapeHtml(match.city)} - ${escapeHtml(match.interests.join(", "))}</p>
          </div>
          <button class="primary-button compact" data-chat="${match.id}" type="button">Message</button>
        </article>
      `,
    )
    .join("");
}

function renderChat() {
  const matches = state.matches.map((id) => findProfile(id)).filter(Boolean);

  chatPeople.innerHTML = matches.length
    ? matches
        .map(
          (match) => `
            <button class="person-row ${state.activeChat === match.id ? "active" : ""}" data-chat="${match.id}" type="button">
              <img class="avatar" src="${match.image}" alt="${match.name}" />
              <span>
                <h4>${escapeHtml(match.name)}</h4>
                <p>${escapeHtml(match.city)}</p>
              </span>
            </button>
          `,
        )
        .join("")
    : `<div class="empty-state"><h3>No one to message yet</h3><p>Your matches will appear here.</p></div>`;

  const activeProfile = findProfile(state.activeChat);
  chatTitle.textContent = activeProfile ? `Chat with ${activeProfile.name}` : "Choose a match";
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

function renderProfile() {
  if (!state.currentUser) return;
  profilePreview.innerHTML = `
    <div class="preview-photo" style="background-image: url('${state.currentUser.image || DEFAULT_PROFILE_IMAGE}')"></div>
    <div>
      <p class="eyebrow">Your live profile</p>
      <h3>${escapeHtml(state.currentUser.name)}, ${escapeHtml(state.currentUser.age)}</h3>
      <p>${escapeHtml(state.currentUser.city)} - ${escapeHtml(state.currentUser.intent || "Direct chemistry")}</p>
      <p>${escapeHtml(state.currentUser.bio)}</p>
    </div>
  `;
  document.querySelector("#edit-name-input").value = state.currentUser.name;
  document.querySelector("#edit-age-input").value = state.currentUser.age;
  document.querySelector("#edit-city-input").value = state.currentUser.city;
  document.querySelector("#edit-intent-input").value = state.currentUser.intent || "Direct chemistry";
  document.querySelector("#edit-bio-input").value = state.currentUser.bio;
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
  if (!validateOnboardingStep(0) || !validateOnboardingStep(1) || !validateOnboardingStep(3)) return;
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
    image = await readImageFile(photoInput);
  } catch (error) {
    alert(error.message);
    return;
  }

  state.currentUser = {
    email: document.querySelector("#email-input").value.trim(),
    password,
    name: document.querySelector("#name-input").value.trim(),
    age,
    city: document.querySelector("#city-input").value.trim(),
    intent: document.querySelector("#intent-input").value,
    bio: document.querySelector("#bio-input").value.trim(),
    image: image || DEFAULT_PROFILE_IMAGE,
    adultConfirmed: document.querySelector("#adult-input").checked,
  };
  state.savedUser = { ...state.currentUser };
  saveState();
  render();
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

  if (actionButton?.dataset.action === "like") likeProfile(actionButton.dataset.id);
  if (actionButton?.dataset.action === "pass") passProfile(actionButton.dataset.id);
  if (actionButton?.dataset.action === "report") reportProfile(actionButton.dataset.id);

  if (chatButton) {
    state.activeChat = chatButton.dataset.chat;
    activateTab("chat");
    saveState();
    render();
  }

  if (tabButton) activateTab(tabButton.dataset.tab);
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

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  let newImage = "";
  try {
    newImage = await readImageFile(editPhotoInput);
  } catch (error) {
    alert(error.message);
    return;
  }

  const age = Number(document.querySelector("#edit-age-input").value);
  if (age < 18) {
    alert("HookAt is only for adults 18+.");
    return;
  }

  state.currentUser = {
    ...state.currentUser,
    name: document.querySelector("#edit-name-input").value.trim(),
    age,
    city: document.querySelector("#edit-city-input").value.trim(),
    intent: document.querySelector("#edit-intent-input").value,
    bio: document.querySelector("#edit-bio-input").value.trim(),
    image: newImage || state.currentUser.image,
  };
  editPhotoInput.value = "";
  saveState();
  render();
});

render();
