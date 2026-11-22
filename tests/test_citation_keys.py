"""The shared hex citation key (src/citation_keys.py).

Its contract is fixed in context-v/plans/Hex-Code-Citations-and-a-Repair-Tool.md,
because two branches write it and both must agree.
"""

import hashlib
import re
import string

from src.citation_keys import assign_keys, source_key

_BASE36 = string.digits + string.ascii_lowercase


def _expected(identity: str, length: int = 6) -> str:
    n = int(hashlib.sha256(identity.encode()).hexdigest(), 16)
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _BASE36[r] + out
    return out[:length]


def test_key_is_sha256_of_the_link_in_base_36():
    definition = "2025, Jan 08. [Survey](https://Example.org/Fixture/Survey/). Press."
    assert source_key(definition) == _expected("https://example.org/fixture/survey")
    assert re.fullmatch(r"[0-9a-z]{6}", source_key(definition))


def test_same_link_same_key_whatever_the_text():
    a = "2025, Jan 08. [Survey](https://example.org/a%20b/). Fixture Press."
    b = "2024, Dec 01. [Another title](https://EXAMPLE.org/A%20b). Someone else."
    assert source_key(a) == source_key(b)


def test_the_scheme_matches_in_any_case():
    assert source_key("[X](HTTPS://Example.com/x)") == source_key("[X](https://example.com/x)")
    assert source_key("[Y](File:///deal/deck.pdf)") == source_key("[Y](file:///deal/deck.pdf)")


def test_file_links_are_identities_too():
    a = "[Pro forma](file:///deal/inputs/cap%20table.xlsx). Company."
    assert source_key(a) == _expected("file:///deal/inputs/cap table.xlsx")


def test_without_a_link_the_text_less_its_date_is_the_identity():
    a = "2025, Jan 08. Partner   notes from the first meeting."
    b = "2026, Feb 11. partner notes from the first meeting."
    assert source_key(a) == source_key(b) == _expected("partner notes from the first meeting.")


def test_assign_keys_maps_each_old_key_to_its_source_key():
    defs = {
        "1": "[One](https://a.example)",
        "2": "[Two](https://b.example)",
        "3": "[One again](https://a.example/)",
    }
    keys = assign_keys(defs)
    assert keys["1"] == keys["3"] == source_key(defs["1"])
    assert keys["2"] == source_key(defs["2"])


def test_two_identities_with_the_same_six_characters_both_get_eight():
    # Find two identities whose six-character keys collide.
    seen: dict[str, str] = {}
    pair = None
    i = 0
    while pair is None:
        url = f"https://collide.example/{i}"
        k = _expected(url.lower())
        if k in seen:
            pair = (seen[k], url)
        seen[k] = url
        i += 1
    keys = assign_keys({"a": f"[A]({pair[0]})", "b": f"[B]({pair[1]})"})
    assert keys["a"] == _expected(pair[0], 8)
    assert keys["b"] == _expected(pair[1], 8)
    assert keys["a"] != keys["b"]
