"""A configurable number of concurrent tests that behave like remote cloud jobs."""

from __future__ import annotations

from pathlib import Path

import pytest

from .simulator import (
    CloudJobCase,
    CloudJobConfig,
    SimulatedCloud,
)

CONFIG_DIRECTORY = Path(__file__).with_name("configs")


@pytest.mark.asyncio_cooperative
async def test_cloud_validation_job(cloud_job_case: CloudJobCase) -> None:
    """Submit a config, wait for remote work, retrieve it, and validate it."""

    case = cloud_job_case
    config = CloudJobConfig.from_file(CONFIG_DIRECTORY / case.config_filename)
    cloud = SimulatedCloud()

    job = await cloud.submit(config, case)
    while await cloud.poll(job) != "succeeded":
        pass
    result = await cloud.retrieve(job)

    assert result.job_id == case.job_id
    assert result.config_digest == config.digest
    assert result.image == config.image
    assert result.region == config.region
    assert result.validated_checks == config.checks
    assert result.virtual_runtime_seconds == case.virtual_runtime_seconds
