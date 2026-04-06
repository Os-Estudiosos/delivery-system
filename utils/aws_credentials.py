from __future__ import annotations

import os
from pathlib import Path


def configure_local_aws_credentials() -> None:
    """Point boto3 at the repo-local AWS credentials file when it exists."""
    root_dir = Path(__file__).resolve().parents[1]
    credentials_file = root_dir / ".aws" / "credentials"
    config_file = root_dir / ".aws" / "config"

    if credentials_file.exists() and not os.environ.get("AWS_SHARED_CREDENTIALS_FILE"):
        os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(credentials_file)

    if config_file.exists() and not os.environ.get("AWS_CONFIG_FILE"):
        os.environ["AWS_CONFIG_FILE"] = str(config_file)