"""Tests for src/utils/config.py — _require and _optional helpers."""

import os
import pytest
from unittest.mock import patch


def test_require_raises_on_missing_key():
    from src.utils.config import _require
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError, match="MISSING_KEY"):
            _require("MISSING_KEY")


def test_require_raises_on_empty_string():
    from src.utils.config import _require
    with patch.dict(os.environ, {"MY_KEY": ""}):
        with pytest.raises(EnvironmentError, match="MY_KEY"):
            _require("MY_KEY")


def test_require_raises_on_whitespace_only_value():
    """A value of spaces only is effectively missing and should be rejected."""
    from src.utils.config import _require
    with patch.dict(os.environ, {"MY_KEY": "   "}):
        with pytest.raises(EnvironmentError, match="MY_KEY"):
            _require("MY_KEY")


def test_require_strips_and_returns_value():
    from src.utils.config import _require
    with patch.dict(os.environ, {"MY_KEY": "  actual-value  "}):
        result = _require("MY_KEY")
    assert result == "actual-value"


def test_require_returns_value_without_whitespace():
    from src.utils.config import _require
    with patch.dict(os.environ, {"MY_KEY": "plain-value"}):
        assert _require("MY_KEY") == "plain-value"


def test_optional_returns_default_when_missing():
    from src.utils.config import _optional
    with patch.dict(os.environ, {}, clear=True):
        assert _optional("NONEXISTENT_KEY", "fallback") == "fallback"


def test_optional_returns_empty_string_by_default():
    from src.utils.config import _optional
    with patch.dict(os.environ, {}, clear=True):
        assert _optional("NONEXISTENT_KEY") == ""


def test_optional_returns_set_value():
    from src.utils.config import _optional
    with patch.dict(os.environ, {"MY_KEY": "hello"}):
        assert _optional("MY_KEY") == "hello"
