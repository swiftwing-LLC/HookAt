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

loginForm.addEventListener("submit", (event) => {
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
  const passwordMatches = savedUser.password === passwordInput.value;

  if (!emailMatches || !passwordMatches) {
    alert("Email or password is incorrect.");
    return;
  }

  state.currentUser = { ...savedUser };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  window.location.href = "index.html";
});
