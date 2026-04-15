const STORAGE_KEY = "hookat-dating-state-v2";
const DEFAULT_PROFILE_IMAGE = "assets/default-avatar.png";

const demoProfiles = [
  {
    id: "maya",
    name: "Sloane",
    gender: "Women",
    age: 29,
    city: "Brooklyn",
    email: "demo+sloane@hookat.local",
    bio: "Direct, selective, and not here for vague intentions.",
    intent: "Direct chemistry",
    seeking: "Everyone",
    image: "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=82",
  },
  {
    id: "noah",
    name: "Nico",
    gender: "Men",
    age: 32,
    city: "Queens",
    email: "demo+nico@hookat.local",
    bio: "Clear plans, clean boundaries, no endless small talk.",
    intent: "Tonight only",
    seeking: "Everyone",
    image: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=900&q=82",
  },
  {
    id: "leah",
    name: "Raine",
    gender: "Women",
    age: 27,
    city: "Jersey City",
    email: "demo+raine@hookat.local",
    bio: "Flirty first, honest always. I like people who say what they mean.",
    intent: "Flirty chat first",
    seeking: "Everyone",
    image: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=900&q=82",
  },
  {
    id: "eli",
    name: "Dante",
    gender: "Men",
    age: 31,
    city: "Hoboken",
    email: "demo+dante@hookat.local",
    bio: "No pressure, no games, just mutual interest and respect.",
    intent: "Open to repeats",
    seeking: "Everyone",
    image: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=900&q=82",
  },
];

const usersRoot = document.querySelector("#admin-users");

function loadState() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) {
    return { savedUser: null, currentUser: null, profiles: demoProfiles, bannedUsers: [], blockedUsers: [] };
  }

  try {
    return {
      savedUser: null,
      currentUser: null,
      profiles: demoProfiles,
      bannedUsers: [],
      blockedUsers: [],
      ...JSON.parse(stored),
    };
  } catch {
    return { savedUser: null, currentUser: null, profiles: demoProfiles, bannedUsers: [], blockedUsers: [] };
  }
}

function saveState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getUsers(state) {
  const realUser = state.savedUser
    ? {
      ...state.savedUser,
      id: "current-user",
      gender: "Account user",
      source: "Registered on this device",
      loginStatus: state.currentUser ? "Logged in" : "Logged out",
    }
    : null;
  const demoUsers = (state.profiles || demoProfiles).map((profile) => ({
    ...profile,
    source: "Demo user",
    loginStatus: "Demo only",
  }));

  return [realUser, ...demoUsers].filter(Boolean);
}

function render() {
  const state = loadState();
  const users = getUsers(state);

  usersRoot.innerHTML = users
    .map((user) => {
      const isBanned = state.bannedUsers.includes(user.id);
      const isBlocked = state.blockedUsers.includes(user.id);
      return `
        <article class="admin-user">
          <img class="admin-photo" src="${user.image || DEFAULT_PROFILE_IMAGE}" alt="${escapeHtml(user.name)}" />
          <div class="admin-user-main">
            <div class="admin-user-top">
              <div>
                <h2>${escapeHtml(user.name)}, ${escapeHtml(user.age || "N/A")}</h2>
                <p>${escapeHtml(user.gender || "Unknown")} - ${escapeHtml(user.city || "Unknown city")}</p>
              </div>
              <div class="admin-statuses">
                <span class="${isBanned ? "danger-status" : ""}">${isBanned ? "Banned" : "Active"}</span>
                <span class="${isBlocked ? "danger-status" : ""}">${isBlocked ? "Blocked" : "Visible"}</span>
              </div>
            </div>
            <div class="admin-grid">
              <p><strong>Email</strong>${escapeHtml(user.email || "No email")}</p>
              <p><strong>Login</strong>${escapeHtml(user.loginStatus)}</p>
              <p><strong>Password</strong>Hidden</p>
              <p><strong>Seeking</strong>${escapeHtml(user.seeking || "Everyone")}</p>
              <p><strong>Intent</strong>${escapeHtml(user.intent || "Not set")}</p>
              <p><strong>Source</strong>${escapeHtml(user.source)}</p>
            </div>
            <p class="admin-bio">${escapeHtml(user.bio || "")}</p>
            <div class="admin-actions">
              <button class="ghost-button" data-admin-action="ban" data-user-id="${user.id}" type="button">${isBanned ? "Unban" : "Ban"}</button>
              <button class="ghost-button" data-admin-action="block" data-user-id="${user.id}" type="button">${isBlocked ? "Unblock" : "Block"}</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

document.addEventListener("click", (event) => {
  const actionButton = event.target.closest("[data-admin-action]");
  if (!actionButton) return;

  const state = loadState();
  const userId = actionButton.dataset.userId;
  const listName = actionButton.dataset.adminAction === "ban" ? "bannedUsers" : "blockedUsers";
  const list = state[listName] || [];

  state[listName] = list.includes(userId) ? list.filter((id) => id !== userId) : [...list, userId];
  saveState(state);
  render();
});

render();
