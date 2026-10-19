import pytest
from telegram_bot import get_session_id, build_telegram_app, USER_MODES

def test_telegram_session_id():
    assert get_session_id(12345) == "telegram_12345"
    assert get_session_id(999999999) == "telegram_999999999"

def test_telegram_app_builder():
    dummy_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"
    app = build_telegram_app(dummy_token)
    assert app is not None
    # Check that handlers are registered
    handlers = app.handlers[0]
    assert len(handlers) >= 5

def test_telegram_user_modes():
    USER_MODES[111] = "chat"
    USER_MODES[222] = "work"
    USER_MODES[333] = "auto"
    assert USER_MODES[111] == "chat"
    assert USER_MODES[222] == "work"
    assert USER_MODES[333] == "auto"
