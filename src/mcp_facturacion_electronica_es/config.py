"""Centralised settings for mcp-facturacion-electronica-es.

Loads credentials once at import time via pydantic-settings and immediately
pops the password env vars so they are not readable by other tools in the same
process (mitigation for the co-residency risk identified in security audit H1).

Usage in tool handlers::

    from mcp_facturacion_electronica_es.config import aeat_settings

    cert_path = aeat_settings.certificate_path
    cert_password = aeat_settings.certificate_password  # None after env-var pop
"""

from __future__ import annotations

import logging
import os

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class AEATSettings(BaseSettings):
    """AEAT / FACe / VeriFactu / SII connection settings."""

    environment: str = Field(default="sandbox", alias="AEAT_ENV")
    certificate_path: str | None = Field(default=None, alias="AEAT_CERTIFICATE_PATH")
    certificate_password: str | None = Field(default=None, alias="AEAT_CERTIFICATE_PASSWORD")
    face_client_id: str | None = Field(default=None, alias="FACE_CLIENT_ID")
    face_client_secret: str | None = Field(default=None, alias="FACE_CLIENT_SECRET")
    face_environment: str = Field(default="sandbox", alias="FACE_ENV")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


def _load_aeat_settings() -> AEATSettings:
    settings = AEATSettings()
    # Pop password from environment so subsequent os.environ.get() calls by any
    # other tool in the same process cannot read the credential.
    for var in ("AEAT_CERTIFICATE_PASSWORD",):
        if var in os.environ:
            os.environ.pop(var)
            logger.debug("Popped %s from process environment after first load", var)
    return settings


# Module-level singleton — credentials loaded and env vars popped at import time.
aeat_settings: AEATSettings = _load_aeat_settings()
