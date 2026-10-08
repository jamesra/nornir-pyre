"""Pin ``is_headless`` exported by the nornir-pyre root ``conftest.py`` (no PyQt import)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

_CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"

_TRUTHY_FLAGS = ("1", "true", "yes", "on")
_FLAG_WORDS = _TRUTHY_FLAGS + ("0", "false", "no", "off", "", "2", "y", "t", "enabled")

# os.environ rejects NUL and lone surrogates.
_ENV_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"))


def _load_root_conftest():
    """Load ``conftest.py`` by path; pytest registers it under a name tests cannot import reliably."""
    spec = importlib.util.spec_from_file_location("_pyre_root_conftest", _CONFTEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_conftest = _load_root_conftest()


@st.composite
def _flag_values(draw) -> str | None:
    """``NORNIR_HEADLESS`` values: known words with case/whitespace noise, arbitrary text, or unset."""
    kind = draw(st.sampled_from(("word", "text", "unset")))
    if kind == "unset":
        return None
    if kind == "text":
        return draw(_ENV_TEXT)
    word = draw(st.sampled_from(_FLAG_WORDS))
    if draw(st.booleans()):
        word = word.upper()
    return draw(st.sampled_from(("", " ", "\t"))) + word + draw(st.sampled_from(("", " ", "\n")))


_DISPLAY_VALUES = st.one_of(st.none(), st.just(""), st.just(":0"), _ENV_TEXT.filter(bool))
_PLATFORMS = st.sampled_from(("win32", "linux", "darwin", "cygwin"))


def _expected(flag: str | None, display: str | None, platform: str) -> bool:
    if flag is not None and flag.strip().lower() in _TRUTHY_FLAGS:
        return True
    return platform != "win32" and not display


@given(flag=_flag_values(), display=_DISPLAY_VALUES, platform=_PLATFORMS)
@example(flag=" TRUE ", display=":0", platform="win32")
@example(flag="0", display=None, platform="linux")
@example(flag="off", display="", platform="linux")
@example(flag="0", display=":0", platform="linux")
@example(flag=None, display=None, platform="win32")
def test_is_headless_matches_env_and_display_rules(flag: str | None, display: str | None, platform: str) -> None:
    """Truthy ``NORNIR_HEADLESS`` wins; otherwise headless means non-Windows without a ``DISPLAY``."""
    with pytest.MonkeyPatch.context() as mp:
        for name, value in (("NORNIR_HEADLESS", flag), ("DISPLAY", display)):
            if value is None:
                mp.delenv(name, raising=False)
            else:
                mp.setenv(name, value)
        mp.setattr(sys, "platform", platform)
        assert _conftest.is_headless() is _expected(flag, display, platform)
    assert "is_headless" in _conftest.__all__
