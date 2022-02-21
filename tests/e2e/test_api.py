import pytest

from httpx import AsyncClient


# from unittest.mock import patch


@pytest.mark.anyio
async def test_add_service(app, base_url):
    print(app)
    print("url: ", app.url_path_for("add_service"))
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(app.url_path_for("add_service"))
    print("response: ", response)
    assert False


# @pytest.mark.asyncio
# async def test_create_service(app, base_url, repository, handler, service, valid_access_token_in_db):
#     service.id = given_id = -1
#     print("service: ", service.dict())
#     with (
#         patch("app.database.get_directories", return_value=["fastdeploytest"]),
#         patch("app.database.get_service_config", return_value={"steps": []}),
#     ):
#         async with AsyncClient(app=app, base_url=base_url) as client:
#             response = await client.post(
#                 app.url_path_for("create_service"),
#                 headers={"authorization": f"Bearer {valid_access_token_in_db}"},
#                 json=service.dict(),
#             )

#     result = response.json()
#     print("result: ", result)

#     assert response.status_code == 200

#     # make sure added step was dispatched to event handlers
#     assert handler.last_event.name == service.name

#     result = response.json()
#     service_from_db = await repository.get_service_by_name(result["name"])
#     assert service_from_db.id != given_id
