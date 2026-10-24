// What the demo view (index.html) and the viewer view (watch.html) share: the clock spine, a
// lens panel, and a session with its stream. Plain scripts, no modules, no build step.

const JUST_SPOKE_MS = 60_000; // match time a card counts as just said, before the panel reads as quiet

let spineSeq = -1; // the newest match state shown; every stream carries the same hub sequence
let teamNames = {}; // team_id -> short name, from the match state

function mmss(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function showSpine(state) {
  if (!document.getElementById("clock")) return; // a view with no shared spine (delay.html)
  if (state.seq <= spineSeq) return; // another stream already showed this instant
  spineSeq = state.seq;
  const [home, away] = state.score;
  teamNames = { [home.team_id]: home.short_name, [away.team_id]: away.short_name };
  document.getElementById("home-name").textContent = home.short_name;
  document.getElementById("away-name").textContent = away.short_name;
  document.getElementById("home-goals").textContent = home.goals;
  document.getElementById("away-goals").textContent = away.goals;
  document.getElementById("clock").textContent = mmss(state.clock_ms);
  document.getElementById("period").textContent = state.period === 1 ? "1st half" : "2nd half";
}

// --- playback: the speed every viewer shares, and watching from kickoff (D3, D33) ---------------

const SPEEDS = [1, 5, 25, 50]; // the choices the page offers; the server refuses anything else past its max
const KICKOFF_KEY = "matchlens.kickoff_offset_ms"; // how far behind live this tab chose to watch

const KICKOFF_PENDING = "pending"; // chosen, but the live clock is read when the sessions are made

function kickoffOffset() {
  const ms = Number(sessionStorage.getItem(KICKOFF_KEY));
  return Number.isFinite(ms) && ms > 0 ? ms : 0;
}

// Read the live clock once, as late as possible, and share it with every panel in the tab, so
// they all start at 0:00 together rather than wherever the clock got to during the reload.
let kickoffRead = null;
function resolveKickoff() {
  if (sessionStorage.getItem(KICKOFF_KEY) !== KICKOFF_PENDING) return Promise.resolve();
  kickoffRead ??= fetch("/playback")
    .then((res) => res.json())
    .then(({ clock_ms }) => sessionStorage.setItem(KICKOFF_KEY, String(Math.max(0, clock_ms))));
  return kickoffRead;
}

let shownSpeed = null;

function showSpeed(speed) {
  shownSpeed = speed;
  const bar = document.getElementById("playback");
  if (!bar) return;
  bar.querySelector(".speed").textContent = speed === null ? "Speed: starting…" : `Speed ${speed}×`;
  bar.querySelectorAll("button[data-speed]").forEach((b) => {
    b.setAttribute("aria-pressed", String(Number(b.dataset.speed) === speed));
  });
}

async function chooseSpeed(speed) {
  const note = document.querySelector("#playback .note");
  const res = await fetch("/playback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speed }),
  });
  note.textContent = res.ok ? "Speed changes for everyone watching." : `The server refused ${speed}×.`;
}

// A new session for every panel in this tab, each that much further behind live: the tab then
// watches the match from 0:00 while everyone else carries on where they are.
function watchFromKickoff() {
  sessionStorage.clear();
  sessionStorage.setItem(KICKOFF_KEY, KICKOFF_PENDING);
  location.reload();
}

function backToLive() {
  sessionStorage.clear();
  location.reload();
}

function mountPlayback() {
  const bar = document.getElementById("playback");
  if (!bar) return;
  const speed = document.createElement("span");
  speed.className = "speed";
  const choices = document.createElement("span");
  choices.className = "choices";
  for (const x of SPEEDS) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.speed = String(x);
    b.textContent = `${x}×`;
    b.addEventListener("click", () => chooseSpeed(x));
    choices.append(b);
  }
  const behind = sessionStorage.getItem(KICKOFF_KEY) !== null;
  const jump = document.createElement("button");
  jump.type = "button";
  jump.className = "jump";
  jump.textContent = behind ? "Back to live" : "Watch from kickoff";
  jump.addEventListener("click", behind ? backToLive : watchFromKickoff);
  const note = document.createElement("span");
  note.className = "note";
  note.textContent = "Speed changes for everyone watching.";
  if (behind) resolveKickoff().then(() => {
    note.textContent = `Watching from kickoff, ${mmss(kickoffOffset())} behind live.`;
  });
  bar.replaceChildren(speed, choices, jump, note);
  showSpeed(shownSpeed);
}

mountPlayback();

// sessionStorage survives a reload but is not shared between tabs, so each tab is its own viewer.
async function restoreOrCreateSession(key, body) {
  const id = sessionStorage.getItem(key);
  if (id) {
    const res = await fetch(`/session/${encodeURIComponent(id)}`);
    if (res.ok) return res.json();
  }
  // First visit, or the server no longer knows this session.
  // A tab watching from kickoff puts every session it makes that far further behind.
  await resolveKickoff();
  const offset = kickoffOffset() + (body.stream_offset_ms || 0);
  const res = await fetch("/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, stream_offset_ms: offset }),
  });
  const session = await res.json();
  sessionStorage.setItem(key, session.session_id);
  return session;
}

