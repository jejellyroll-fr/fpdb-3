"""Unit test for InterProcessLock acquire and release functionality."""

import os

from fpdb_3_legacy import interlocks


def test_interprocess_lock_acquire_and_release():
    """Verify that InterProcessLock acquires and releases lock cleanly."""
    lock_name = f"test_fpdb_lock_{os.getpid()}"
    lock1 = interlocks.InterProcessLock(name=lock_name)

    assert lock1.acquire("test_source1") is True
    assert lock1.locked() is True

    # Second acquire in same process should fail
    lock2 = interlocks.InterProcessLock(name=lock_name)
    assert lock2.acquire("test_source2", wait=False) is False

    # Release lock1
    lock1.release()

    # Second lock can now be acquired
    assert lock2.acquire("test_source2", wait=False) is True
    lock2.release()
