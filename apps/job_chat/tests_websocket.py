from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.job_chat.ws_auth import JWTAuthMiddleware
from Core.asgi import build_websocket_application


class DummyUser:
    id = 1
    username = "ws-owner"
    is_authenticated = True
    is_active = True
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


    @async_to_sync
    async def test_invalid_messages_are_rejected_without_saving(self):
        application = build_websocket_application()
        save_message = AsyncMock()

        with (
            patch("apps.job_chat.ws_auth.JWTAuthentication.get_validated_token", return_value=object()),
            patch("apps.job_chat.ws_auth.JWTAuthentication.get_user", return_value=DummyUser()),
            patch(
                "apps.job_chat.views.consumers.JobChatConsumer.check_job_permission",
                new=AsyncMock(return_value=True),
            ),
            patch("apps.job_chat.views.consumers.JobChatConsumer.save_message", new=save_message),
        ):
            communicator = WebsocketCommunicator(
                application,
                "/ws/jobs/11111111-1111-1111-1111-111111111111/chat/?token=test-token",
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()

            for payload in (
                {"type": "message", "content": "hi", "msg_type": "system"},
                {"type": "message", "content": "{\"widget_type\": \"proposal\", \"data\": {}}", "msg_type": "widget"},
                {"type": "message", "content": "   "},
            ):
                await communicator.send_json_to(payload)
                event = await communicator.receive_json_from()
                self.assertEqual(event["type"], "error")

            save_message.assert_not_awaited()
            await communicator.disconnect()

class WebSocketJWTMiddlewareTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ws-user",
            email="ws-user@example.com",
            password="ChangeMe123!",
            email_verified=True,
        )
        self.middleware = JWTAuthMiddleware(app=None)
        # database_sync_to_async closes "obsolete" connections, which would drop
        # the connection holding this test's transaction on PostgreSQL.
        patcher = patch("channels.db.close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _resolve(self, token):
        return async_to_sync(self.middleware._get_user)(token)

    def test_valid_token_resolves_the_user(self):
        self.assertEqual(self._resolve(str(AccessToken.for_user(self.user))), self.user)

    def test_suspended_user_is_anonymous_even_with_a_valid_access_token(self):
        token = str(AccessToken.for_user(self.user))
        self.user.status = self.user.Status.SUSPENDED
        self.user.save(update_fields=["status"])

        self.assertIsInstance(self._resolve(token), AnonymousUser)

    def test_token_for_deleted_user_is_anonymous_instead_of_crashing(self):
        token = str(AccessToken.for_user(self.user))
        self.user.delete()

        self.assertIsInstance(self._resolve(token), AnonymousUser)

    def test_garbage_token_is_anonymous(self):
        self.assertIsInstance(self._resolve("not-a-jwt"), AnonymousUser)
