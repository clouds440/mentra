"""The only production Cloudinary adapter. Provider URLs stay inside this module."""

import hashlib
import time
from contextlib import contextmanager
import httpx
import logging
import re
from app.core.exceptions import AppError


class _PrivateProviderRequest(logging.Filter):
    def filter(self, record):
        # httpx otherwise logs signed download URLs at INFO.
        if "api.cloudinary.com" in record.getMessage():
            record.msg = "Cloudinary file HTTP request"
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_PrivateProviderRequest())


def unavailable():
    return AppError(
        "FILES_UNAVAILABLE",
        "File storage is temporarily unavailable. Please retry.",
        503,
    )


class CloudinaryProvider:
    def __init__(self, settings):
        self.settings = settings
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", settings.app_env):
            raise ValueError("APP_ENV must be a simple file namespace name")
        self.namespace = f"{settings.files_namespace}/{settings.files_environment or settings.app_env}"
        from urllib.parse import urlsplit, unquote

        parsed = urlsplit(settings.cloudinary_url)
        self.valid_scheme = parsed.scheme == "cloudinary"
        self.options = dict(
            cloud_name=parsed.hostname or "",
            api_key=unquote(parsed.username or ""),
            api_secret=unquote(parsed.password or ""),
            secure=True,
        )
        self.environment = self.options["cloud_name"]
        self.client = httpx.Client(
            timeout=httpx.Timeout(settings.files_timeout_seconds, connect=10),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=settings.files_concurrency),
        )

    def _ready(self):
        if not self.valid_scheme or not all(
            self.options[k] for k in ("cloud_name", "api_key", "api_secret")
        ):
            raise unavailable()

    def _owned(self, row):
        if (
            not row["public_id"].startswith(self.namespace + "/")
            or row.get("environment", self.environment) != self.environment
        ):
            raise AppError(
                "FILES_NAMESPACE",
                "File storage namespace does not match this application.",
                503,
            )

    def ensure_folder(self):
        self._ready()
        import cloudinary.api

        try:
            cloudinary.api.create_folder(self.namespace, **self.options)
        except Exception:
            raise unavailable() from None

    def upload(self, path, row):
        self._ready()
        self._owned(row)
        import cloudinary.uploader

        try:
            return cloudinary.uploader.upload(
                str(path),
                **self.options,
                public_id=row["public_id"],
                resource_type=row["resource_type"],
                type="authenticated",
                overwrite=False,
                asset_folder=row["public_id"].rsplit("/", 1)[0],
                timeout=self.settings.files_timeout_seconds,
            )
        except Exception:
            raise unavailable() from None

    @contextmanager
    def stream(self, row, byte_range=None):
        self._ready()
        self._owned(row)
        import cloudinary.utils

        # private_download_url works for all three resource types. No transformation.
        url = cloudinary.utils.private_download_url(
            row["public_id"],
            None,
            **self.options,
            resource_type=row["resource_type"],
            type="authenticated",
            expires_at=int(time.time()) + 120,
        )
        try:
            headers = {"Accept-Encoding": "identity"}
            if byte_range:
                headers["Range"] = byte_range
            with self.client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    raise unavailable()
                yield response
        except AppError:
            raise
        except Exception:
            raise unavailable() from None

    def verify(self, row):
        digest, size = hashlib.sha256(), 0
        with self.stream(row) as response:
            for chunk in response.iter_bytes(256 * 1024):
                size += len(chunk)
                if size > row["size_bytes"]:
                    raise AppError(
                        "FILES_INTEGRITY", "Stored file verification failed.", 502
                    )
                digest.update(chunk)
        if size != row["size_bytes"] or digest.hexdigest() != row["sha256"]:
            raise AppError("FILES_INTEGRITY", "Stored file verification failed.", 502)

    def destroy(self, row):
        self._ready()
        self._owned(row)
        import cloudinary.uploader

        try:
            result = cloudinary.uploader.destroy(
                row["public_id"],
                **self.options,
                resource_type=row["resource_type"],
                type="authenticated",
                invalidate=True,
                timeout=self.settings.files_timeout_seconds,
            )
            if result.get("result") not in ("ok", "not found"):
                raise unavailable()
        except Exception:
            raise unavailable() from None

    def close(self):
        self.client.close()
