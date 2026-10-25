// The producer view (P1, Q43): the demo view's panels, each with what a viewer is never shown.
// The panels, their sessions and the ladder strip are panel.js and app.js, unchanged. This adds
// the stream of what each lens last did and why, and shows it as it arrives. It works out
// nothing: the state, the words and the numbers are all the feed's.

const FEED_URL = "/producer/stream";

function addRow(list, label) {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  list.append(term, detail);
  return detail;
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
  const figures = document.createElement("dl");
  figures.className = "figures";
  const importance = addRow(figures, "Importance");
  const cards = addRow(figures, "Cards");
  root.append(headline, why, figures);
  panel.quiet.after(root);
  return { root, headline, why, importance, cards };
}

function showLens(panel, internals, view) {
  internals.root.className = `internals state-${view.state}`;
  internals.headline.textContent = view.headline;
  internals.why.textContent = view.why;
  internals.importance.textContent = view.importance === null
    ? "none yet"
    : `${view.importance.toFixed(2)} against a threshold of ${view.threshold.toFixed(2)}`;
  internals.cards.textContent = view.shown_in_window === null
    ? `up to ${view.max_cards_per_10min} in 10 min`
    : `${view.shown_in_window} of ${view.max_cards_per_10min} in the 10 min to ${mmss(view.as_of_clock)}`;
  // The panel's own idle line reads "quiet by choice", which is only true of a lens that chose.
  panel.quiet.hidden = view.state === "broken" || view.state === "alarm";
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
  source.addEventListener("lenses", (e) => {
    for (const view of JSON.parse(e.data).lenses) {
      const panel = panels.find((candidate) => candidate.lens.lens_id === view.lens_id);
      if (panel) showLens(panel, internals.get(view.lens_id), view);
    }
  });
});
