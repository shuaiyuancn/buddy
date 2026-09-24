import os
import uuid
import pytest

import src.single_instance
from src.single_instance import acquire_single_instance_lock, release_single_instance_lock

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Named mutexes are Windows-only")


@pytest.fixture
def mutex_name():
    # Unique per test so a running Buddy (or another test) never collides
    name = f"Local\\Buddy-Test-{uuid.uuid4()}"
    yield name
    release_single_instance_lock()


def test_first_acquire_succeeds_and_holds_handle(mutex_name):
    assert acquire_single_instance_lock(mutex_name) is True
    assert src.single_instance._mutex_handle is not None


def test_second_instance_is_rejected_while_lock_is_held(mutex_name):
    assert acquire_single_instance_lock(mutex_name) is True

    # Simulate a second process: forget our handle so the next call opens the mutex afresh
    held = src.single_instance._mutex_handle
    src.single_instance._mutex_handle = None
    try:
        assert acquire_single_instance_lock(mutex_name) is False
        assert src.single_instance._mutex_handle is None
    finally:
        src.single_instance._mutex_handle = held


def test_lock_can_be_reacquired_after_release(mutex_name):
    assert acquire_single_instance_lock(mutex_name) is True
    release_single_instance_lock()
    assert src.single_instance._mutex_handle is None
    assert acquire_single_instance_lock(mutex_name) is True
