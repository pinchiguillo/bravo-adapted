# Job chat WebSocket

```
wss://<host>/ws/jobs/<job_uuid>/chat/
```

Only the job's requester, the provider that owns the announcement, and staff can connect.

## Authentication

Send a JWT access token in one of these ways, in order of preference:

1. **Subprotocol** (browsers):
   `new WebSocket(url, ["bearer", accessToken])`. The server accepts with the `bearer` subprotocol.
2. **`Authorization: Bearer <token>` header** (native and server-side clients).
3. **`?token=<token>` query parameter**: legacy web client only. It is accepted while
   `JOB_CHAT_WS_ALLOW_QUERY_TOKEN` is on, because query strings end up in proxy logs.

Browser connections must come from an origin in `WS_ALLOWED_ORIGINS`. Connections without an
`Origin` header (native apps) rely on the token alone.

The handshake is rejected when the token is invalid, the account is not active, or the user is not a
participant of the job.

## Messages from the client

Every frame is a JSON object with a `type`.

| `type` | Fields | Effect |
|---|---|---|
| `history` | `before` (optional message UUID) | Replies with a page of history |
| `message` | `content`, `msg_type` (`plain_text` default, or `widget`) | Stores and broadcasts the message |
| `proposal_status` | `message_uuid`, `status` (`accepted` or `rejected`) | Answers a price proposal |
| `typing` | `is_typing` (boolean) | Broadcasts a typing indicator |

A `widget` message is a price proposal; `content` is a JSON string:

```json
{"widget_type": "proposal",
 "data": {"title": "Deep clean", "price": 120.5, "price_mode": "total", "currency": "EUR"}}
```

`description`, `category` and `subcategory` are optional. `price` is a non-negative amount with
two decimals, `price_mode` is one of `total`, `hourly`, `daily`, `monthly`, `per_sqm`, `per_unit`,
and `currency` one of `EUR`, `USD`, `GBP`. The server always stores a new proposal with
`"status": "pending"`. Only the other participant can answer it, once; accepting it moves a pending
job to `active`.

## Messages from the server

| `type` | Fields |
|---|---|
| `history` | `data`: messages, oldest first; `has_more`: older messages exist (pass the first UUID as `before`) |
| `message` | `data`: a stored or updated message (`uuid`, `user_id`, `username`, `type`, `content`, `attachments`, `created_at`, `updated_at`) |
| `user_status` | `status` (`online` or `offline`), `user_id`, `username` |
| `typing` | `user_id`, `username`, `is_typing` |
| `error` | `message` |

## Limits and session checks

- Frames other than `typing` count against `JOB_CHAT_WS_RATE_LIMIT` per user per
  `JOB_CHAT_WS_RATE_WINDOW` seconds, across all of that user's sockets.
- Identical typing indicators within two seconds are dropped.
- Before acting on a frame, the server checks that the access token has not expired and that the
  account is still active and still a participant. If not, it sends an `error` and closes with
  code **4401**; the client should refresh its token and reconnect.
- Binary frames and JSON that is not an object get an `error` frame.

The same rules apply to the REST endpoints under `/api/jobs/<job_uuid>/`, and messages sent or
answered over REST are broadcast to connected sockets.
