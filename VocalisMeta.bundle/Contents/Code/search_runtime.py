# coding: utf-8
"""Per-thread operation budgets and process-local provider outage backoff."""
from __future__ import unicode_literals
import time
import threading
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

CONTEXT = threading.local()
FAILURES = {}
LOCK = threading.RLock()


class SearchWindow(object):
    def __init__(self, requests=24, seconds=90, clock=None):
        self.clock = clock or time.time
        self.deadline = self.clock() + seconds
        self.limit = requests
        self.used = 0
        self.exhausted = False

    def allowance(self, timeout):
        remaining = self.deadline - self.clock()
        if self.used >= self.limit or remaining < 1:
            self.exhausted = True
            return None
        self.used = self.used + 1
        return min(timeout, remaining)


def window():
    try:
        return CONTEXT.window
    except AttributeError:
        return None


def sidecar():
    try:
        return CONTEXT.sidecar
    except AttributeError:
        return {}


def provider(url):
    return (urlparse(url).hostname or '').lower()


def allowance(url, timeout):
    with LOCK:
        state = FAILURES.get(provider(url))
        if state and state[1] > time.time():
            return None, 'provider_cooldown'
    active = window()
    if active:
        timeout = active.allowance(timeout)
        if timeout is None:
            return None, 'search_budget_exhausted'
    return timeout, ''


def response(url, ok, transient=True):
    key = provider(url)
    with LOCK:
        if ok or not transient:
            FAILURES.pop(key, None)
        else:
            count, until = FAILURES.get(key, (0, 0))
            count = count + 1
            FAILURES[key] = (count, time.time() + 60 if count >= 3 else 0)


def pause(seconds):
    active = window()
    if active:
        seconds = min(seconds, max(0, active.deadline - active.clock()))
    if seconds:
        time.sleep(seconds)


def preview():
    try:
        return CONTEXT.preview
    except AttributeError:
        return False


def artwork_candidates():
    try:
        return CONTEXT.artwork_candidates
    except AttributeError:
        return None
