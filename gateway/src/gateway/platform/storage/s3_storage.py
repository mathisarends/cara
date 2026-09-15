from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from obstore.store import S3Store

from gateway.platform.storage.obstore_storage import ObstoreObjectStorage

if TYPE_CHECKING:
    from obstore.store import ClientConfig, S3Config


class S3ObjectStorage(ObstoreObjectStorage):
    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None,
        public_endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
    ) -> None:
        store = _create_store(bucket, endpoint_url, access_key, secret_key)
        signing_store = store
        if public_endpoint_url and public_endpoint_url != endpoint_url:
            signing_store = _create_store(
                bucket,
                public_endpoint_url,
                access_key,
                secret_key,
            )
        super().__init__(store, signing_store=signing_store)


def _create_store(
    bucket: str,
    endpoint_url: str | None,
    access_key: str | None,
    secret_key: str | None,
) -> S3Store:
    config: S3Config = {}
    if endpoint_url:
        config.update(
            endpoint=endpoint_url,
            virtual_hosted_style_request=False,
        )
    if access_key:
        config["access_key_id"] = access_key
    if secret_key:
        config["secret_access_key"] = secret_key

    client_options: ClientConfig | None = None
    if endpoint_url and urlsplit(endpoint_url).scheme == "http":
        client_options = {"allow_http": True}

    return S3Store(
        bucket,
        config=config or None,
        client_options=client_options,
    )
