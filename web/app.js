// One session per tab: sessionStorage survives a reload but is not shared between tabs.
const SESSION_KEY = "matchlens.session_id";

async function createSession() {
  const res = await fetch("/session", { method: "POST" });
  const session = await res.json();
  sessionStorage.setItem(SESSION_KEY, session.session_id);
  return session;
}

async function restoreOrCreateSession() {
  const id = sessionStorage.getItem(SESSION_KEY);
  if (id) {
    const res = await fetch(`/session/${encodeURIComponent(id)}`);
    if (res.ok) return res.json();
  }
  return createSession(); // first visit, or the server no longer knows this session
}

function mmss(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function show(state) {
  const [home, away] = state.score;
  document.getElementById("home-name").textContent = home.short_name;
  document.getElementById("away-name").textContent = away.short_name;
  document.getElementById("home-goals").textContent = home.goals;
  document.getElementById("away-goals").textContent = away.goals;
  document.getElementById("clock").textContent = mmss(state.clock_ms);
  document.getElementById("period").textContent = state.period === 1 ? "1st half" : "2nd half";
}

function addCard(card) {
  const li = document.createElement("li");
  li.className = "card";
  const time = document.createElement("time");
  time.textContent = mmss(card.display_at_clock);
  const h2 = document.createElement("h2");
  h2.textContent = card.rendition.headline;
  const p = document.createElement("p");
  p.textContent = card.rendition.body;
  li.append(time, h2, p);
  document.getElementById("cards").prepend(li); // newest first
}

function setStatus(text, live) {
  const el = document.getElementById("status");
  el.textContent = text;
  el.classList.toggle("live", live);
}

let unloading = false;
window.addEventListener("pagehide", () => { unloading = true; });

async function connect() {
  const session = await restoreOrCreateSession();
  // EventSource reconnects by itself and sends Last-Event-ID, so the server resumes from there.
  const source = new EventSource(`/stream?session_id=${encodeURIComponent(session.session_id)}`);
  source.addEventListener("open", () => setStatus(`live · ${session.lens_id}`, true));
  source.addEventListener("match_state", (e) => show(JSON.parse(e.data)));
  source.addEventListener("card", (e) => addCard(JSON.parse(e.data)));
  source.addEventListener("error", () => {
    if (unloading) return; // a reload closes the stream; that is not a lost session
    setStatus("reconnecting…", false);
    if (source.readyState === EventSource.CLOSED) {
      // The browser gave up, e.g. the stream was refused. restoreOrCreateSession() keeps this
      // session if the server still knows it, and only starts a new one if it does not.
      setTimeout(connect, 2000);
    }
  });
}

connect();
