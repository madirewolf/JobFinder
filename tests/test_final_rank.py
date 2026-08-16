"""Tests for the composite final_rank scorer.

Pins directional behaviour (QC bonus, freshness decay, salary tiers, check-risk
discount, target-geo penalty) rather than exact numerics, so we can tune
individual factors without breaking every test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from job_finder.ranking import FRESHNESS_HALF_LIFE_HOURS, RankInputs, final_rank


def _now() -> datetime:
    return datetime(2026, 4, 23, tzinfo=timezone.utc)


def _base(**overrides) -> RankInputs:
    kw = dict(
        fit_score=0.8,
        check_risk_score=0.0,
        first_seen=_now(),
        salary_min=100_000,
        salary_max=140_000,
        remote_type="hybrid",
        in_target_geography=True,
        hq_province="ON",
    )
    kw.update(overrides)
    return RankInputs(**kw)


class TestQCBonus:
    def test_qc_scores_higher_than_on(self):
        on = final_rank(_base(hq_province="ON"), now=_now())
        qc = final_rank(_base(hq_province="QC"), now=_now())
        assert qc > on
        # 1.08× — allow tiny float slack
        assert qc / on == pytest.approx(1.08, rel=1e-4)

    def test_case_insensitive(self):
        a = final_rank(_base(hq_province="qc"), now=_now())
        b = final_rank(_base(hq_province="QC"), now=_now())
        assert a == b


class TestCheckRiskDiscount:
    def test_high_risk_shrinks_rank(self):
        low = final_rank(_base(check_risk_score=0.0), now=_now())
        hi = final_rank(_base(check_risk_score=1.0), now=_now())
        # At risk=1.0 the multiplier is (1 - 0.6) = 0.4
        assert hi < low
        assert hi / low == pytest.approx(0.4, rel=1e-4)

    def test_mid_risk_is_mid(self):
        low = final_rank(_base(check_risk_score=0.0), now=_now())
        mid = final_rank(_base(check_risk_score=0.5), now=_now())
        assert mid < low
        assert mid / low == pytest.approx(0.7, rel=1e-4)


class TestFreshness:
    def test_older_post_ranks_lower(self):
        new = final_rank(_base(first_seen=_now()), now=_now())
        old_ts = _now() - timedelta(hours=FRESHNESS_HALF_LIFE_HOURS)
        old = final_rank(_base(first_seen=old_ts), now=_now())
        # Decay is exp(-t/τ) where τ = FRESHNESS_HALF_LIFE_HOURS.
        # At t=τ the factor is e^-1 ≈ 0.368 (not 0.5 — the constant is a time
        # constant, not a strict half-life despite the name).
        import math
        assert old / new == pytest.approx(math.exp(-1), rel=1e-2)

    def test_old_post_decays_below_half(self):
        new = final_rank(_base(first_seen=_now()), now=_now())
        old_ts = _now() - timedelta(hours=FRESHNESS_HALF_LIFE_HOURS)
        old = final_rank(_base(first_seen=old_ts), now=_now())
        assert old < new * 0.5

    def test_naive_datetime_treated_as_utc(self):
        # Shouldn't crash on a naive datetime (we assume UTC)
        naive = datetime(2026, 4, 23)
        r = final_rank(_base(first_seen=naive), now=_now())
        assert r >= 0.0


class TestSalaryTiers:
    def test_high_salary_beats_low(self):
        low = final_rank(_base(salary_min=75_000), now=_now())
        hi = final_rank(_base(salary_min=160_000), now=_now())
        assert hi > low

    def test_unknown_salary_is_neutral(self):
        unknown = final_rank(_base(salary_min=None, salary_max=None), now=_now())
        at_90k = final_rank(_base(salary_min=90_000, salary_max=None), now=_now())
        # Both hit the 1.0 salary factor
        assert unknown == pytest.approx(at_90k, rel=1e-4)


class TestGeography:
    def test_out_of_target_penalized(self):
        in_tgt = final_rank(_base(in_target_geography=True), now=_now())
        out = final_rank(_base(in_target_geography=False), now=_now())
        assert out < in_tgt
        # Location factor is 0.3 vs 1.0
        assert out / in_tgt == pytest.approx(0.3, rel=1e-4)


class TestRemoteFlex:
    def test_remote_beats_hybrid_beats_onsite(self):
        remote = final_rank(_base(remote_type="remote"), now=_now())
        hybrid = final_rank(_base(remote_type="hybrid"), now=_now())
        onsite = final_rank(_base(remote_type="onsite"), now=_now())
        unspec = final_rank(_base(remote_type="unspecified"), now=_now())
        assert remote > hybrid > onsite > unspec


class TestNonNegative:
    def test_zero_fit_produces_zero(self):
        r = final_rank(_base(fit_score=0.0), now=_now())
        assert r == 0.0

    def test_never_negative(self):
        r = final_rank(_base(check_risk_score=1.5), now=_now())  # absurd, shouldn't flip sign
        assert r >= 0.0
