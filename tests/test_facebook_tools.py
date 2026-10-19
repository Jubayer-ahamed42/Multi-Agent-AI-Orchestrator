import pytest
from unittest.mock import patch, MagicMock
from tools.facebook_tools import get_facebook_page_info, publish_facebook_page_post


def test_get_facebook_page_info_success():
    fake_response = MagicMock()
    fake_response.__enter__.return_value = fake_response
    fake_response.read.return_value = b'{"id": "1347013991822233", "name": "Be Smart With AI", "category": "Digital creator", "link": "https://facebook.com/1347013991822233", "phone": "+8801984787625"}'

    with patch("urllib.request.urlopen", return_value=fake_response):
        info = get_facebook_page_info(page_id="1347013991822233", access_token="fake_token")
        assert info["success"] is True
        assert info["name"] == "Be Smart With AI"
        assert info["page_id"] == "1347013991822233"
        assert info["phone"] == "+8801984787625"


def test_get_facebook_page_info_missing_credentials():
    with patch("tools.facebook_tools.FB_PAGE_ID", ""), \
         patch("tools.facebook_tools.FB_PAGE_ACCESS_TOKEN", ""), \
         patch.dict("os.environ", {"FB_PAGE_ID": "", "FB_PAGE_ACCESS_TOKEN": ""}):
        info = get_facebook_page_info()
        assert info["success"] is False
        assert "not configured" in info["error"]


def test_publish_facebook_page_post_success():
    fake_response = MagicMock()
    fake_response.__enter__.return_value = fake_response
    fake_response.read.return_value = b'{"id": "1347013991822233_123456789"}'

    with patch("urllib.request.urlopen", return_value=fake_response):
        res = publish_facebook_page_post("Test message", page_id="1347013991822233", access_token="fake_token")
        assert res["success"] is True
        assert res["post_id"] == "1347013991822233_123456789"
        assert "https://www.facebook.com/" in res["post_url"]


def test_publish_facebook_page_post_empty_message():
    res = publish_facebook_page_post("   ", page_id="1347013991822233", access_token="fake_token")
    assert res["success"] is False
    assert "empty" in res["error"]
