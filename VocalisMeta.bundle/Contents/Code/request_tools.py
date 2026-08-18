# coding: utf-8
"""Pure helpers for classifying HTTP failures and calculating retry delays."""

from __future__ import unicode_literals

import time

try:
    from email.utils import parsedate_tz, mktime_tz
except ImportError:  # pragma: no cover
    parsedate_tz = None
    mktime_tz = None


TRANSIENT_STATUSES = set([408, 425, 429, 500, 502, 503, 504])


class RequestBudget(object):
    """Bound logical requests for one operation without counting retries."""

    def __init__(self, limit):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 8
        self.limit = max(1, min(50, limit))
        self.used = 0
        self.providers = {}

    def take(self, provider=''):
        if self.used >= self.limit:
            return False
        self.used = self.used + 1
        provider = str(provider or '')
        self.providers[provider] = self.providers.get(provider, 0) + 1
        return True

    @property
    def remaining(self):
        return max(0, self.limit - self.used)


def integer_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def error_response(error):
    try:
        return error.response
    except AttributeError:
        return None


def source_status(source, name):
    try:
        if name == 'status':
            return source.status
        if name == 'status_code':
            return source.status_code
        if name == 'code':
            return source.code
    except AttributeError:
        pass
    return None


def status_from_error(error):
    for source in (error, error_response(error)):
        if source is None:
            continue
        for name in ('status', 'status_code', 'code'):
            status = integer_value(source_status(source, name))
            if status is not None:
                return status
    return None


def headers_from_error(error):
    for source in (error_response(error), error):
        try:
            headers = source.headers if source is not None else None
        except AttributeError:
            headers = None
        if headers:
            return headers
    return {}


def header_value(headers, wanted):
    wanted = wanted.lower()
    try:
        direct = headers.get(wanted) or headers.get(wanted.title())
        if direct is not None:
            return direct
    except AttributeError:
        pass
    try:
        for key, value in headers.items():
            if str(key).lower() == wanted:
                return value
    except AttributeError:
        pass
    return None


def retry_after_seconds(error, now=None, maximum=30):
    value = header_value(headers_from_error(error), 'retry-after')
    if value is None:
        return None
    seconds = integer_value(value)
    if seconds is None and parsedate_tz and mktime_tz:
        try:
            target = mktime_tz(parsedate_tz(str(value)))
            seconds = int(round(target - (time.time() if now is None else now)))
        except (TypeError, ValueError, OverflowError):
            seconds = None
    if seconds is None:
        return None
    return max(0, min(int(maximum), seconds))


def should_retry(status):
    # A missing status normally means a DNS, TLS, connection, or timeout error.
    return status is None or status in TRANSIENT_STATUSES


def backoff_seconds(attempt, error=None, maximum=30):
    retry_after = retry_after_seconds(error, maximum=maximum) if error else None
    if retry_after is not None:
        return retry_after
    attempt = max(1, int(attempt))
    return min(int(maximum), 2 ** (attempt - 1))
