"""Read .env file"""

from pathlib import Path

import environ  # type: ignore

env = environ.Env(
    DEBUG=(bool, False),
    CI=(bool, False),
)

env_file = Path(__file__).resolve().parent.parent / ".env"
if env.bool("NHL_READ_ENV_FILE", default=True) and env_file.is_file():
    environ.Env.read_env(str(env_file))

__all__ = [
    "env",
]
