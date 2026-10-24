// The delay view (D2): two sessions on one lens, one 5 s and one 45 s behind the action. Each is
// sent the cards and the score its own video has reached, so the same goal lands in each panel at
// a different moment. The offsets are this view's; the lens is the session default.
const SESSION_KEY = "matchlens.delay.session_id.";
const OFFSETS_MS = [5_000, 45_000];

function setStatus(panels) {
  const el = document.getElementById("status");
  const live = panels.filter((p) => p.live).length;
  el.textContent = `live · ${live} of ${panels.length} viewers`;
  el.classList.toggle("live", live > 0);
}

async function connect(panel, offset, panels) {
  const session = await restoreOrCreateSession(SESSION_KEY + offset, { stream_offset_ms: offset });
  stream(panel, session, () => setStatus(panels), () => connect(panel, offset, panels));
  return session;
}

async function start() {
  const lenses = await (await fetch("/lenses")).json();
  const panels = [];
  for (const offset of OFFSETS_MS) {
    // The session picks the default lens; the panel shows it by name once the session says which.
    const session = await restoreOrCreateSession(SESSION_KEY + offset, { stream_offset_ms: offset });
    const lens = lenses.find((l) => l.lens_id === session.lens_id);
    const panel = new Panel({ ...lens, audience: `${offset / 1000} s behind the action` });
    panels.push(panel);
    document.getElementById("panels").append(panel.root);
    stream(panel, session, () => setStatus(panels), () => connect(panel, offset, panels));
  }
  setStatus(panels);
}

start();
