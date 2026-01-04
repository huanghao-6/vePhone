from pathlib import Path
import json
import logging
import os
import time
from datetime import datetime, timezone

from .case_runner import RunnerConfig, run_suite
from .env_utils import env_bool, load_env_from_root
from .system_prompt import SYSTEM_PROMPT
from .app_runner import run_cli



def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()