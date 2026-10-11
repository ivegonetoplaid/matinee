"""A household service's run of failures: said as starting just after start, warned once past it, cleared by an
answer."""

from __future__ import annotations

import logging

from matinee.outage import STARTING_S, Outage


def test_a_failure_just_after_start_is_said_as_starting_then_warned_once_if_it_lasts() -> None:
    outage = Outage(started_at=0.0)
    assert outage.failed(1.0) == logging.INFO
    assert outage.failed(20.0) is None  # the run was said
    assert outage.failed(STARTING_S) == logging.WARNING  # it outlasted the start
    assert outage.failed(STARTING_S + 15) is None
    assert outage.answered() is True and outage.answered() is False
    assert outage.failed(STARTING_S + 30) == logging.WARNING  # a later run is warned at once


def test_a_failure_no_starting_service_gives_is_warned_at_once() -> None:
    assert Outage(started_at=0.0).failed(1.0, may_be_starting=False) == logging.WARNING
