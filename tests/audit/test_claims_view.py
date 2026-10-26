"""P3: the rejected-claims view lists every claim with its verdict, and computes nothing.

Every verdict here is the real verifier's. A rejected claim is a real L7 claim with one number
changed, so the reasons on it are the ones A3 writes, not ones made up for the test.
"""

import json
import math

import pytest

from matchlens import verification
from matchlens.audit import Audit
from matchlens.audit.claims import ClaimsPage, claims_page
from matchlens.models import CheckName, CheckStatus, Verdict
from matchlens.verification import checks
from tests.audit.support import a_moment_with_a_wrong_claim, a_moment_with_claims, verify_all


def _audit_with(*moments_with_claims) -> Audit:
    audit = Audit()
    for explained, claims in moments_with_claims:
        audit.record(explained.moment, claims, verify_all(explained, claims), ())
    return audit


def _rows(page: ClaimsPage):
    return [row for moment in page.moments for row in moment.claims]


def _row(page: ClaimsPage, claim_id: str):
    return next(row for row in _rows(page) if row.claim_id == claim_id)


@pytest.fixture(scope="module")
def mixed(played):
    """One goal with its own claims and a wrong one added, the real verdicts, and the page."""
    goal, claims = a_moment_with_a_wrong_claim(played)
    return goal, claims, verify_all(goal, claims), claims_page(_audit_with((goal, claims)))


def test_accepted_and_rejected_claims_are_both_listed(mixed):
    goal, claims, _, page = mixed

    listed = {row.claim_id: row.verdict for row in _rows(page)}

    assert set(listed) == {claim.claim_id for claim in claims}
    assert listed[goal.claims[0].claim_id] is Verdict.PASS
    assert listed[claims[-1].claim_id] is Verdict.FAIL


def test_a_rejection_names_each_failed_check_and_carries_its_reason_verbatim(mixed):
    _, claims, recorded, page = mixed
    rejection = recorded[-1]

    row = _row(page, claims[-1].claim_id)

    shown = {
        check.check: check.reason for check in row.checks if check.status is CheckStatus.FAILED
    }
    kept = {
        name: result.reason
        for name, result in rejection.checks.items()
        if result.status is CheckStatus.FAILED
    }
    assert shown == kept and kept  # really rejected, so this is not comparing two empty dicts
    assert row.failure_reason == rejection.failure_reason


def test_every_claim_lists_all_six_checks_in_the_order_they_run(mixed):
    *_, page = mixed

    for row in _rows(page):
        assert [check.check for check in row.checks] == list(CheckName)


def test_a_check_that_did_not_apply_is_carried_as_such_and_never_as_passed(played):
    # Entity does not apply to a team subject, which is most of seed 1's claims.
    explained = next(
        found
        for found in played.explained
        if any(
            result.status is CheckStatus.NOT_APPLICABLE
            for verdict in verify_all(found)
            for result in verdict.checks.values()
        )
    )
    page = claims_page(_audit_with((explained, explained.claims)))

    shown = {
        (row.claim_id, check.check): check.status for row in _rows(page) for check in row.checks
    }
    kept = {
        (verdict.claim_id, name): result.status
        for verdict in verify_all(explained)
        for name, result in verdict.checks.items()
    }
    assert shown == kept
    assert CheckStatus.NOT_APPLICABLE in shown.values()


def test_a_value_failure_shows_what_was_claimed_beside_what_was_recomputed(mixed):
    _, claims, recorded, page = mixed
    [operand] = claims[-1].operands
    [recomputed] = recorded[-1].recomputed_value

    [shown] = _row(page, claims[-1].claim_id).operands

    assert shown.claimed == f"{operand.value:g}"
    assert shown.recomputed == f"{recomputed:g}"
    assert shown.claimed != shown.recomputed


