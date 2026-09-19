from dishka import Provider, Scope, provide

from gateway.platform.storage.object_storage import ObjectStorage
from gateway.platform.storage.s3_storage import S3ObjectStorage
from gateway.platform.storage.settings import StorageSettings


class StorageProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> StorageSettings:
        return StorageSettings()

    @provide
    def object_storage(self, settings: StorageSettings) -> ObjectStorage:
        return S3ObjectStorage(
            settings.bucket,
            endpoint_url=settings.endpoint_url,
            public_endpoint_url=settings.public_endpoint_url,
            access_key=settings.access_key,
            secret_key=(
                None
                if settings.secret_key is None
                else settings.secret_key.get_secret_value()
            ),
        )
