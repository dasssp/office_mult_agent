import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.connectors.base import ASRService, MeetingIMConnector
from app.schemas import RequestContext
from app.services.runtime_state import BackgroundTask, BackgroundTaskService

TaskHandler = Callable[
    [BackgroundTask, RequestContext],
    Awaitable[dict[str, object]],
]


class TaskCancelled(RuntimeError):
    """Raised by a handler after observing a persisted cancellation request."""


@dataclass
class MeetingTranscriptionHandler:
    meeting_connector: MeetingIMConnector
    asr: ASRService
    tasks: BackgroundTaskService
    poll_interval_seconds: float = 1.0

    async def __call__(
        self, task: BackgroundTask, context: RequestContext
    ) -> dict[str, object]:
        meeting_id = str((task.payload or {}).get("meeting_id", "")).strip()
        if not meeting_id:
            raise ValueError("meeting_id is required")

        current = await self.tasks.get(task.task_id, context)
        if current.cancel_requested:
            raise TaskCancelled
        recording = await self.meeting_connector.get_recording(
            meeting_id=meeting_id,
            context=context,
        )
        submitted = await self.asr.submit_transcription(
            recording_ref=str(recording["recording_ref"]),
            context=context,
        )
        asr_task_id = str(submitted["task_id"])

        while True:
            current = await self.tasks.get(task.task_id, context)
            if current.cancel_requested:
                raise TaskCancelled
            status = await self.asr.get_transcription_status(
                task_id=asr_task_id,
                context=context,
            )
            state = str(status.get("status", "running"))
            if state == "completed":
                result = await self.asr.get_transcription_result(
                    task_id=asr_task_id,
                    context=context,
                )
                return {
                    "asr_task_id": asr_task_id,
                    "segments": list(result.get("segments", [])),
                }
            if state == "failed":
                raise RuntimeError("ASR_FAILED")
            await asyncio.sleep(self.poll_interval_seconds)


class AsyncTaskWorker:
    """Claims durable jobs and executes them outside the API process."""

    def __init__(
        self,
        *,
        tasks: BackgroundTaskService,
        handlers: dict[str, TaskHandler],
        worker_id: str,
        task_timeout_seconds: float = 300,
        lease_timeout_seconds: int = 360,
        retry_delay_seconds: int = 10,
    ) -> None:
        self._tasks = tasks
        self._handlers = handlers
        self._worker_id = worker_id
        self._task_timeout_seconds = task_timeout_seconds
        self._lease_timeout_seconds = lease_timeout_seconds
        self._retry_delay_seconds = retry_delay_seconds

    async def run_once(self) -> bool:
        task = await self._tasks.claim(
            self._worker_id,
            lease_timeout_seconds=self._lease_timeout_seconds,
        )
        if task is None:
            return False
        context = RequestContext(
            thread_id=f"task:{task.task_id}",
            tenant_id=task.tenant_id,
            operator_id=task.operator_id or "system-worker",
        )
        handler = self._handlers.get(task.kind)
        if handler is None:
            task.attempts = task.max_attempts
            await self._tasks.fail(
                task,
                error_code="TASK_HANDLER_NOT_FOUND",
                retry_delay_seconds=0,
            )
            return True
        try:
            async with asyncio.timeout(self._task_timeout_seconds):
                result = await handler(task, context)
            latest = await self._tasks.get(task.task_id, context)
            if latest.cancel_requested:
                task.cancel_requested = True
                raise TaskCancelled
            await self._tasks.succeed(task, result)
        except TaskCancelled:
            task.cancel_requested = True
            await self._tasks.fail(
                task,
                error_code="TASK_CANCELLED",
                retry_delay_seconds=0,
            )
        except TimeoutError:
            await self._tasks.fail(
                task,
                error_code="TASK_TIMEOUT",
                retry_delay_seconds=self._retry_delay_seconds,
            )
        except (KeyError, TypeError, ValueError):
            task.attempts = task.max_attempts
            await self._tasks.fail(
                task,
                error_code="INVALID_TASK_PAYLOAD",
                retry_delay_seconds=0,
            )
        except Exception:  # noqa: BLE001 - worker boundary must persist all handler failures
            await self._tasks.fail(
                task,
                error_code="TASK_EXECUTION_FAILED",
                retry_delay_seconds=self._retry_delay_seconds,
            )
        return True

    async def run_forever(
        self,
        *,
        stop_event: asyncio.Event,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        while not stop_event.is_set():
            handled = await self.run_once()
            if handled:
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=poll_interval_seconds,
                )
            except TimeoutError:
                pass
