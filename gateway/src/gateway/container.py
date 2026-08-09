from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider

from gateway.features import FEATURES
from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure import CodexAgentRunner
from gateway.infrastructure import DatabaseProvider, DatabaseSettings
from llm import CodexModel, create_codex_model


class _AgentProvider(Provider):
    scope = Scope.APP

    def __init__(self, agent: AgentRunner | None = None) -> None:
        self._agent = agent
        super().__init__()

    @provide
    def agent(self, sessions: SessionRepository) -> AgentRunner:
        return self._agent or CodexAgentRunner(
            sessions,
            create_codex_model(CodexModel.TERRA),
        )


def create_container(
    agent: AgentRunner | None = None,
    database_settings: DatabaseSettings | None = None,
) -> AsyncContainer:
    feature_providers = (
        provider() for feature in FEATURES for provider in feature.providers
    )
    return make_async_container(
        _AgentProvider(agent),
        DatabaseProvider(database_settings),
        *feature_providers,
        FastapiProvider(),
    )
