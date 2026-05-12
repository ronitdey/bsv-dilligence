"""Async collectors. Each returns a Result[T] — never raises."""

from .github import collect_github
from .hackernews import collect_hn
from .packages import collect_packages
from .web import collect_web

__all__ = ["collect_github", "collect_hn", "collect_packages", "collect_web"]
