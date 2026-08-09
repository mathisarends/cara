from functools import partial

from agenttoolkit import Skills
from config import load_cara_config
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider

from agent.tools import build_tools
from gateway.features import FEATURES
from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure import RuntimeAgentRunner
from gateway.infrastructure import DatabaseProvider
from llm import CodexModel, create_codex_model


class _AgentProvider(Provider):
    scope = Scope.APP

    @provide
    def agent(self, sessions: SessionRepository) -> AgentRunner:
        configuration = load_cara_config()
        skills = Skills.from_dir(configuration.workspace_root / "skills")
        return RuntimeAgentRunner(
            sessions=sessions,
            llm=create_codex_model(CodexModel.TERRA),
            tool_factory=partial(
                build_tools,
                configuration=configuration,
                skills=skills,
            ),
            prompt_root=configuration.workspace_root,
            skills=skills,
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
