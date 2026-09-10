"""
Tests for the Brandfetch client and its mapping onto the brand-config shape.

The point of this module is that colors, fonts and logos stop being a model's
reading of a stylesheet and become published data. So the tests that matter are
about the mapping being faithful and the failures being soft: every "we could
not get data" case must return None, because the caller's response to all of
them is the same — fall back to inference — and a raised exception there would
turn a thin brand config into a dead request.
"""

import httpx
import pytest

from src.server import brandfetch_api as bf


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("BRANDFETCH_API_KEY", "test-key")


STRIPE_LIKE = {
    "name": "Stripe",
    "domain": "stripe.com",
    "qualityScore": 1.0,
    "colors": [
        {"type": "accent", "hex": "#635BFF"},
        {"type": "dark", "hex": "#0A2540"},
        {"type": "light", "hex": "#FFFFFF"},
    ],
    "fonts": [
        {"type": "title", "name": "Sohne Var"},
        {"type": "body", "name": "Inter"},
    ],
    "logos": [
        {"type": "logo", "theme": "light", "formats": [
            {"format": "png", "src": "light.png"}, {"format": "svg", "src": "light.svg"}]},
        {"type": "logo", "theme": "dark", "formats": [{"format": "svg", "src": "dark.svg"}]},
        {"type": "icon", "theme": "dark", "formats": [{"format": "jpeg", "src": "icon.jpg"}]},
    ],
}


# --- domain parsing ------------------------------------------------------


@pytest.mark.parametrize("given,expected", [
    ("https://www.humain.vc/about?x=1", "humain.vc"),
    ("http://Example.COM/", "example.com"),
    ("stripe.com", "stripe.com"),
    ("https://sub.firm.co.uk/team", "sub.firm.co.uk"),
    ("", ""),
])
def test_domain_from_url(given, expected):
    assert bf.domain_from_url(given) == expected


def test_www_is_stripped():
    """Brandfetch 404s on a www. prefix, which reads as 'firm not indexed' —
    the wrong conclusion, drawn from a formatting detail."""
    assert bf.domain_from_url("https://www.stripe.com") == "stripe.com"


# --- shaping -------------------------------------------------------------


def test_shape_maps_colors_fonts_and_logos():
    out = bf.shape_for_brand_config(STRIPE_LIKE)
    assert out["company_name"] == "Stripe"
    assert out["accent_color"] == "#635BFF"
    assert out["primary_color"] == "#635BFF"
    assert out["text_dark"] == "#0A2540"
    assert out["background"] == "#FFFFFF"
    assert out["header_font_family"] == "Sohne Var"
    assert out["font_family"] == "Inter"
    assert out["logo_alt_text"] == "Stripe"


def test_svg_is_preferred_over_raster():
    """The logo lands in an HTML export and a PDF; SVG survives both."""
    out = bf.shape_for_brand_config(STRIPE_LIKE)
    assert out["logo_light_url"] == "light.svg"


def test_wordmark_preferred_over_icon():
    """The config slot is a header lockup, not a favicon."""
    payload = {"logos": [
        {"type": "icon", "theme": "light", "formats": [{"format": "svg", "src": "icon.svg"}]},
        {"type": "logo", "theme": "light", "formats": [{"format": "svg", "src": "word.svg"}]},
    ]}
    assert bf.shape_for_brand_config(payload)["logo_light_url"] == "word.svg"


def test_single_theme_logo_fills_both_slots():
    """One logo in both modes beats a missing header. Real case: humain.vc
    publishes only a dark-theme asset."""
    payload = {"logos": [
        {"type": "logo", "theme": "dark", "formats": [{"format": "png", "src": "only.png"}]},
    ]}
    out = bf.shape_for_brand_config(payload)
    assert out["logo_light_url"] == "only.png"
    assert out["logo_dark_url"] == "only.png"


def test_absent_fields_are_omitted_not_emptied():
    """The model is shown what is missing. Empty strings would read as answers."""
    out = bf.shape_for_brand_config({"name": "Firm"})
    assert set(out) == {"company_name", "logo_alt_text"}
    assert "tagline" not in out
    assert "primary_color" not in out


def test_malformed_hex_is_dropped():
    payload = {"colors": [{"type": "accent", "hex": "not-a-color"},
                          {"type": "dark", "hex": "0A2540"}]}
    out = bf.shape_for_brand_config(payload)
    assert "accent_color" not in out
    assert out["text_dark"] == "#0A2540", "a missing # is a format quirk, not bad data"


# --- failure modes are all soft ------------------------------------------


def _stub(monkeypatch, **kwargs):
    def fake_get(url, **_kw):
        if "exc" in kwargs:
            raise kwargs["exc"]
        return httpx.Response(kwargs.get("status", 200),
                              json=kwargs.get("json", STRIPE_LIKE),
                              request=httpx.Request("GET", url))
    monkeypatch.setattr(bf.httpx, "get", fake_get)


def test_missing_key_returns_none(monkeypatch):
    monkeypatch.delenv("BRANDFETCH_API_KEY", raising=False)
    assert bf.fetch_brand("stripe.com") is None
    assert bf.api_key_present() is False


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_error_statuses_return_none(monkeypatch, status):
    _stub(monkeypatch, status=status, json={})
    assert bf.fetch_brand("stripe.com") is None


def test_network_error_returns_none(monkeypatch):
    _stub(monkeypatch, exc=httpx.ConnectError("boom"))
    assert bf.fetch_brand("stripe.com") is None


def test_success_returns_payload(monkeypatch):
    _stub(monkeypatch)
    assert bf.fetch_brand("stripe.com")["name"] == "Stripe"


def test_blank_domain_short_circuits(monkeypatch):
    called = []
    monkeypatch.setattr(bf.httpx, "get", lambda *a, **k: called.append(1))
    assert bf.fetch_brand("") is None
    assert not called, "no request should be made for an unparseable URL"


def test_describe_payload_is_one_line():
    line = bf.describe_payload(STRIPE_LIKE)
    assert "\n" not in line
    assert "3 color(s)" in line and "3 logo(s)" in line


# --- upstream data is not automatically good data ------------------------


@pytest.mark.parametrize("junk", [
    "var(--font-body)",
    "VAR( --x )",
    "inherit",
    "initial",
    "unset",
    "none",
    "",
    "   ",
    None,
    123,
])
def test_css_keywords_and_var_refs_are_not_font_names(junk):
    """Brandfetch scrapes font-family without resolving custom properties.
    humain.vc really does come back as var(--font-display)."""
    payload = {"fonts": [{"type": "body", "name": junk}]}
    assert "font_family" not in bf.shape_for_brand_config(payload)


def test_a_font_stack_yields_its_first_family():
    payload = {"fonts": [{"type": "body", "name": "'Inter', Helvetica, sans-serif"}]}
    assert bf.shape_for_brand_config(payload)["font_family"] == "Inter"


def test_a_real_font_name_survives():
    payload = {"fonts": [{"type": "title", "name": "Sohne Var"}]}
    assert bf.shape_for_brand_config(payload)["header_font_family"] == "Sohne Var"


def test_rejected_font_leaves_the_key_absent_for_the_model():
    """Absent, not empty — the caller shows the model what is still missing."""
    payload = {"name": "Firm", "fonts": [{"type": "body", "name": "var(--x)"}]}
    out = bf.shape_for_brand_config(payload)
    assert "font_family" not in out
    assert out["company_name"] == "Firm"
