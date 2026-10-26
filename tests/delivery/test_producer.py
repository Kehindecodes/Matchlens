"""P1: the producer view tells a lens that chose silence from a lens that failed (Q43).

Invariant 11 is what makes it buildable: a lens that deliberately says nothing has a suppressed
rendition and a reason, and a lens that is broken has none. The feed holds what the pipeline
reports; nothing here is recomputed.
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchlens import lenses
from matchlens.delivery import producer as producer_module
from matchlens.delivery.http import WEB_DIR, create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.producer import LensState, LensView, ProducerFeed
from matchlens.delivery.sessions import SessionStore
from matchlens.models import Lens, MomentType, Rendition, SuppressionReason
from matchlens.rendering import LensOutcome, MomentOutcome
from tests.delivery.test_http import LiveServer, _fields

MOMENT_CLOCK_MS = 51 * 60_000 + 9_000

PRODUCER_FILES = (
    "producer.html",
    "producer.js",
    "producer.css",
    "claims.html",
    "claims.js",
    "claims.css",
)


def _rendition(lens_id: str, reason: SuppressionReason | None = None) -> Rendition:
    suppressed = reason is not None
    return Rendition(
        rendition_id=f"m-1:{lens_id}", moment_id="m-1", lens_id=lens_id, language="en",
        headline=None if suppressed else "Larkfield score", body=None if suppressed else "1–0.",
        surviving_claim_ids=() if suppressed else ("c-1",),
        suppressed=suppressed, suppression_reason=reason,
        rendered_at=datetime.now(UTC), model="templates", model_version="test",
    )  # fmt: skip


def _outcome(
    lens: Lens, reason: SuppressionReason | None = None, importance: float = 0.31, shown: int = 0
) -> LensOutcome:
    return LensOutcome(
        lens_id=lens.lens_id, rendition=_rendition(lens.lens_id, reason),
        importance=importance, shown_in_window=shown,
    )  # fmt: skip


def _moment(
    outcomes: list[LensOutcome], failure: str | None = None, moment_id: str = "m-1"
) -> MomentOutcome:
    return MomentOutcome(
        moment_id=moment_id, clock_ms=MOMENT_CLOCK_MS, moment_type=MomentType.CHANCE,
        lens_ids=tuple(lens.lens_id for lens in lenses.all_lenses()),
        outcomes=tuple(outcomes), failure=failure,
    )  # fmt: skip


def _views(feed: ProducerFeed) -> dict[str, LensView]:
    return {view.lens_id: view for view in feed.snapshot().lenses}


@pytest.fixture
def rows() -> list[Lens]:
    return lenses.all_lenses()


@pytest.fixture
def feed(rows) -> ProducerFeed:
    return ProducerFeed(rows)


# --- the ticket's one real requirement: quiet and broken are not the same thing -----------------


def test_a_lens_that_chose_silence_and_a_lens_with_no_rendition_render_differently(feed, rows):
    quiet_lens, broken_lens, spoke_lens = rows
    feed.receive(
        _moment(
            [
                _outcome(quiet_lens, SuppressionReason.BELOW_THRESHOLD),
                _outcome(spoke_lens),
            ]  # no outcome for `broken_lens`: Rendering produced nothing at all
        )
    )
    views = _views(feed)
    quiet, broken = views[quiet_lens.lens_id], views[broken_lens.lens_id]

    assert quiet.state is LensState.QUIET
    assert broken.state is LensState.BROKEN
    assert quiet.headline == "Quiet by choice"
    assert broken.headline == "Broken"
    assert quiet.why != broken.why
    # The quiet lens says why, in words. The broken one says there is nothing to explain.
    assert "threshold" in quiet.why.lower()
    assert "no rendition" in broken.why.lower()
    assert "choice" not in broken.why.lower() and "choice" not in broken.headline.lower()
    assert views[spoke_lens.lens_id].state is LensState.SPOKE


def test_the_page_styles_a_quiet_lens_and_a_broken_one_differently():
    stylesheet = (WEB_DIR / "producer.css").read_text()

    def rule(state: LensState) -> str:
        found = re.search(rf"\.internals\.state-{state.value}\s*\{{([^}}]*)\}}", stylesheet)
        assert found, f"no rule for {state.value}"
        return found.group(1).strip()

    assert rule(LensState.QUIET) != rule(LensState.BROKEN)
    assert len({rule(state) for state in LensState}) == len(LensState)


def test_a_failed_moment_leaves_every_lens_broken_with_what_failed(feed, rows):
    feed.receive(_moment([], failure="RuntimeError: selection exploded"))
    for view in feed.snapshot().lenses:
        assert view.state is LensState.BROKEN
        assert "RuntimeError: selection exploded" in view.why


def test_a_lens_that_rendered_nothing_but_has_no_failure_to_name_is_still_broken(feed, rows):
    feed.receive(_moment([_outcome(rows[0])]))
    views = _views(feed)
    assert views[rows[1].lens_id].state is LensState.BROKEN
    assert views[rows[0].lens_id].state is LensState.SPOKE


# --- why a lens is quiet, in words ------------------------------------------------------------


# Which reasons are a lens's choice, which an alarm, and which a failure (DATA-MODEL's table).
_STATE_OF_REASON = {
    SuppressionReason.OUT_OF_SCOPE: LensState.QUIET,
    SuppressionReason.MUTED: LensState.QUIET,
    SuppressionReason.CLAIMS_FILTERED_OUT: LensState.QUIET,
    SuppressionReason.BELOW_THRESHOLD: LensState.QUIET,
    SuppressionReason.RATE_LIMITED: LensState.QUIET,
    SuppressionReason.VERIFICATION_FAILED: LensState.ALARM,
    SuppressionReason.DEGRADED: LensState.BROKEN,
}


def test_every_suppression_reason_has_a_state_and_words():
    # Adding a reason to the enum fails here until the producer view can say it.
    assert set(_STATE_OF_REASON) == set(SuppressionReason)
    assert set(producer_module.STATE_OF_REASON) == set(SuppressionReason)


@pytest.mark.parametrize("reason", list(SuppressionReason))
def test_a_suppressed_lens_shows_its_reason_in_words(feed, rows, reason):
    lens = rows[0]
    feed.receive(_moment([_outcome(lens, reason, importance=0.31, shown=lens.max_cards_per_10min)]))
    view = _views(feed)[lens.lens_id]
    assert view.state is _STATE_OF_REASON[reason]
    assert view.why and "_" not in view.why  # words, not the enum's name
    assert view.suppression_reason is reason


def test_a_degraded_lens_is_a_failure_and_never_reads_as_quiet_by_choice(feed, rows):
    # A5 stores a Rendering failure as a suppressed rendition, which is a record and not a gap,
    # but it is not a lens choosing silence.
    feed.receive(_moment([_outcome(rows[0], SuppressionReason.DEGRADED)]))
    view = _views(feed)[rows[0].lens_id]
    assert view.state is LensState.BROKEN
    assert "choice" not in view.headline.lower() and "choice" not in view.why.lower()


def test_a_verification_failure_is_an_alarm_apart_from_a_lens_that_chose_to_filter(feed, rows):
    feed.receive(
        _moment(
            [
                _outcome(rows[0], SuppressionReason.VERIFICATION_FAILED),
                _outcome(rows[1], SuppressionReason.CLAIMS_FILTERED_OUT),
            ]
        )
    )
    views = _views(feed)
    assert views[rows[0].lens_id].state is LensState.ALARM
    assert views[rows[1].lens_id].state is LensState.QUIET
    assert views[rows[0].lens_id].headline != views[rows[1].lens_id].headline


def test_below_threshold_says_the_importance_and_the_threshold_it_missed(feed, rows):
    lens = rows[0]
    feed.receive(_moment([_outcome(lens, SuppressionReason.BELOW_THRESHOLD, importance=0.31)]))
    view = _views(feed)[lens.lens_id]
    assert view.importance == 0.31 and view.threshold == lens.importance_threshold
    assert "0.31" in view.why and f"{lens.importance_threshold:.2f}" in view.why


def test_rate_limited_says_how_many_cards_it_had_shown_of_how_many_it_may(feed, rows):
    lens = rows[0]
    shown = lens.max_cards_per_10min
    feed.receive(_moment([_outcome(lens, SuppressionReason.RATE_LIMITED, shown=shown)]))
    view = _views(feed)[lens.lens_id]
    assert f"{shown} of {lens.max_cards_per_10min}" in view.why


def test_the_card_count_against_the_limit_and_the_clock_it_is_as_of_are_per_lens(feed, rows):
    feed.receive(_moment([_outcome(rows[0], shown=2), _outcome(rows[1], shown=5)]))
    views = _views(feed)
    assert views[rows[0].lens_id].shown_in_window == 2
    assert views[rows[1].lens_id].shown_in_window == 5
    assert views[rows[0].lens_id].max_cards_per_10min == rows[0].max_cards_per_10min
    assert views[rows[0].lens_id].as_of_clock == MOMENT_CLOCK_MS


def test_before_any_moment_every_lens_is_listening_not_broken(feed, rows):
    views = feed.snapshot().lenses
    assert [view.lens_id for view in views] == [lens.lens_id for lens in rows]
    assert {view.state for view in views} == {LensState.LISTENING}
    assert all(view.as_of_clock is None and view.importance is None for view in views)
    assert all(view.name for view in views)


def test_a_broken_lens_stays_flagged_until_it_next_renders(feed, rows):
    lens = rows[0]
    feed.receive(_moment([], failure="RuntimeError: boom"))
    assert _views(feed)[lens.lens_id].state is LensState.BROKEN
    feed.receive(_moment([_outcome(lens, SuppressionReason.BELOW_THRESHOLD)], moment_id="m-2"))
    assert _views(feed)[lens.lens_id].state is LensState.QUIET


def test_the_snapshot_serialises_with_its_state_as_a_word(feed, rows):
    feed.receive(_moment([_outcome(rows[0], SuppressionReason.BELOW_THRESHOLD)]))
    row = json.loads(feed.snapshot().model_dump_json())["lenses"][0]
    assert row["state"] == "quiet" and row["suppression_reason"] == "below_threshold"


def test_the_feed_wakes_a_follower_on_every_report(feed, rows):
    async def scenario():
        stream = feed.follow()
        first = await anext(stream)
        feed.receive(_moment([_outcome(rows[0])]))
        second = await asyncio.wait_for(anext(stream), 1)
        await stream.aclose()
        return first, second

    first, second = asyncio.run(scenario())
    assert {view.state for view in first.lenses} == {LensState.LISTENING}
    assert {view.lens_id: view.state for view in second.lenses}[rows[0].lens_id] is LensState.SPOKE


# --- the page, and who can reach it -----------------------------------------------------------


def _client(feed: ProducerFeed | None) -> TestClient:
    return TestClient(create_app(MatchStateHub(), SessionStore(), producer=feed))


def test_with_the_setting_off_the_producer_view_is_not_there():
    client = _client(None)
    assert client.get("/producer").status_code == 404
    assert client.get("/producer/stream").status_code == 404
    for name in PRODUCER_FILES:
        assert client.get(f"/static/{name}").status_code == 404, name
    assert client.get("/static/panel.js").status_code == 200  # the viewer's files are unaffected


def test_with_the_setting_on_the_page_and_its_files_are_served(feed):
    client = _client(feed)
    page = client.get("/producer")
    assert page.status_code == 200 and "producer.js" in page.text
    for name in PRODUCER_FILES:
        assert client.get(f"/static/{name}").status_code == 200, name


def test_the_producer_stream_sends_the_lenses_as_they_are(feed, rows):
    feed.receive(_moment([_outcome(rows[0], SuppressionReason.BELOW_THRESHOLD)]))
    with LiveServer(MatchStateHub(), producer=feed) as live:
        url = "/producer/stream"
        with live.client.stream("GET", url) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            block: list[str] = []
            for line in response.iter_lines():
                if line:
                    block.append(line)
                elif block:
                    break
    fields = _fields(block)
    assert fields["event"] == "lenses"
    states = {row["lens_id"]: row["state"] for row in json.loads(fields["data"])["lenses"]}
    assert states[rows[0].lens_id] == "quiet"


def _viewer_assets() -> list[Path]:
    hidden = set(PRODUCER_FILES)
    return [
        path
        for path in Path(WEB_DIR).iterdir()
        if path.suffix in {".html", ".js", ".css"} and path.name not in hidden
    ]


def test_none_of_it_leaks_onto_the_viewer_pages():
    assets = _viewer_assets()
    assert {path.name for path in assets} >= {"index.html", "watch.html", "delay.html", "panel.js"}
    for path in assets:
        text = path.read_text().lower()
        assert "producer" not in text, path.name
        assert "/producer" not in text, path.name


def test_the_producer_page_reuses_the_panel_and_the_ladder_rather_than_rebuilding_them():
    page = (WEB_DIR / "producer.html").read_text()
    script = (WEB_DIR / "producer.js").read_text()
    assert "/static/panel.js" in page and "/static/app.js" in page
    assert 'id="ladder"' in page  # A5's rung strip: shown by panel.js, on every rung
    assert "class Panel" not in script and "new Panel(" not in script
    assert "EventSource(" in script  # its own stream, for what the cards do not carry


def test_the_producer_page_computes_nothing():
    script = (WEB_DIR / "producer.js").read_text()
    # Everything on it arrives as a word or a number from the feed; it picks and displays.
    assert "suppression_reason ===" not in script
    assert "importance <" not in script and "importance >" not in script
    assert "Date.now" not in script
