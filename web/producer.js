// The producer view (P1, Q43): the demo view's panels, each with what a viewer is never shown.
// The panels, their sessions and the ladder strip are panel.js and app.js, unchanged. This adds
// the stream of what each lens last did and why, and shows it as it arrives. It works out
// nothing: the state, the words and the numbers are all the feed's.
//
// It also holds the controls (P2, Q44): mute and unmute a lens, with a reason. The page sends what
// was typed and shows what the feed says came of it.

const FEED_URL = "/producer/stream";
const MUTE_URL = "/producer/mute";
const UNMUTE_URL = "/producer/unmute";
const ACTION_WORDS = { suppress: "muted", release: "unmuted" };
// The panel's own idle line says "quiet by choice", which is untrue of a lens that is not choosing.
const STATES_THAT_ARE_NOT_A_CHOICE = ["broken", "alarm", "muted"];

function addRow(list, label) {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  list.append(term, detail);
  return detail;
}

// A refusal in the server's own words, or a plain one if it said none.
async function refusalOf(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch (_) { /* no body: fall through */ }
  return "The server refused it.";
}

// The reason box and the button under a panel's internals. It sends what was typed, to mute or to
// unmute as the button says, and the feed then says what came of it.
function mountControls(panel) {
  const controls = document.createElement("div");
  controls.className = "controls";
  const reason = document.createElement("input");
  reason.type = "text";
  reason.placeholder = "Reason (required)";
  reason.autocomplete = "off";
  reason.setAttribute("aria-label", `Reason to mute or unmute ${panel.lens.name}`);
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.next = "mute";
  button.textContent = "Mute this lens";
  const note = document.createElement("p");
  note.className = "note";
  note.setAttribute("role", "status");
  controls.append(reason, button, note);

  button.addEventListener("click", async () => {
    const text = reason.value.trim();
    if (!text) {
      note.textContent = "A reason is needed before a lens is muted or unmuted.";
      reason.focus();
      return;
    }
    const actor = document.getElementById("actor").value.trim() || "producer";
    const response = await fetch(button.dataset.next === "unmute" ? UNMUTE_URL : MUTE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lens_id: panel.lens.lens_id, reason: text, actor }),
    });
    if (response.ok) {
      note.textContent = "";
      reason.value = "";
    } else {
      note.textContent = await refusalOf(response);
    }
  });
  return { controls, button };
}

// The block under a panel's idle line. The state is a class, prefixed because `quiet` is already
// the idle line's, so a quiet lens and a broken one differ in their label, their border and their
// glyph as well as their colour.
function mountInternals(panel) {
  const root = document.createElement("div");
  root.className = "internals state-listening";
  root.setAttribute("role", "status");
  const headline = document.createElement("strong");
  headline.className = "headline";
  const why = document.createElement("p");
  why.className = "why";
  const mutedBy = document.createElement("p");
  mutedBy.className = "muted-by";
  mutedBy.hidden = true;
  const figures = document.createElement("dl");
  figures.className = "figures";
  const importance = addRow(figures, "Importance");
  const cards = addRow(figures, "Cards");
  root.append(headline, why, mutedBy, figures);
  panel.quiet.after(root);
  const { controls, button } = mountControls(panel);
  root.after(controls);
  return { root, headline, why, mutedBy, importance, cards, button };
}

function showLens(panel, internals, view) {
  internals.root.className = `internals state-${view.state}`;
  internals.headline.textContent = view.headline;
  internals.why.textContent = view.why;
  internals.mutedBy.hidden = view.muted === null;
  if (view.muted !== null) {
    const { actor, clock_ms, reason } = view.muted;
    internals.mutedBy.textContent = `${actor} muted it at ${mmss(clock_ms)}: ${reason}`;
  }
  internals.button.textContent = view.muted === null ? "Mute this lens" : "Unmute this lens";
  internals.button.dataset.next = view.muted === null ? "mute" : "unmute";
  internals.importance.textContent = view.importance === null
    ? "none yet"
    : `${view.importance.toFixed(2)} against a threshold of ${view.threshold.toFixed(2)}`;
  internals.cards.textContent = view.shown_in_window === null
    ? `up to ${view.max_cards_per_10min} in 10 min`
    : `${view.shown_in_window} of ${view.max_cards_per_10min} in the 10 min to ${mmss(view.as_of_clock)}`;
  panel.quiet.hidden = STATES_THAT_ARE_NOT_A_CHOICE.includes(view.state);
}

// Every mute and unmute, newest first, as the feed sent them.
function showActions(panels, actions) {
  const list = document.getElementById("actions");
  if (actions.length === 0) return; // the page's own "none yet" line stays
  const names = new Map(panels.map((panel) => [panel.lens.lens_id, panel.lens.name]));
  list.replaceChildren(...[...actions].reverse().map((action) => {
    const item = document.createElement("li");
    const lens = names.get(action.target_id.id) ?? action.target_id.id;
    item.textContent =
      `${mmss(action.clock_ms)} · ${action.actor} ${ACTION_WORDS[action.action]} ${lens} · ${action.reason}`;
    return item;
  }));
}

function setFeedStatus(live) {
  const el = document.getElementById("feed-status");
  el.textContent = live ? "producer feed: live" : "producer feed: lost, reconnecting";
  el.classList.toggle("live", live);
}

panelsMounted.then((panels) => {
  const internals = new Map(panels.map((panel) => [panel.lens.lens_id, mountInternals(panel)]));
  const source = new EventSource(FEED_URL);
  source.addEventListener("open", () => setFeedStatus(true));
  source.addEventListener("error", () => setFeedStatus(false));
  source.addEventListener("lenses", (event) => {
    const snapshot = JSON.parse(event.data);
    for (const view of snapshot.lenses) {
      const panel = panels.find((candidate) => candidate.lens.lens_id === view.lens_id);
      if (panel) showLens(panel, internals.get(view.lens_id), view);
    }
    showActions(panels, snapshot.actions);
  });
});
