"""Controlled workload for pytest-asyncio-cooperative PR #86."""

import asyncio

import pytest

_real_asyncio_wait = asyncio.wait
_first_wait = True


async def _batch_same_turn_completions(*args, **kwargs):
    """Make asyncio.wait's documented multi-completion case deterministic."""

    kwargs["timeout"] = None
    done, pending = await _real_asyncio_wait(*args, **kwargs)
    global _first_wait

    if _first_wait and kwargs.get("return_when") == asyncio.FIRST_COMPLETED:
        _first_wait = False
        for _ in range(1000):
            if len(done) >= 3:
                break
            await asyncio.sleep(0)
            newly_done = {task for task in pending if task.done()}
            done.update(newly_done)
            pending.difference_update(newly_done)
        if len(done) < 3:
            raise RuntimeError("could not form the three-task completion batch")
    return done, pending


# PR #86 is specifically about one wait call returning several completed tasks.
# Event-loop scheduling details can otherwise make that condition nondeterministic.
asyncio.wait = _batch_same_turn_completions


_first_replacements_completed = asyncio.Event()
_replacement_count = 0


@pytest.mark.parametrize("index", range(12))
@pytest.mark.asyncio_cooperative
async def test_refill_pressure(index: int) -> None:
    """Complete three initial tasks together while replacements remain queued."""

    if index < 3:
        return
    if index == 3:
        await _first_replacements_completed.wait()
        return

    global _replacement_count
    await asyncio.sleep(0.12)
    _replacement_count += 1
    if _replacement_count == 3:
        _first_replacements_completed.set()
