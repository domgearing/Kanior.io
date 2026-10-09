"""Authenticated web-to-desktop capture commands; no provider credentials cross this API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, Response

from api.foundation_routes import CsrfSessionDep, SessionDep
from contracts.models import (
    RecorderCommand,
    RecorderCommandCreate,
    RecorderCommandPoll,
    RecorderCommandResult,
    RecorderDevice,
    RecorderDevicePage,
    RecorderHeartbeat,
)
from domain.recorder_control import RecorderControlService


def create_recorder_control_router(service: RecorderControlService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get(
        "/recorder-devices", response_model=RecorderDevicePage, operation_id="list_recorder_devices"
    )
    def list_devices(session: SessionDep) -> RecorderDevicePage:
        return service.list_devices(session.context)

    @router.put(
        "/recorder-devices/{device_id}/heartbeat",
        response_model=RecorderDevice,
        operation_id="heartbeat_recorder_device",
    )
    def heartbeat(
        device_id: UUID,
        report: RecorderHeartbeat,
        session: CsrfSessionDep,
        x_recorder_device_token: str = Header(),
    ) -> RecorderDevice:
        return service.heartbeat(session.context, device_id, report, x_recorder_device_token)

    @router.post(
        "/recorder-devices/{device_id}/commands",
        response_model=RecorderCommand,
        status_code=201,
        operation_id="create_recorder_command",
    )
    def submit(
        device_id: UUID,
        command: RecorderCommandCreate,
        response: Response,
        session: CsrfSessionDep,
    ) -> RecorderCommand:
        result = service.submit(session.context, device_id, command)
        response.headers["Location"] = f"/api/v1/recorder-commands/{result.command_id}"
        return result

    @router.post(
        "/recorder-devices/{device_id}/commands/claim",
        response_model=RecorderCommandPoll,
        operation_id="poll_recorder_command",
    )
    def poll(
        device_id: UUID, session: CsrfSessionDep, x_recorder_device_token: str = Header()
    ) -> RecorderCommandPoll:
        return service.poll(session.context, device_id, x_recorder_device_token)

    @router.get(
        "/recorder-commands/{command_id}",
        response_model=RecorderCommand,
        operation_id="get_recorder_command",
    )
    def get_command(command_id: UUID, session: SessionDep) -> RecorderCommand:
        return service.get_command(session.context, command_id)

    @router.post(
        "/recorder-commands/{command_id}/result",
        response_model=RecorderCommand,
        operation_id="complete_recorder_command",
    )
    def complete(
        command_id: UUID,
        result: RecorderCommandResult,
        session: CsrfSessionDep,
        x_recorder_device_token: str = Header(),
    ) -> RecorderCommand:
        return service.complete(session.context, command_id, result, x_recorder_device_token)

    return router
