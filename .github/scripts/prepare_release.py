"""Inject the tag version and repository into config.py before freezing."""
import os
import re
from pathlib import Path

version = os.environ.get("GITHUB_REF_NAME", "").removeprefix("v")
repository = os.environ.get("GITHUB_REPOSITORY", "")
if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
    raise SystemExit(f"Release tag must look like v1.2.3; received {version!r}")
if not re.fullmatch(r"[^/]+/[^/]+", repository):
    raise SystemExit(f"Invalid GitHub repository: {repository!r}")

config_path = Path("config.py")
source = config_path.read_text(encoding="utf-8")
source, version_count = re.subn(
    r"(?m)^APP_VERSION\s*=.*$", f'APP_VERSION = "{version}"', source, count=1
)
source, repository_count = re.subn(
    r"(?m)^GITHUB_REPO\s*=.*$", f'GITHUB_REPO = "{repository}"', source, count=1
)
if version_count != 1 or repository_count != 1:
    raise SystemExit("Could not update APP_VERSION and GITHUB_REPO in config.py")
config_path.write_text(source, encoding="utf-8")
print(f"Building MedyaMate v{version} for {repository}")
