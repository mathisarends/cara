from uuid import uuid4

import pytest
from pydantic import ValidationError

from gateway.features.automation.domain import (
    AutomationEnvelope,
    ReminderPayload,
    SessionAutomationTarget,
)
from gateway.features.automation.infrastructure import AutomationEnvelopeCodec


def test_automation_payload_codec_round_trips_versioned_reminder() -> None:
    codec = AutomationEnvelopeCodec()
    envelope = AutomationEnvelope(
        schema_version=1,
        target=SessionAutomationTarget(kind="session", session_id=uuid4()),
        payload=ReminderPayload(
            kind="reminder",
            message="Hang up the laundry",
            created_from_turn_id=uuid4(),
        ),
    )

    assert codec.decode(codec.encode(envelope)) == envelope


def test_automation_payload_codec_rejects_unknown_schema_version() -> None:
    codec = AutomationEnvelopeCodec()

    with pytest.raises(ValidationError):
        codec.decode(
            '{"schema_version":2,'
            '"target":{"kind":"session",'
            '"session_id":"00000000-0000-0000-0000-000000000001"},'
            '"payload":{"kind":"reminder","message":"test",'
            '"created_from_turn_id":"00000000-0000-0000-0000-000000000002"}}'
        )
