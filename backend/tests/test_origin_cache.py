"""Tests for bounded custom-domain origin verification caching."""
from backend.security.origin_cache import OriginVerificationCache


def test_verified_origin_result_is_cached_until_ttl_expires():
    now = [100.0]
    cache = OriginVerificationCache(ttl_seconds=5, max_entries=10, clock=lambda: now[0])
    calls = []

    def resolver(host):
        calls.append(host)
        return host == "school.example"

    assert cache.get_or_resolve("School.Example", resolver) is True
    assert cache.get_or_resolve("school.example", resolver) is True
    assert calls == ["school.example"]

    now[0] += 5.1
    assert cache.get_or_resolve("school.example", resolver) is True
    assert calls == ["school.example", "school.example"]


def test_negative_origin_decisions_are_cached_but_resolver_errors_are_not():
    cache = OriginVerificationCache(ttl_seconds=5)
    calls = []

    def denied(host):
        calls.append(host)
        return False

    assert cache.get_or_resolve("unknown.example", denied) is False
    assert cache.get_or_resolve("unknown.example", denied) is False
    assert calls == ["unknown.example"]

    cache.invalidate("unknown.example")
    attempts = [0]

    def unavailable(_host):
        attempts[0] += 1
        raise RuntimeError("database unavailable")

    for _ in range(2):
        try:
            cache.get_or_resolve("unknown.example", unavailable)
        except RuntimeError:
            pass
        else:
            raise AssertionError("resolver failure should propagate")
    assert attempts == [2]


def test_origin_cache_is_bounded_and_supports_targeted_invalidation():
    cache = OriginVerificationCache(ttl_seconds=5, max_entries=2)
    calls = []

    def resolver(host):
        calls.append(host)
        return True

    for host in ("a.example", "b.example", "c.example"):
        assert cache.get_or_resolve(host, resolver)
    assert len(cache._entries) == 2

    # The least recently used entry was evicted.
    assert cache.get_or_resolve("a.example", resolver)
    assert calls.count("a.example") == 2

    cache.invalidate("a.example")
    assert cache.get_or_resolve("a.example", resolver)
    assert calls.count("a.example") == 3
