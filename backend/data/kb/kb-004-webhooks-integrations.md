---
id: kb-004
title: Webhooks & Integrations Configuration Manual
product: OmniCorp Platform
lang: en
updated: 2026-09-01
tags: [webhooks, integrations, salesforce, slack, events]
---

# Webhooks & Integrations Configuration Manual

Webhooks let the OmniCorp Platform notify a customer's systems in real time when something changes. Built-in connectors for Salesforce and Slack cover the most common integration needs without custom code. This manual covers configuration, security, delivery guarantees and troubleshooting.

## Webhooks

### Creating an endpoint

Admins create webhook endpoints in **Admin Console → Integrations → Webhooks → Add endpoint**:

1. Enter the HTTPS URL of the receiver. Plain HTTP URLs and private IP ranges are rejected.
2. Select the event types to subscribe to.
3. Save. The **signing secret** is displayed **once**; the customer must store it securely.

A workspace can have up to **25 endpoints** on Business and up to **100 endpoints** on Enterprise. Webhooks are not available on the Starter plan.

### Event types

| Event | Triggered when |
|---|---|
| `record.created` | A record is created in the UI, by API or by import |
| `record.updated` | Any field of a record changes |
| `record.deleted` | A record is moved to the Trash |
| `user.provisioned` | A user is created, including by JIT or SCIM (kb-001) |
| `user.deprovisioned` | A user is deactivated, including by SCIM |
| `export.completed` | A bulk data export has finished (kb-003) |
| `audit.event` | Any audit log entry (Enterprise only; used for SIEM streaming) |

Each payload contains `id`, `type`, `created_at`, `workspace_id` and a `data` object. Event IDs are unique and should be used to de-duplicate deliveries, because delivery is **at least once**.

### Verifying signatures

Every request carries the headers `X-Omni-Signature` and `X-Omni-Timestamp`. The signature is an **HMAC-SHA256** of `<timestamp>.<raw request body>` using the signing secret, hex-encoded. Receivers must:

1. Recompute the HMAC and compare it using a constant-time comparison.
2. Reject requests whose timestamp is more than **5 minutes** old to prevent replay attacks.

### Rotating the signing secret

Choose **Rotate secret** on the endpoint. For **24 hours** both the old and the new secret are valid, and each request is signed with both (two signatures separated by a comma in `X-Omni-Signature`). The customer should deploy the new secret within that window.

### Delivery, retries and auto-disable

- The receiver must return a **2xx** status within **10 seconds**; otherwise the attempt counts as failed.
- Failed deliveries are retried **8 times** with exponential backoff: after 1 minute, 5 minutes, 15 minutes, 1 hour, 3 hours, 6 hours, 12 hours and 24 hours.
- If all attempts fail, the event is marked as failed. After **3 consecutive events** have failed permanently, the endpoint is **automatically disabled** and all workspace Admins receive an email.
- Delivery throughput is limited to **50 events per second** per endpoint. Excess events are queued, not dropped.

Outbound webhook deliveries do **not** count against the customer's API rate limit. Calls that the receiver makes back to the OmniCorp API, for example to fetch full record details, **do** count (see *API Rate Limits & Quotas Reference*, kb-002). Receivers should use the data in the payload where possible.

### Delivery log and replay

**Admin Console → Integrations → Webhooks → Delivery log** shows every attempt from the last **7 days**, with request, response code and latency. Individual events, or all failed events for an endpoint, can be replayed from the log. Events older than 7 days cannot be replayed.

## Salesforce connector

Available on **Business** and **Enterprise**.

- **Setup**: **Admin Console → Integrations → Salesforce → Connect**, then authorize with a dedicated Salesforce integration user that has API access and "Modify All" permission on the synchronized objects.
- **Sync**: bi-directional synchronization of Accounts, Contacts and Opportunities every **15 minutes**. Enterprise customers can lower the interval to 5 minutes.
- **Field mapping**: default mappings are created automatically; custom fields are mapped in the connector's **Field mapping** tab. Conflicts are resolved with "last modified wins".
- **API usage**: every sync cycle uses approximately **1 OmniCorp API request per 200 changed records**, and this traffic counts against the workspace's per-minute rate limit and daily quota (kb-002). Large initial syncs of more than 500,000 records should be planned with the CSM and may require a temporary limit increase.
- Sync errors appear in the connector's **Sync history** and can be sent to Slack.

## Slack connector

Available on **all plans**.

- **Setup**: **Admin Console → Integrations → Slack → Add to Slack**, then choose the Slack workspace and channels.
- **Notifications**: rules send messages to channels for record events, mentions, failed Salesforce syncs and disabled webhook endpoints.
- Starter workspaces are limited to **3 notification rules**; Business and Enterprise have no limit.
- The connector posts as the "OmniCorp" bot and needs to be invited into private channels.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| All deliveries fail with timeout | Receiver takes longer than 10 s | Acknowledge immediately with 2xx and process asynchronously |
| Signature mismatch | Body was parsed or re-serialized before verification, or wrong secret after rotation | Verify against the raw body; check the secret |
| Endpoint shows "Disabled" | 3 events failed after all retries | Fix the receiver, re-enable the endpoint, replay failed events |
| Duplicate events | Normal at-least-once delivery | De-duplicate by event `id` |
| Salesforce sync stops with `QUOTA_EXCEEDED` | Daily API quota used up (kb-002) | Reduce sync frequency or request a quota increase |
