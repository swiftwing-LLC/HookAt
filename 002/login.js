const STORAGE_KEY = "hookat-dating-state-v2";

const loginForm = document.querySelector("#login-form");
const emailInput = document.querySelector("#login-email");
const passwordInput = document.querySelector("#login-password");

function loadState() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return null;

  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
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

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const state = loadState();
  const savedUser = state?.savedUser;

  if (!savedUser) {
    alert("No local HookAt account found. Please create an account first.");
    window.location.href = "index.html";
    return;
  }

  if ((state.bannedUsers || []).includes("current-user")) {
    alert("This account has been banned by admin.");
    return;
  }

  const emailMatches = savedUser.email === emailInput.value.trim();
  const passwordMatches = savedUser.passwordHash
    ? savedUser.passwordHash === await hashPassword(passwordInput.value)
    : savedUser.password === passwordInput.value;

  if (!emailMatches || !passwordMatches) {
    alert("Email or password is incorrect.");
    return;
  }

  delete savedUser.password;
  state.currentUser = { ...savedUser };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  window.location.href = "index.html";
});
