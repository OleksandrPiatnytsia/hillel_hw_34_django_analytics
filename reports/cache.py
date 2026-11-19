"""The cache of the report answers (Redis), dropped after every recalculation.

A report answer depends on its parameters (report, period, sort...), so
there are many keys, and after a recalculation ALL of them are out of date.
Redis can't delete keys by a pattern cheaply, so every key carries a
version number instead:

    reports:version = 7
    key of an answer = "report:7:<report>:<parameters>"

    recalculation -> reports:version = 8 -> every new key is "report:8:...",
    the old "report:7:..." keys are never read again and expire by timeout.

Used by the report pages and the REST API (stage 4.2, 4.4).
"""

import hashlib
import json

from django.core.cache import cache

VERSION_KEY = "reports:version"
# An answer is kept at most this long even without a recalculation
TIMEOUT = 60 * 60


def current_version():
    # add() writes only when the key is missing (a new or flushed Redis)
    cache.add(VERSION_KEY, 1, timeout=None)
    return cache.get(VERSION_KEY, 1)


def invalidate_reports():
    """Every cached report answer becomes out of date at once."""
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        # The key is missing: nothing was cached under it anyway
        cache.add(VERSION_KEY, 1, timeout=None)


def answer_key(report, params):
    """A short key of one answer: the parameters are hashed, sorted by name."""
    text = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(text.encode()).hexdigest()[:32]
    return f"report:{current_version()}:{report}:{digest}"


def cached_answer(report, params, compute):
    """The answer from the cache, or compute() it and keep it."""
    key = answer_key(report, params)
    answer = cache.get(key)
    if answer is None:
        answer = compute()
        cache.set(key, answer, TIMEOUT)
    return answer
