"""Read .env file"""
import os.path

import environ  # type: ignore

env = environ.Env(
    DEBUG=(bool, False),
    CI=(bool, False),
)

os.chdir('..')
if os.path.exists("nhl_web_app/.env"):
    environ.Env.read_env("nhl_web_app/.env")  # reading .env file

__all__ = [
    "env",
]