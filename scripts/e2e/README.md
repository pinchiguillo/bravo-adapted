# End-to-end smoke scripts

These scripts exercise the API through the nginx gateway of a running stack
(`docker compose up`). They are not part of the unit/integration suite and are
never collected by the test runner.

```bash
pip install -r scripts/e2e/requirements.txt
python3 scripts/e2e/smoke_asset_upload.py                 # defaults to http://localhost:24356
python3 scripts/e2e/smoke_job_chat_full_flow.py --url <base_url>
./scripts/e2e/validate_legal_documents_via_nginx.sh       # runs inside the compose stack
```

| Script | What it checks |
|---|---|
| `smoke_asset_upload.py` | Presigned S3 upload flow for generic assets |
| `smoke_announcement_workflow.py` | Announcement creation and image uploads, plus negative cases |
| `smoke_announcement_patch.py` | PATCH of an announcement and its nested subservices |
| `smoke_new_announcement_creation_workflow.py` | Single-request creation of an announcement with subservices and prices |
| `smoke_job_chat_attachments.py` | Job chat messages with S3 attachments |
| `smoke_job_chat_full_flow.py` | Full job chat flow, including WebSocket streaming |
| `validate_legal_documents_via_nginx.sh` | Legal document uploads land in the private bucket |
| `validate_plan_tiers_via_public_gateway.sh` | Plan tiers are exposed through the public catalog |
