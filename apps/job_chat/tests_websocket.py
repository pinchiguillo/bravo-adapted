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
                new=AsyncMock(return_value=(history_payload, False)),
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


CHAT_PATH = "/ws/jobs/11111111-1111-1111-1111-111111111111/chat/"


def authenticated(permission=True):
    """Patch JWT validation and the participant check for consumer-level tests."""
    return (
        patch("apps.job_chat.ws_auth.JWTAuthentication.get_validated_token", return_value=object()),
        patch("apps.job_chat.ws_auth.JWTAuthentication.get_user", return_value=DummyUser()),
        patch(
            "apps.job_chat.views.consumers.JobChatConsumer.check_job_permission",
            new=AsyncMock(return_value=permission),
        ),
    )


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    WS_ALLOWED_ORIGINS=["https://app.example.com"],
)
class JobChatWebSocketHardeningTests(SimpleTestCase):
    databases = {"default"}

    async def _connect(self, path=CHAT_PATH + "?token=t", headers=None, subprotocols=None):
        communicator = WebsocketCommunicator(
            build_websocket_application(), path, headers=headers or [], subprotocols=subprotocols
        )
        connected, subprotocol = await communicator.connect()
        return communicator, connected, subprotocol

    @async_to_sync
    async def test_browser_connections_from_other_origins_are_rejected(self):
        auth, user, permission = authenticated()
        with auth, user, permission:
            evil, evil_connected, _ = await self._connect(headers=[(b"origin", b"https://evil.example")])
            app, app_connected, _ = await self._connect(headers=[(b"origin", b"https://app.example.com")])
            native, native_connected, _ = await self._connect()

            self.assertFalse(evil_connected)
            self.assertTrue(app_connected)
            self.assertTrue(native_connected)
            await app.disconnect()
            await native.disconnect()

    @async_to_sync
    async def test_token_can_travel_in_the_subprotocol_instead_of_the_url(self):
        auth, user, permission = authenticated()
        with auth as validate, user, permission:
            communicator, connected, subprotocol = await self._connect(
                path=CHAT_PATH, subprotocols=["bearer", "header-token"]
            )

            self.assertTrue(connected)
            self.assertEqual(subprotocol, "bearer")
            validate.assert_called_once_with("header-token")
            await communicator.disconnect()

    @async_to_sync
    async def test_query_string_tokens_can_be_disabled(self):
        auth, user, permission = authenticated()
        with self.settings(JOB_CHAT_WS_ALLOW_QUERY_TOKEN=False), auth, user, permission:
            communicator, connected, _ = await self._connect()

            self.assertFalse(connected)

    @async_to_sync
    async def test_binary_frames_and_non_object_json_get_an_error_frame(self):
        auth, user, permission = authenticated()
        with auth, user, permission:
            communicator, _, _ = await self._connect()
            await communicator.receive_json_from()

            await communicator.send_to(bytes_data=b"\x00\x01")
            binary_error = await communicator.receive_json_from()
            await communicator.send_to(text_data="[1, 2]")
            array_error = await communicator.receive_json_from()

            self.assertEqual(binary_error["type"], "error")
            self.assertEqual(array_error["type"], "error")
            await communicator.disconnect()

    @async_to_sync
    async def test_client_frames_are_rate_limited_per_user(self):
        auth, user, permission = authenticated()
        history = patch(
            "apps.job_chat.views.consumers.JobChatConsumer.get_serialized_history",
            new=AsyncMock(return_value=([], False)),
        )
        with self.settings(JOB_CHAT_WS_RATE_LIMIT=2), auth, user, permission, history:
            communicator, _, _ = await self._connect()
            await communicator.receive_json_from()

            replies = []
            for _ in range(3):
                await communicator.send_json_to({"type": "history"})
                replies.append((await communicator.receive_json_from())["type"])

            self.assertEqual(replies, ["history", "history", "error"])
            await communicator.disconnect()

    @async_to_sync
    async def test_rejected_sockets_do_not_broadcast_presence(self):
        auth, user, _ = authenticated()
        permission = patch(
            "apps.job_chat.views.consumers.JobChatConsumer.check_job_permission",
            new=AsyncMock(side_effect=[True, False]),
        )
        with auth, user, permission:
            member, _, _ = await self._connect()
            await member.receive_json_from()

            intruder, intruder_connected, _ = await self._connect()
            # Daphne delivers websocket.disconnect after a rejected handshake; the test
            # communicator does not, so send it explicitly.
            await intruder.disconnect()

            self.assertFalse(intruder_connected)
            self.assertTrue(await member.receive_nothing(timeout=0.2))
            await member.disconnect()

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
