from fastapi_canon import Feature

from sandbox_manager.presentation import AuthenticationProvider

platform_feature = Feature(name="platform", providers=[AuthenticationProvider])
