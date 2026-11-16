from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deploy.entrypoints import dependencies


@pytest.mark.asyncio
async def test_interleaved_refusals_own_fresh_exception_and_headers():
    exceptions = []
    for _ in range(3):
        for getter in (
            dependencies.get_current_active_user,
            dependencies.get_current_active_service,
            dependencies.get_current_active_deployment,
            dependencies.get_current_config,
        ):
            args = ("synthetic-invalid-token",)
            if getter is not dependencies.get_current_config:
                args += (SimpleNamespace(uow=object()),)
            with pytest.raises(HTTPException) as refused:
                await getter(*args)
            error = refused.value
            assert error.status_code == 401
            assert error.detail == "Could not validate credentials"
            assert error.headers == {"WWW-Authenticate": "Bearer"}
            frames = []
            traceback = error.__traceback__
            while traceback:
                frames.append(traceback.tb_frame)
                traceback = traceback.tb_next
            assert len(frames) == 2
            exceptions.append(error)
    assert len({id(error) for error in exceptions}) == len(exceptions)
    assert len({id(error.headers) for error in exceptions}) == len(exceptions)
