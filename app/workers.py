import asyncio
import signal
import socket

from app.config import get_settings
from app.connectors.registry import ConnectorRegistry
from app.database import Database
from app.repositories.runtime import SqlAlchemyRuntimeStateRepository
from app.services.runtime_state import BackgroundTaskService
from app.services.task_worker import AsyncTaskWorker, MeetingTranscriptionHandler


async def run_worker() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the background worker")
    if settings.task_worker_lease_seconds <= settings.task_worker_timeout_seconds:
        raise RuntimeError(
            "TASK_WORKER_LEASE_SECONDS must be greater than "
            "TASK_WORKER_TIMEOUT_SECONDS"
        )

    database = Database(settings.database_url)
    tasks = BackgroundTaskService(
        SqlAlchemyRuntimeStateRepository(database.session_factory)
    )
    connectors = ConnectorRegistry.for_environment(settings.app_env)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except NotImplementedError:
            pass

    meeting_handler = MeetingTranscriptionHandler(
        meeting_connector=connectors.meeting_im,
        asr=connectors.asr,
        tasks=tasks,
        poll_interval_seconds=settings.task_worker_poll_seconds,
    )
    worker = AsyncTaskWorker(
        tasks=tasks,
        handlers={"meeting_transcription": meeting_handler},
        worker_id=f"{socket.gethostname()}:{id(tasks)}",
        task_timeout_seconds=settings.task_worker_timeout_seconds,
        lease_timeout_seconds=settings.task_worker_lease_seconds,
        retry_delay_seconds=settings.task_worker_retry_delay_seconds,
    )
    try:
        await worker.run_forever(
            stop_event=stop_event,
            poll_interval_seconds=settings.task_worker_poll_seconds,
        )
    finally:
        await database.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
