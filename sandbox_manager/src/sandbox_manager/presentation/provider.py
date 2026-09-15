from dishka import Provider, Scope, provide

from sandbox_manager.presentation.authentication import AuthSettings


class AuthenticationProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> AuthSettings:
        return AuthSettings()
