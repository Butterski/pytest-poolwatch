"""Deterministic async simulation of a small cloud validation service."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SIMULATION_SEED = 0xC10D
REAL_SECONDS_PER_VIRTUAL_MINUTE = 0.010
VIRTUAL_SECONDS_PER_REAL_SECOND = 60 / REAL_SECONDS_PER_VIRTUAL_MINUTE
POLL_INTERVAL_SECONDS = 30
SUBMIT_LATENCY_SECONDS = 0.0005
RETRIEVE_LATENCY_SECONDS = 0.0005

JobStatus = Literal["running", "succeeded"]


@dataclass(frozen=True, slots=True)
class CloudJobConfig:
    """The validated contents of a submitted JSON config file."""

    schema_version: int
    image: str
    region: str
    checks: tuple[str, ...]

    @classmethod
    def from_file(cls, path: Path) -> CloudJobConfig:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 1:
            raise ValueError(f"{path} has an unsupported schema version")
        checks = tuple(str(check) for check in raw.get("checks", ()))
        if not checks:
            raise ValueError(f"{path} must configure at least one check")
        return cls(
            schema_version=1,
            image=str(raw["image"]),
            region=str(raw["region"]),
            checks=checks,
        )

    @property
    def digest(self) -> str:
        payload = {
            "checks": self.checks,
            "image": self.image,
            "region": self.region,
            "schema_version": self.schema_version,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class CloudJobCase:
    """A test case whose random-looking duration is chosen before execution."""

    index: int
    virtual_runtime_seconds: int
    config_filename: str

    @property
    def job_id(self) -> str:
        return f"cloud-job-{self.index:04d}"

    @property
    def pytest_id(self) -> str:
        return f"{self.job_id}-{self.virtual_runtime_seconds}s"


@dataclass(slots=True)
class SubmittedJob:
    """A private job receipt and its deterministic virtual clock."""

    case: CloudJobCase
    config: CloudJobConfig
    elapsed_virtual_seconds: int = 0


@dataclass(frozen=True, slots=True)
class CloudJobResult:
    """The result returned after the simulated service finishes."""

    job_id: str
    config_digest: str
    image: str
    region: str
    validated_checks: tuple[str, ...]
    virtual_runtime_seconds: int


class SimulatedCloud:
    """A local stand-in for an asynchronous submit/poll/retrieve API."""

    async def submit(
        self,
        config: CloudJobConfig,
        case: CloudJobCase,
    ) -> SubmittedJob:
        await asyncio.sleep(SUBMIT_LATENCY_SECONDS)
        return SubmittedJob(case=case, config=config)

    async def poll(self, job: SubmittedJob) -> JobStatus:
        remaining = job.case.virtual_runtime_seconds - job.elapsed_virtual_seconds
        if remaining <= 0:
            return "succeeded"

        virtual_step = min(POLL_INTERVAL_SECONDS, remaining)
        await asyncio.sleep(virtual_step / VIRTUAL_SECONDS_PER_REAL_SECOND)
        job.elapsed_virtual_seconds += virtual_step
        return (
            "succeeded"
            if job.elapsed_virtual_seconds >= job.case.virtual_runtime_seconds
            else "running"
        )

    async def retrieve(self, job: SubmittedJob) -> CloudJobResult:
        if job.elapsed_virtual_seconds < job.case.virtual_runtime_seconds:
            raise RuntimeError("cannot retrieve a cloud job before it succeeds")
        await asyncio.sleep(RETRIEVE_LATENCY_SECONDS)
        return CloudJobResult(
            job_id=job.case.job_id,
            config_digest=job.config.digest,
            image=job.config.image,
            region=job.config.region,
            validated_checks=job.config.checks,
            virtual_runtime_seconds=job.case.virtual_runtime_seconds,
        )


def build_cases(
    count: int,
    *,
    seed: int = SIMULATION_SEED,
) -> tuple[CloudJobCase, ...]:
    """Build stable random-duration cases without runtime timing randomness."""

    config_filenames = (
        "linux-validation.json",
        "windows-validation.json",
        "container-policy.json",
        "package-audit.json",
    )
    return tuple(
        CloudJobCase(
            index=index,
            virtual_runtime_seconds=random.Random(seed + index).randint(60, 300),
            config_filename=config_filenames[index % len(config_filenames)],
        )
        for index in range(count)
    )