class Panel {
  constructor(lens) {
    this.lens = lens;
    this.live = null; // null until the stream first opens, false once it has been lost
    this.count = 0;
    this.lastSpoke = null; // match clock of the newest card
    this.clock = null; // match clock this panel's own stream last reported
    const root = document.getElementById("panel-template").content.firstElementChild.cloneNode(true);
    this.root = root;
    this.title = root.querySelector("h2");
    this.audience = root.querySelector(".audience");
    this.countEl = root.querySelector(".count");
    this.quiet = root.querySelector(".quiet");
    this.cards = root.querySelector(".cards");
    this.render();
  }

  render() {
    const team = this.lens.focus_team && teamNames[this.lens.focus_team];
    this.title.textContent = team ? `${this.lens.name} · ${team}` : this.lens.name;
    this.audience.textContent = this.lens.audience;
    this.countEl.textContent = `${this.count} ${this.count === 1 ? "card" : "cards"}`;
    this.quiet.className = "quiet";
    if (this.live === null) {
      this.quiet.textContent = "Joining the match";
      return;
    }
    if (!this.live) {
      this.quiet.classList.add("lost");
      this.quiet.textContent = "Reconnecting to the match";
      return;
    }
    this.quiet.classList.add("listening");
    const at = this.clock === null ? "" : ` · ${mmss(this.clock)}`;
    if (this.lastSpoke === null) {
      this.quiet.textContent = `Watching · nothing worth saying yet${at}`;
    } else if (this.clock - this.lastSpoke < JUST_SPOKE_MS) {
      this.quiet.textContent = `Watching · just spoke${at}`;
    } else {
      const mins = Math.floor((this.clock - this.lastSpoke) / 60_000);
      this.quiet.textContent = `Watching · quiet for ${mins} min by choice${at}`;
    }
  }

  onState(state) {
    this.clock = state.clock_ms;
    // A view whose panels are on different offsets shows each one's own score (D32).
    const score = this.root.querySelector(".panel-score");
    if (score) {
      const [home, away] = state.score;
      score.textContent = `${home.short_name} ${home.goals}–${away.goals} ${away.short_name} · ${mmss(state.clock_ms)}`;
    }
    this.render();
  }

  // Cards are shown in the order delivery releases them, never reordered (invariant 8).
  addCard(card) {
    const li = document.createElement("li");
    li.className = "card";
    const time = document.createElement("time");
    time.textContent = mmss(card.display_at_clock);
    const h3 = document.createElement("h3");
    h3.textContent = card.rendition.headline;
    const p = document.createElement("p");
    p.textContent = card.rendition.body;
    li.append(time, h3, p);
    this.cards.prepend(li); // newest first
    this.count += 1;
    this.lastSpoke = card.display_at_clock;
    this.root.classList.add("spoke");
    clearTimeout(this.spokeTimer);
    this.spokeTimer = setTimeout(() => this.root.classList.remove("spoke"), 1500);
    this.render();
  }

  // What this lens showed before the viewer joined, told once above the cards (D4). It is not
  // a card: it is not counted, and it does not say the panel just spoke.
  showCatchUp(summary) {
    const section = document.createElement("section");
    section.className = "catchup";
    const h3 = document.createElement("h3");
    h3.textContent = `The match so far · to ${mmss(summary.to_clock)}`;
    const ol = document.createElement("ol");
    for (const line of summary.lines) {
      const li = document.createElement("li");
      const time = document.createElement("time");
      time.textContent = mmss(line.clock_ms);
      const strong = document.createElement("strong");
      strong.textContent = line.headline;
      const p = document.createElement("p");
      p.textContent = line.body;
      li.append(time, " ", strong, p);
      ol.append(li);
    }
    section.append(h3, ol);
    this.cards.before(section);
  }

  // A lens switch: the cards already shown stay as they were, and a marker says where the new
  // lens takes over. Nothing is re-rendered or back-filled (L5).
  switchTo(lens) {
    this.lens = lens;
    this.lastSpoke = null; // quiet is this lens's choice, so it is counted from the switch
    const li = document.createElement("li");
    li.className = "switch";
    li.textContent = this.clock === null ? `Now: ${lens.name}` : `Now: ${lens.name} · from ${mmss(this.clock)}`;
    this.cards.prepend(li);
    this.render();
  }
}

let unloading = false;
window.addEventListener("pagehide", () => { unloading = true; });

// Opens the session's stream into `panel`. `onStatus` is told whenever the stream opens or drops.
function stream(panel, session, onStatus, reopen) {
  // EventSource reconnects by itself and sends Last-Event-ID, so the server resumes from there.
  const source = new EventSource(`/stream?session_id=${encodeURIComponent(session.session_id)}`);
  source.addEventListener("open", () => {
    panel.live = true;
    panel.render();
    onStatus();
  });
  source.addEventListener("match_state", (e) => {
    const state = JSON.parse(e.data);
    showSpine(state);
    panel.onState(state);
  });
  source.addEventListener("card", (e) => panel.addCard(JSON.parse(e.data)));
  source.addEventListener("catch_up", (e) => panel.showCatchUp(JSON.parse(e.data)));
  source.addEventListener("playback", (e) => showSpeed(JSON.parse(e.data).speed));
  source.addEventListener("error", () => {
    if (unloading) return; // a reload closes the stream; that is not a lost session
    panel.live = false;
    panel.render();
    onStatus();
    if (source.readyState === EventSource.CLOSED) {
      // The browser gave up, e.g. the stream was refused. Reopening keeps this session if the
      // server still knows it, and only starts a new one if it does not.
      setTimeout(reopen, 2000);
    }
  });
}
