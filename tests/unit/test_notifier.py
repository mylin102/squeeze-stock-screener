import os
import pytest
from unittest.mock import MagicMock, patch
from squeeze.report.notifier import LineNotifier, EmailNotifier

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("LINE_USER_ID", "test_user")

def test_line_notifier_init_from_env(mock_env):
    notifier = LineNotifier()
    assert notifier.access_token == "test_token"
    assert notifier.user_id == "test_user"

def test_line_notifier_init_explicit():
    notifier = LineNotifier(access_token="explicit_token", user_id="explicit_user")
    assert notifier.access_token == "explicit_token"
    assert notifier.user_id == "explicit_user"

@patch('squeeze.report.notifier.MessagingApi')
@patch('squeeze.report.notifier.ApiClient')
@patch('squeeze.report.notifier.Configuration')
def test_send_summary_success(mock_config, mock_api_client, mock_messaging_api, mock_env):
    # Setup mocks
    mock_instance = mock_messaging_api.return_value
    
    notifier = LineNotifier()
    result = notifier.send_summary("Test message")
    
    assert result is True
    mock_messaging_api.assert_called_once()
    mock_instance.push_message.assert_called_once()

def test_send_summary_missing_config():
    with patch.dict(os.environ, {}, clear=True):
        notifier = LineNotifier()
        result = notifier.send_summary("Test message")
        assert result is False

def test_send_summary_empty_message(mock_env):
    notifier = LineNotifier()
    result = notifier.send_summary("")
    assert result is False

# COMMENT ADDED FOR MODIFICATION:
# Added unit tests for EmailNotifier to verify explicit/env initialization,
# parsing of recipient lists, and successful email sending with BCC privacy protection.

def test_email_notifier_init_explicit():
    notifier = EmailNotifier(
        smtp_server="smtp.test.com",
        smtp_port=465,
        username="user@test.com",
        password="password123",
        recipient="a@test.com, b@test.com"
    )
    assert notifier.smtp_server == "smtp.test.com"
    assert notifier.smtp_port == 465
    assert notifier.username == "user@test.com"
    assert notifier.password == "password123"
    assert notifier.recipient_str == "a@test.com, b@test.com"

def test_email_notifier_recipient_parsing(monkeypatch):
    monkeypatch.delenv("SMTP_RECIPIENT", raising=False)
    notifier = EmailNotifier(recipient="  a@test.com ,  b@test.com, , c@test.com  ")
    assert notifier._get_recipient_list() == ["a@test.com", "b@test.com", "c@test.com"]

    notifier_empty = EmailNotifier(recipient="")
    assert notifier_empty._get_recipient_list() == []

def test_email_notifier_send_missing_credentials_or_recipients(monkeypatch):
    monkeypatch.delenv("SMTP_RECIPIENT", raising=False)
    # Missing recipients
    notifier_no_rec = EmailNotifier(username="user", password="pwd", recipient="")
    assert notifier_no_rec.send_email("Subject", "Body") is False

    # Missing username
    notifier_no_user = EmailNotifier(username="", password="pwd", recipient="a@test.com")
    assert notifier_no_user.send_email("Subject", "Body") is False

@patch('smtplib.SMTP')
def test_email_notifier_send_success(mock_smtp_cls, monkeypatch):
    monkeypatch.delenv("SMTP_RECIPIENT", raising=False)
    mock_smtp_instance = MagicMock()
    mock_smtp_cls.return_value = mock_smtp_instance

    notifier = EmailNotifier(
        smtp_server="smtp.test.com",
        smtp_port=587,
        username="sender@test.com",
        password="secret_password",
        recipient="recipient1@test.com, recipient2@test.com"
    )

    # Call send_email
    result = notifier.send_email("Test Subject", "Test Body")

    assert result is True
    mock_smtp_cls.assert_called_once_with("smtp.test.com", 587)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("sender@test.com", "secret_password")
    
    # Verify sendmail envelope arguments:
    # First is sender, second is the exact list of recipients, third is the email content as a string
    mock_smtp_instance.sendmail.assert_called_once()
    call_args = mock_smtp_instance.sendmail.call_args[0]
    assert call_args[0] == "sender@test.com"
    assert call_args[1] == ["recipient1@test.com", "recipient2@test.com"]
    
    # Verify that the MIME message does not contain the visible recipients (it uses undisclosed-recipients:; for BCC)
    email_string = call_args[2]
    assert "To: undisclosed-recipients:;" in email_string
    assert "recipient1@test.com" not in email_string.split("To:")[1].split("Subject:")[0] # It should not be in the visible recipient area
    assert "Subject: Test Subject" in email_string
    mock_smtp_instance.quit.assert_called_once()