@pytest.mark.parametrize("figures", [(math.nan,), ()], ids=["nan", "none"])
def test_an_operand_with_no_recomputed_figure_shows_none_and_never_a_number(played, figures):
    explained = next(
        found for found in played.explained if found.claims and len(found.claims[0].operands) == 1
    )
    claim = explained.claims[0]
    verdict = verify_all(explained, [claim])[0].model_copy(update={"recomputed_value": figures})
    audit = Audit()
    audit.record(explained.moment, [claim], [verdict], ())

    page = claims_page(audit)

    [row] = _rows(page)
    assert [operand.recomputed for operand in row.operands] == [None]
    json.dumps(page.model_dump(mode="json"), allow_nan=False)  # NaN cannot reach the browser


def test_the_view_cites_who_proposed_each_claim_and_who_checked_it(mixed):
    _, claims, recorded, page = mixed
    claim, verdict = claims[-1], recorded[-1]

    row = _row(page, claim.claim_id)

    assert row.said_by == f"{claim.model} {claim.model_version}"
    assert row.checked_by == f"{verdict.model} {verdict.model_version}"


def test_a_subject_is_named_when_the_match_introduced_it_and_cited_by_id_when_not(played):
    goal, claims = a_moment_with_a_wrong_claim(played)
    subject = claims[0].operands[0].subject.id
    named = _audit_with((goal, claims))
    named.introduce({subject: "Away Nine"})
    unnamed = _audit_with((goal, claims))

    assert _row(claims_page(named), claims[0].claim_id).operands[0].subject == "Away Nine"
    assert _row(claims_page(unnamed), claims[0].claim_id).operands[0].subject == subject


def test_windows_and_clocks_read_as_minutes_and_seconds(mixed):
    goal, claims, _, page = mixed

    [operand, *_] = _row(page, claims[0].claim_id).operands

    assert operand.window == "00:00–18:54"  # 0 to 1_134_535 ms
    assert page.moments[0].clock == "18:54"
    assert page.moments[0].moment_type == goal.moment.type.value


def test_a_match_where_nothing_was_rejected_shows_every_claim_and_every_check(played):
    first, second, *_ = (found for found in played.explained if found.claims)  # all pass
    page = claims_page(_audit_with((first, first.claims), (second, second.claims)))

    rows = _rows(page)
    assert page.totals.rejected == 0
    assert page.totals.claims == len(first.claims) + len(second.claims) > 0
    assert all(row.verdict is Verdict.PASS for row in rows)
    for row in rows:  # the checks ran: they are listed, not left out
        assert len(row.checks) == len(CheckName)
        assert all(check.status is not CheckStatus.FAILED for check in row.checks)


def test_the_totals_count_the_whole_trail_and_not_only_the_page(played):
    goal, claims = a_moment_with_a_wrong_claim(played)
    other = a_moment_with_claims(played, after=played.explained.index(goal) + 1)
    audit = _audit_with((goal, claims), (other, other.claims))

    page = claims_page(audit, after=1)

    assert [moment.moment_id for moment in page.moments] == [other.moment.moment_id]
    assert page.recorded == 2
    assert page.totals.claims == len(claims) + len(other.claims)
    assert page.totals.rejected == 1


def test_a_moment_with_no_claims_has_nothing_to_list_but_still_counts_as_recorded(played):
    explained = a_moment_with_claims(played)
    audit = Audit()
    audit.record(explained.moment, [], [], ())

    page = claims_page(audit)

    assert page.recorded == 1 and page.moments == [] and page.totals.claims == 0


def test_an_empty_trail_is_an_empty_page():
    page = claims_page(Audit())

    assert page.recorded == 0 and page.moments == []
    assert page.totals.claims == 0 and page.totals.rejected == 0


def test_the_view_recomputes_and_rechecks_nothing(played, monkeypatch):
    goal, claims = a_moment_with_a_wrong_claim(played)
    audit = _audit_with((goal, claims))

    def refuse(*_, **__):
        raise AssertionError("the view went back to the record")

    monkeypatch.setattr(verification, "verify", refuse)
    for name in ("recompute", "value_", "citation", "temporal", "entity", "entailment", "coverage"):
        monkeypatch.setattr(checks, name, refuse)

    page = claims_page(audit)

    assert page.totals.rejected == 1
