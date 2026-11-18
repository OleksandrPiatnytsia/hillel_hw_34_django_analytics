"""The version of the service, shown in the footer of every page.

Two parts:
- __version__: written by hand, MAJOR.MINOR.PATCH (semantic versioning),
  raised once per release, not per commit. 0.x while the stages of the
  homework are being built; 1.0.0 = the first full release (stage 6).
- the commit: comes by itself. Railway gives every deploy from GitHub the
  variable RAILWAY_GIT_COMMIT_SHA; elsewhere it can be set as APP_COMMIT.
  No variable (local Docker, runserver) -> no commit, only the version.
"""

import os

__version__ = "0.1.0"


def deployed_commit():
    """The full SHA of the deployed commit, or "" when it is unknown."""
    return os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("APP_COMMIT", "")
