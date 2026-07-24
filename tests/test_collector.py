"""collector exit code: 0 while any section succeeds, 1 on total failure."""

import collector


def _boom(*a, **k):
    raise RuntimeError("section down")


def test_all_sections_ok_exits_zero(write_snapshot, monkeypatch):
    from tests.conftest import make_row
    write_snapshot(1000, [make_row(address="1.2.3.4")])
    # services runs for real over the snapshot; the other two are faked.
    monkeypatch.setattr(collector, "collect_propagation", lambda: {"collected": 0})
    monkeypatch.setattr(collector, "write_unique_estimate",
                        lambda: {"estimate": 1.0, "reachable": 1})
    assert collector.main() == 0


def test_partial_failure_exits_zero(monkeypatch):
    # propagation + services down, unique up -> still a soft success.
    monkeypatch.setattr(collector, "collect_propagation", _boom)
    monkeypatch.setattr(collector, "refresh_services_series", _boom)
    monkeypatch.setattr(collector, "write_unique_estimate",
                        lambda: {"estimate": 5.0, "reachable": 9})
    assert collector.main() == 0


def test_total_failure_exits_one(monkeypatch):
    monkeypatch.setattr(collector, "collect_propagation", _boom)
    monkeypatch.setattr(collector, "refresh_services_series", _boom)
    monkeypatch.setattr(collector, "write_unique_estimate", _boom)
    result = collector.run()
    assert result["failed"] == ["propagation", "services", "unique"]
    assert collector.main() == 1
