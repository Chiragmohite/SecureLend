"""Shared fixtures + IP-unblock retry helper for pytest-xdist runs.

The brute-force test intentionally blocks the shared egress IP, which cascades
into other tests running concurrently on the second xdist worker. We patch
requests.Session to auto-recover by unblocking IPs via direct Mongo access
if a 403 (blocked IP) is encountered.
"""
import os
import time
import pytest
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient
import requests as _requests

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_mongo = MongoClient(os.environ["MONGO_URL"])
_db = _mongo[os.environ["DB_NAME"]]


def _unblock_all_ips():
    _db.blocked_ips.update_many(
        {"unblocked_at": None},
        {"$set": {"unblocked_at": datetime.now(timezone.utc).isoformat()}},
    )


@pytest.fixture(autouse=True)
def _reset_blocked_ips():
    """Before each test, unblock all IPs. Also retry the test's setup once if blocked."""
    _unblock_all_ips()
    yield


# Monkey-patch requests to retry on 403 "blocked" once with mongo unblock
_orig_request = _requests.Session.request
_orig_top_request = _requests.request


def _resilient_request(self, method, url, **kwargs):
    for attempt in range(3):
        resp = _orig_request(self, method, url, **kwargs)
        if resp.status_code == 403 and "IP is temporarily blocked" in resp.text:
            _unblock_all_ips()
            time.sleep(0.2)
            continue
        return resp
    return resp


def _resilient_top(method, url, **kwargs):
    for attempt in range(3):
        resp = _orig_top_request(method, url, **kwargs)
        if resp.status_code == 403 and "IP is temporarily blocked" in resp.text:
            _unblock_all_ips()
            time.sleep(0.2)
            continue
        return resp
    return resp


_requests.Session.request = _resilient_request
_requests.request = _resilient_top
# also patch the top-level convenience helpers
for _fn in ("get", "post", "put", "patch", "delete"):
    def _make(m):
        def wrapper(url, **kwargs):
            return _resilient_top(m, url, **kwargs)
        return wrapper
    setattr(_requests, _fn, _make(_fn.upper()))
