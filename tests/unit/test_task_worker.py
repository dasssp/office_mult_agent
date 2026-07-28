import pytest

from app.schemas import RequestContext
from app.services.runtime_state import BackgroundTaskService
from app.services.task_worker import AsyncTaskWorker, MeetingTranscriptionHandler


def _context() -> RequestContext:
    return RequestContext(
        thread_id="thread-1",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )


@pytest.mark.asyncio
async def test_worker_claims_and_completes_durable_task() -> None:
    tasks = BackgroundTaskService()
    task = await tasks.create(
        kind="example",
        payload={"value": 7},
        context=_context(),
    )

    async def handler(_task, _context):
        return {"answer": 42}

    worker = AsyncTaskWorker(
        tasks=tasks,
        handlers={"example": handler},
        worker_id="worker-1",
    )
    assert await worker.run_once() is True
    completed = await tasks.get(task.task_id, _context())
    assert completed.status == "succeeded"
    assert completed.result == {"answer": 42}
    assert completed.attempts == 1


@pytest.mark.asyncio
async def test_worker_retries_failure_then_succeeds() -> None:
    tasks = BackgroundTaskService()
    task = await tasks.create(kind="unstable", context=_context(), max_attempts=2)
    calls = 0

    async def handler(_task, _context):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient detail must not be persisted")
        return {"status": "recovered"}

    worker = AsyncTaskWorker(
        tasks=tasks,
        handlers={"unstable": handler},
        worker_id="worker-1",
        retry_delay_seconds=0,
    )
    await worker.run_once()
    waiting = await tasks.get(task.task_id, _context())
    assert waiting.status == "retry_wait"
    assert waiting.error_code == "TASK_EXECUTION_FAILED"
    await worker.run_once()
    completed = await tasks.get(task.task_id, _context())
    assert completed.status == "succeeded"
    assert completed.attempts == 2


@pytest.mark.asyncio
async def test_cancelled_queued_task_is_never_executed() -> None:
    tasks = BackgroundTaskService()
    task = await tasks.create(kind="example", context=_context())
    await tasks.cancel(task.task_id, _context())
    called = False

    async def handler(_task, _context):
        nonlocal called
        called = True
        return {}

    worker = AsyncTaskWorker(
        tasks=tasks,
        handlers={"example": handler},
        worker_id="worker-1",
    )
    assert await worker.run_once() is False
    assert called is False
    assert (await tasks.get(task.task_id, _context())).status == "cancelled"


@pytest.mark.asyncio
async def test_stale_running_task_is_reclaimed_after_worker_crash() -> None:
    tasks = BackgroundTaskService()
    task = await tasks.create(kind="example", context=_context(), max_attempts=2)
    first_claim = await tasks.claim("crashed-worker", lease_timeout_seconds=360)
    assert first_claim is not None
    reclaimed = await tasks.claim("replacement-worker", lease_timeout_seconds=0)
    assert reclaimed is not None
    assert reclaimed.task_id == task.task_id
    assert reclaimed.locked_by == "replacement-worker"
    assert reclaimed.attempts == 2


class _MeetingConnector:
    async def get_recording(self, *, meeting_id, context):
        return {"recording_ref": f"mock://{meeting_id}"}


class _ASR:
    async def submit_transcription(self, *, recording_ref, context):
        return {"task_id": "asr-1", "status": "queued"}

    async def get_transcription_status(self, *, task_id, context):
        return {"task_id": task_id, "status": "completed"}

    async def get_transcription_result(self, *, task_id, context):
        return {"segments": [{"segment_id": "s1", "text": "done", "confidence": 1.0}]}


@pytest.mark.asyncio
async def test_meeting_transcription_runs_in_worker() -> None:
    tasks = BackgroundTaskService()
    task = await tasks.create(
        kind="meeting_transcription",
        payload={"meeting_id": "meeting-1"},
        context=_context(),
    )
    handler = MeetingTranscriptionHandler(
        meeting_connector=_MeetingConnector(),
        asr=_ASR(),
        tasks=tasks,
        poll_interval_seconds=0,
    )
    worker = AsyncTaskWorker(
        tasks=tasks,
        handlers={"meeting_transcription": handler},
        worker_id="worker-1",
    )
    await worker.run_once()
    result = await tasks.get(task.task_id, _context())
    assert result.status == "succeeded"
    assert result.result is not None
    assert result.result["asr_task_id"] == "asr-1"
