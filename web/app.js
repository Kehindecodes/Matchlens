// The demo view: one panel per lens, each its own session and stream (Q24: A), on one clock.
const SESSION_KEY = "matchlens.session_id.";

function setStatus(panels) {
  const el = document.getElementById("status");
  const live = panels.filter((p) => p.live).length;
  el.textContent = `live · ${live} of ${panels.length} lenses`;
  el.classList.toggle("live", live > 0);
}

async function connect(panel, panels) {
  const lens = panel.lens;
  const session = await restoreOrCreateSession(SESSION_KEY + lens.lens_id, {
    lens_id: lens.lens_id,
    focus_team: lens.focus_team,
  });
  stream(panel, session, () => setStatus(panels), () => connect(panel, panels));
}

async function start() {
  const lenses = await (await fetch("/lenses")).json();
  const panels = lenses.map((lens) => new Panel(lens));
  document.getElementById("panels").append(...panels.map((p) => p.root));
  setStatus(panels);
  panels.forEach((p) => connect(p, panels));
}

start();
