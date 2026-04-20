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
