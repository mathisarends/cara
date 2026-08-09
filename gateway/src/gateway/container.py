from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider

from cara.tools import build_tools
from gateway.features import FEATURES
from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure import CodexAgentRunner
from gateway.infrastructure import DatabaseProvider
from llm import CodexModel, create_codex_model


class _AgentProvider(Provider):
    scope = Scope.APP

    @provide
    def agent(self, sessions: SessionRepository) -> AgentRunner:
        return CodexAgentRunner(
            sessions=sessions,
            llm=create_codex_model(CodexModel.TERRA),
            tool_factory=build_tools,
        )


def create_container() -> AsyncContainer:
    feature_providers = (
        provider() for feature in FEATURES for provider in feature.providers
    )
    return make_async_container(
        _AgentProvider(),
        DatabaseProvider(),
        *feature_providers,
        FastapiProvider(),
    )
