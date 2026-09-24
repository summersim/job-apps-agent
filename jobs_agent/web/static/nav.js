// Shared by every authenticated page's nav bar.
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("nav-logout");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      await fetch("/api/logout", { method: "POST" });
    } finally {
      location.href = "/login";
    }
  });
});
