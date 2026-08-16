"""Tests for the Stage-2 regex classifier.

These don't pin exact scores (those will drift as you tune weights) — they pin
*directional* behavior: the SOC2/bank/clearance posts score high on check_risk,
the graphics/5G posts score high on fit, the WordPress posts score low.
"""

from __future__ import annotations

from job_finder.classify.regex_pass import classify


class TestCheckRisk:
    def test_clearance_posting_high_check_risk(self):
        text = "We require a Secret clearance and Reliability status. Canadian citizen required."
        r = classify("Backend Engineer", text)
        assert r.check_risk_score > 0.7

    def test_fintech_posting_medium_check_risk(self):
        text = "OSFI-regulated environment. SOC 2 compliance. Bondable position."
        r = classify("Software Engineer", text)
        assert r.check_risk_score > 0.4

    def test_vanilla_saas_posting_low_check_risk(self):
        text = "Build our web application using TypeScript and React. Collaborative team."
        r = classify("Frontend Engineer", text)
        assert r.check_risk_score < 0.2

    def test_open_source_startup_negative_tilt(self):
        text = "Seed-stage YC startup. We contribute upstream. No clearance required."
        r = classify("Founding Engineer", text)
        assert r.check_risk_score < 0.2


class TestFitScore:
    def test_graphics_posting_high_fit(self):
        text = (
            "Work on our real-time rendering pipeline. Experience with GLSL shaders, "
            "WebGPU, and Vulkan required. Nice to have: gaussian splatting, NeRF research."
        )
        r = classify("Graphics Engineer", text)
        assert r.fit_score > 0.6

    def test_5g_posting_high_fit(self):
        text = "Design 5G network functions. Experience with O-RAN, DPDK, and packet processing."
        r = classify("5G Software Engineer", text)
        assert r.fit_score > 0.6

    def test_wordpress_posting_low_fit(self):
        text = "Maintain our WordPress site. PHP developer experience required."
        r = classify("WordPress Developer", text)
        assert r.fit_score < 0.3

    def test_vanilla_web_modest_fit(self):
        text = "Build features in our TypeScript/React/Next.js stack."
        r = classify("Frontend Engineer", text)
        assert 0.15 < r.fit_score < 0.7  # some signal, not high


class TestRoleCategory:
    def test_detects_graphics(self):
        r = classify("Rendering Engineer", "Shader programming with Vulkan and rasterization.")
        assert r.role_category == "graphics"

    def test_detects_5g(self):
        r = classify("Network Engineer", "5G RAN engineer with O-RAN and LTE experience.")
        assert r.role_category == "5g_networking"

    def test_detects_games(self):
        r = classify("Gameplay Programmer", "Unreal Engine 5 gameplay programmer for AAA title.")
        assert r.role_category == "games"
