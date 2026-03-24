from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from backend.app.domain.entities.job import JobStatus


@dataclass(slots=True)
class ExecutionSnapshot:
    job_id: str
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None
    latest_activity: str | None = None


class ExecutionProvider(ABC):
    @abstractmethod
    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        workdir: str | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_status(self, job_id: str) -> JobStatus:
        raise NotImplementedError

    @abstractmethod
    def get_result(self, job_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_error(self, job_id: str) -> str | None:
        raise NotImplementedError

    def has_job(self, job_id: str) -> bool:
        return False

    def get_snapshot(self, job_id: str) -> ExecutionSnapshot:
        return ExecutionSnapshot(
            job_id=job_id,
            status=self.get_status(job_id),
            response=self.get_result(job_id),
            error=self.get_error(job_id),
            provider_session_id=self.get_provider_session_id(job_id),
            phase=self.get_phase(job_id),
            latest_activity=self.get_latest_activity(job_id),
        )

    def watch_job(
        self,
        job_id: str,
        on_change: Callable[[ExecutionSnapshot], None],
    ) -> Callable[[], None] | None:
        return None

    def supports_job_cancellation(self) -> bool:
        return False

    def cancel_job(self, job_id: str) -> bool:
        return False

    @abstractmethod
    def get_provider_session_id(self, job_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_phase(self, job_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_activity(self, job_id: str) -> str | None:
        raise NotImplementedError
