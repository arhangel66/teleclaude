from unittest.mock import MagicMock

from src.bot.handlers import _extract_metadata


def _bare_message() -> MagicMock:
    """MagicMock with all metadata fields explicitly None."""
    msg = MagicMock()
    msg.forward_origin = None
    msg.location = None
    msg.venue = None
    msg.contact = None
    msg.poll = None
    msg.dice = None
    msg.reply_to_message = None
    return msg


def test_extract_metadata_empty_for_plain_text() -> None:
    # Arrange
    message = _bare_message()

    # Act
    meta = _extract_metadata(message)

    # Assert
    assert meta == {}


def test_extract_metadata_forward_origin() -> None:
    # Arrange
    message = _bare_message()
    forward = MagicMock()
    forward.model_dump.return_value = {"type": "channel", "chat": {"id": -100, "title": "X"}}
    message.forward_origin = forward

    # Act
    meta = _extract_metadata(message)

    # Assert
    assert meta["forward_origin"]["type"] == "channel"
    forward.model_dump.assert_called_once_with(exclude_none=True, mode="json")


def test_extract_metadata_location() -> None:
    # Arrange
    message = _bare_message()
    loc = MagicMock()
    loc.model_dump.return_value = {"latitude": 55.75, "longitude": 37.62}
    message.location = loc

    # Act
    meta = _extract_metadata(message)

    # Assert
    assert meta["location"] == {"latitude": 55.75, "longitude": 37.62}


def test_extract_metadata_contact_and_venue() -> None:
    # Arrange
    message = _bare_message()
    contact = MagicMock()
    contact.model_dump.return_value = {"phone_number": "+1", "first_name": "Bob"}
    venue = MagicMock()
    venue.model_dump.return_value = {"title": "Cafe", "address": "Main St"}
    message.contact = contact
    message.venue = venue

    # Act
    meta = _extract_metadata(message)

    # Assert
    assert meta["contact"]["first_name"] == "Bob"
    assert meta["venue"]["title"] == "Cafe"


def test_extract_metadata_reply_to_condensed() -> None:
    # Arrange
    message = _bare_message()
    reply = MagicMock()
    reply.message_id = 777
    reply.text = "Previous message"
    reply.caption = None
    reply.from_user.username = "alice"
    message.reply_to_message = reply

    # Act
    meta = _extract_metadata(message)

    # Assert
    assert meta["reply_to"] == {
        "message_id": 777,
        "from": "alice",
        "text": "Previous message",
    }


def test_extract_metadata_reply_truncates_long_text() -> None:
    # Arrange
    message = _bare_message()
    reply = MagicMock()
    reply.message_id = 1
    reply.text = "x" * 1000
    reply.caption = None
    reply.from_user.username = "u"
    message.reply_to_message = reply

    # Act
    meta = _extract_metadata(message)

    # Assert
    assert len(meta["reply_to"]["text"]) == 500
