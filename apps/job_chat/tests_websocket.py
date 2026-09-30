from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, override_settings

from Core.asgi import build_websocket_application


class DummyUser:
    id = 1
    username = "ws-owner"
    is_authenticated = True
    is_staff = False


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class JobChatWebSocketTests(SimpleTestCase):
    # The consumer runs through channels' database_sync_to_async, which calls
    # close_old_connections() and therefore needs database access to be allowed.
    databases = {"default"}

    @async_to_sync
    async def test_authenticated_job_owner_can_connect_to_job_chat_websocket(self):
        application = build_websocket_application()

        with (
            patch(
                "apps.job_chat.ws_auth.JWTAuthentication.get_validated_token",
                return_value=object(),
            ),
            patch(
                "apps.job_chat.ws_auth.JWTAuthentication.get_user",
                return_value=DummyUser(),
            ),
            patch(
                "apps.job_chat.views.consumers.JobChatConsumer.check_job_permission",
                new=AsyncMock(return_value=True),
            ),
        ):
            communicator = WebsocketCommunicator(
                application,
                "/ws/jobs/11111111-1111-1111-1111-111111111111/chat/?token=test-token",
            )

            connected, _ = await communicator.connect()

            self.assertTrue(connected)
            event = await communicator.receive_json_from()
            self.assertEqual(event["type"], "user_status")
            self.assertEqual(event["status"], "online")
            self.assertEqual(event["username"], "ws-owner")

            await communicator.disconnect()

    @async_to_sync
    async def test_history_message_is_returned_when_requested(self):
        application = build_websocket_application()
        history_payload = [
            {
                "uuid": "msg-1",
                "user_id": 1,
                "username": "ws-owner",
                "type": "plain_text",
                "content": "hola",
                "attachments": [],
                "created_at": "2026-04-29T10:00:00Z",
                "updated_at": "2026-04-29T10:00:00Z",
            }
        ]

        with (
            patch(
                "apps.job_chat.ws_auth.JWTAuthentication.get_validated_token",
                return_value=object(),
            ),
            patch(
                "apps.job_chat.ws_auth.JWTAuthentication.get_user",
                return_value=DummyUser(),
            ),
            patch(
                "apps.job_chat.views.consumers.JobChatConsumer.check_job_permission",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "apps.job_chat.views.consumers.JobChatConsumer.get_serialized_history",
                new=AsyncMock(return_value=history_payload),
            ),
        ):
            communicator = WebsocketCommunicator(
                application,
                "/ws/jobs/11111111-1111-1111-1111-111111111111/chat/?token=test-token",
            )

            connected, _ = await communicator.connect()

            self.assertTrue(connected)
            await communicator.receive_json_from()

            await communicator.send_json_to({"type": "history"})
            event = await communicator.receive_json_from()

            self.assertEqual(event["type"], "history")
            self.assertEqual(event["data"], history_payload)

            await communicator.disconnect()

    @async_to_sync
    async def test_proposal_status_update_is_broadcast_as_message(self):
        application = build_websocket_application()
        updated_message = {
            "uuid": "msg-2",
            "user_id": 1,
            "username": "ws-owner",
            "type": "widget",
            "content": "{\"widget_type\":\"proposal\",\"data\":{\"status\":\"accepted\"}}",
            "attachments": [],
            "created_at": "2026-04-29T10:00:00Z",
            "updated_at": "2026-04-29T10:01:00Z",
        }

        with (
            patch(
                "apps.job_chat.ws_auth.JWTAuthentication.get_validated_token",
                return_value=object(),
            ),
            patch(
                "apps.job_chat.ws_auth.JWTAuthentication.get_user",
                return_value=DummyUser(),
            ),
            patch(
                "apps.job_chat.views.consumers.JobChatConsumer.check_job_permission",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "apps.job_chat.views.consumers.JobChatConsumer.update_proposal_status_message",
                new=AsyncMock(return_value=(updated_message, None)),
            ),
        ):
            communicator = WebsocketCommunicator(
                application,
                "/ws/jobs/11111111-1111-1111-1111-111111111111/chat/?token=test-token",
            )

            connected, _ = await communicator.connect()

            self.assertTrue(connected)
            await communicator.receive_json_from()

            await communicator.send_json_to(
                {
                    "type": "proposal_status",
                    "message_uuid": "msg-2",
                    "status": "accepted",
                }
            )
            event = await communicator.receive_json_from()

            self.assertEqual(event["type"], "message")
            self.assertEqual(event["data"], updated_message)

            await communicator.disconnect()
