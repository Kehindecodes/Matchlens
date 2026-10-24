// The viewer view: one session, one stream, one lens at a time. Switching is a POST; the stream
// stays open and the next card is the new lens's (L5).
const SESSION_KEY = "matchlens.watch.session_id";

function setStatus(panel) {
  const el = document.getElementById("status");
  el.textContent = panel.live ? `live · ${panel.lens.name}` : "reconnecting…";
  el.classList.toggle("live", Boolean(panel.live));
}

function showPicker(lenses, current, onPick) {
  const picker = document.getElementById("picker");
  picker.replaceChildren(
    ...lenses.map((lens) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = lens.name;
      button.title = `For ${lens.audience}`;
      button.setAttribute("aria-pressed", String(lens.lens_id === current));
      button.addEventListener("click", () => onPick(lens));
      return button;
    }),
  );
}

async function start() {
  const lenses = await (await fetch("/lenses")).json();
  let session = await restoreOrCreateSession(SESSION_KEY, {});
  const panel = new Panel(lenses.find((l) => l.lens_id === session.lens_id) ?? lenses[0]);
  document.getElementById("panels").append(panel.root);

  // Clicks during a switch are not dropped: the last lens picked is the one the session ends on.
  let wanted = null;
  let switching = false;
  async function pick(lens) {
    wanted = lens;
    if (switching) return;
    switching = true;
    while (wanted && wanted.lens_id !== session.lens_id) {
      const next = wanted;
      const res = await fetch(`/session/${encodeURIComponent(session.session_id)}/lens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lens_id: next.lens_id, focus_team: next.focus_team }),
      });
      if (!res.ok) break; // refused: the session is unchanged, and so is the picker
      session = await res.json();
      panel.switchTo(next);
      setStatus(panel);
    }
    wanted = null;
    switching = false;
    showPicker(lenses, session.lens_id, pick);
  }

  showPicker(lenses, session.lens_id, pick);
  // A reopen keeps this session if the server still knows it, and starts one on the panel's
  // lens if it does not, e.g. after a delivery restart.
  const open = async () => {
    const lens = panel.lens;
    session = await restoreOrCreateSession(SESSION_KEY, { lens_id: lens.lens_id, focus_team: lens.focus_team });
    stream(panel, session, () => setStatus(panel), open);
  };
  open();
}

start();
