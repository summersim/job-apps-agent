// Shared by login.html and signup.html — which one it's on is read from the
// form's data-mode attribute, so the same script posts to /api/login or
// /api/signup.
const form = document.getElementById("auth-form");
const msg = document.getElementById("auth-msg");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "";
  msg.classList.remove("err");

  const mode = form.dataset.mode;
  const email = form.email.value.trim();
  const password = form.password.value;
  const btn = form.querySelector("button[type=submit]");
  btn.disabled = true;

  try {
    const res = await fetch(`/api/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      msg.textContent = data.error || "Something went wrong.";
      msg.classList.add("err");
      return;
    }
    if (data.message) {
      msg.textContent = data.message;
      return;
    }
    location.href = "/";
  } catch (err) {
    msg.textContent = "Could not reach the server.";
    msg.classList.add("err");
  } finally {
    btn.disabled = false;
  }
});
