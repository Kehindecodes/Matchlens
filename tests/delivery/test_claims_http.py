"""P3: the rejected-claims page and its data exist only where the producer view does (Q43: 4B).

The page lists every claim with its verdict and six checks. It is a producer surface: with the
view off there is nothing to find, and a viewer's pages neither link to it nor carry its files.
"""

import re

import pytest
from fastapi.testclient import TestClient

from matchlens import lenses
from matchlens.audit import Audit
from matchlens.audit.claims import claims_page
from matchlens.control import Mutes
from matchlens.delivery.http import WEB_DIR, create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.producer import ProducerFeed
from matchlens.delivery.sessions import SessionStore
from matchlens.models import CheckStatus
from tests.audit.support import a_moment_with_a_wrong_claim, a_moment_with_claims, verify_all

CLAIMS_FILES = ("claims.html", "claims.js", "claims.css")


def _client(audit: Audit | None, view: bool = True) -> TestClient:
    feed = ProducerFeed(lenses.all_lenses(), Mutes()) if view else None
    return TestClient(create_app(MatchStateHub(), SessionStore(), producer=feed, audit=audit))


@pytest.fixture(scope="module")
def recorded(played) -> tuple[Audit, list]:
    """A goal with one claim of its own and a wrong one, and a later moment with its claims."""
    goal, claims = a_moment_with_a_wrong_claim(played)
    later = a_moment_with_claims(played, after=played.explained.index(goal) + 1)
    audit = Audit()
    audit.record(goal.moment, claims, verify_all(goal, claims), ())
    audit.record(later.moment, later.claims, verify_all(later), ())
    return audit, claims


# --- who can reach it ------------------------------------------------------------------------


def test_with_the_producer_view_off_the_claims_page_and_its_data_are_not_there():
    client = _client(Audit(), view=False)

    assert client.get("/producer/claims").status_code == 404
    assert client.get("/producer/claims/data").status_code == 404
    for name in CLAIMS_FILES:
        assert client.get(f"/static/{name}").status_code == 404, name
    assert client.get("/static/panel.js").status_code == 200  # a viewer's files are unaffected


def test_with_the_producer_view_on_the_page_and_its_files_are_served():
    client = _client(Audit())

    page = client.get("/producer/claims")

    assert page.status_code == 200 and "claims.js" in page.text
    for name in CLAIMS_FILES:
        assert client.get(f"/static/{name}").status_code == 200, name


def test_the_producer_page_links_to_it_and_no_viewer_page_does():
    assert "/producer/claims" in (WEB_DIR / "producer.html").read_text()
    viewer_pages = [
        path
        for path in WEB_DIR.iterdir()
        if path.suffix in {".html", ".js", ".css"}
        and path.name not in {"producer.html", "producer.js", "producer.css", *CLAIMS_FILES}
    ]
    assert viewer_pages
    for path in viewer_pages:
        assert "/producer/claims" not in path.read_text().lower(), path.name


# --- the data --------------------------------------------------------------------------------


def test_the_data_is_the_view_of_the_trail_word_for_word(recorded):
    audit, _ = recorded

    response = _client(audit).get("/producer/claims/data")

    assert response.status_code == 200
    assert response.json() == claims_page(audit).model_dump(mode="json")


def test_a_rejection_arrives_with_its_failed_check_and_the_reason_verbatim(recorded):
    audit, claims = recorded
    wrong = claims[-1]
    [verdict] = [
        found
        for entry in audit.trail()
        for found in entry.verifications
        if found.claim_id == wrong.claim_id
    ]

    body = _client(audit).get("/producer/claims/data").json()

    [row] = [
        row
        for moment in body["moments"]
        for row in moment["claims"]
        if row["claim_id"] == wrong.claim_id
    ]
    assert row["verdict"] == "fail"
    failed = {
        check["check"]: check["reason"] for check in row["checks"] if check["status"] == "failed"
    }
    assert failed == {
        name.value: result.reason
        for name, result in verdict.checks.items()
        if result.status is CheckStatus.FAILED
    }
    assert row["operands"][0]["claimed"] != row["operands"][0]["recomputed"]


def test_a_reader_asks_only_for_the_moments_after_the_ones_it_has(recorded):
    audit, _ = recorded
    client = _client(audit)

    everything = client.get("/producer/claims/data").json()
    rest = client.get("/producer/claims/data", params={"after": 1}).json()

    assert everything["recorded"] == rest["recorded"] == 2
    assert [moment["moment_id"] for moment in rest["moments"]] == [
        moment["moment_id"] for moment in everything["moments"][1:]
    ]
    assert rest["totals"] == everything["totals"]


def test_a_negative_cursor_is_refused(recorded):
    audit, _ = recorded

    assert _client(audit).get("/producer/claims/data", params={"after": -1}).status_code == 422


def test_before_any_moment_the_data_is_an_empty_page_not_an_error():
    body = _client(Audit()).get("/producer/claims/data").json()

    assert body == {"recorded": 0, "totals": {"claims": 0, "rejected": 0}, "moments": []}


# --- the page computes nothing -----------------------------------------------------------------


def test_the_script_only_displays_what_the_server_sent():
    script = (WEB_DIR / "claims.js").read_text()

    for arithmetic in ("Math.", "parseFloat", "Number(", "toFixed", ".reduce(", "Date.now"):
        assert arithmetic not in script, arithmetic
    # It never sets a claimed figure against a recomputed one: the page prints both side by side.
    assert not re.search(r"(claimed|recomputed)\s*[!=<>]=*", script)


def test_a_check_that_did_not_apply_is_drawn_differently_from_a_pass():
    script = (WEB_DIR / "claims.js").read_text()
    styles = (WEB_DIR / "claims.css").read_text()

    table = re.search(r"const MARKS = \{([^}]*)\}", script)
    assert table
    marks = dict(re.findall(r'(passed|failed|not_applicable):\s*"([^"]+)"', table.group(1)))
    assert set(marks) == {"passed", "failed", "not_applicable"}
    assert len(set(marks.values())) == 3  # three marks, so a pass can be told from the other two
    assert "✓" not in marks["not_applicable"]
    for status in ("passed", "failed", "not_applicable"):
        assert f".check.{status}" in styles, status
