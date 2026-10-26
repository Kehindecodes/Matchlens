// The rejected-claims page (P3): every claim of the match with its verdict and its six checks.
// It displays what the server sent and works out nothing. Every figure is one A3 stored and every
// reason is A3's own words, so the page cannot agree with itself while the pipeline is wrong.

const DATA_URL = "/producer/claims/data";
const POLL_MS = 2000;
// Three states, three marks. A check that did not apply is not a pass, so it never gets a tick.
const MARKS = { passed: "✓", failed: "✕", not_applicable: "–" };
const STATUS_WORDS = { passed: "passed", failed: "failed", not_applicable: "not applicable" };
const VERDICT_WORDS = { pass: "Accepted", fail: "Rejected" };

const moments = document.getElementById("moments");
const summary = document.getElementById("summary");
const feedStatus = document.getElementById("feed-status");
const onlyRejected = document.getElementById("only-rejected");

// How many moments the page has, which is the cursor it asks the server from.
let recorded = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// What was claimed beside what A3 recomputed from the record, for one operand. Both are printed
// as they came; nothing here compares them. The class says only how A3 judged the `value` check.
function operandLine(operand, valueStatus) {
  const line = element("p", "operand");
  line.append(element("span", "subject", operand.subject), element("span", "what", `${operand.metric} · ${operand.window}`));
  const figures = element("span", `figures value-${valueStatus}`);
  figures.append(
    element("span", "claimed", `Claimed ${operand.claimed}`),
    element("span", "recomputed", `Recomputed ${operand.recomputed ?? "not possible"}`),
  );
  line.append(figures);
  return line;
}

function checkList(checks) {
  const list = element("ul", "checks");
  for (const check of checks) {
    const item = element("li", `check ${check.status}`);
    const mark = element("span", "mark", MARKS[check.status]);
    mark.setAttribute("aria-hidden", "true");
    item.append(mark, element("span", "name", check.check), element("span", "status", STATUS_WORDS[check.status]));
    if (check.reason) item.append(element("span", "reason", check.reason));
    list.append(item);
  }
  return list;
}

function claimCard(claim) {
  const card = element("article", `claim ${claim.verdict}`);
  const head = element("div", "claim-head");
  head.append(
    element("span", "verdict", VERDICT_WORDS[claim.verdict]),
    element("span", "type", claim.claim_type),
    element("code", "id", claim.claim_id),
  );
  card.append(head);
  const valueCheck = claim.checks.find((check) => check.check === "value");
  for (const operand of claim.operands) card.append(operandLine(operand, valueCheck.status));
  card.append(checkList(claim.checks));
  card.append(element("p", "provenance", `Proposed by ${claim.said_by} · checked by ${claim.checked_by}`));
  return card;
}

function momentSection(moment) {
  const section = element("section", "moment");
  section.append(element("h2", "", `${moment.clock} · ${moment.moment_type}`));
  for (const claim of moment.claims) section.append(claimCard(claim));
  return section;
}

// The totals are the server's count over the whole match. A match with nothing rejected says so
// and says the checks still ran, so a clean page is not mistaken for an unchecked one.
function summarise(totals) {
  if (!totals.claims) {
    summary.textContent = "No claims yet.";
  } else if (!totals.rejected) {
    summary.textContent = `${totals.claims} claims, each put through all six checks. None was rejected.`;
  } else {
    summary.textContent = `${totals.claims} claims, each put through all six checks. ${totals.rejected} rejected.`;
  }
}

async function refresh() {
  try {
    const response = await fetch(`${DATA_URL}?after=${recorded}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const page = await response.json();
    if (page.recorded < recorded) {
      // The server started the match over, so what is on the page belongs to the last one.
      moments.replaceChildren();
      recorded = 0;
      return refresh();
    }
    recorded = page.recorded;
    for (const moment of page.moments) moments.prepend(momentSection(moment)); // newest first
    summarise(page.totals);
    feedStatus.textContent = "claims feed: live";
    feedStatus.classList.add("live");
  } catch (error) {
    feedStatus.textContent = "claims feed: not reachable, retrying…";
    feedStatus.classList.remove("live");
  }
}

onlyRejected.addEventListener("change", () => {
  moments.classList.toggle("only-rejected", onlyRejected.checked);
});

refresh();
setInterval(refresh, POLL_MS);
