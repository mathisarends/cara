from fastapi_canon import Feature

from gateway.features.alarm.feature import feature as alarm_feature
from gateway.features.automation.feature import feature as automation_feature
from gateway.features.conversation.feature import feature as conversation_feature
from gateway.features.health.feature import feature as health_feature
from gateway.features.llm.feature import feature as llm_feature
from gateway.features.rooms.feature import feature as rooms_feature
from gateway.features.voice.feature import feature as voice_feature

FEATURES: tuple[Feature, ...] = (
    health_feature,
    alarm_feature,
    automation_feature,
    llm_feature,
    conversation_feature,
    rooms_feature,
    voice_feature,
)
