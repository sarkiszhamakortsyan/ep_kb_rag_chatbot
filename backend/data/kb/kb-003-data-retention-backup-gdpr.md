---
id: kb-003
title: Data Retention, Backup & GDPR Policy
product: OmniCorp Platform
lang: en
updated: 2026-06-02
tags: [retention, backup, gdpr, privacy, data-residency, export]
---

# Data Retention, Backup & GDPR Policy

This document describes how long OmniCorp keeps customer data, how it is backed up and restored, where it is stored, and how data-protection requests under the GDPR are handled. CSMs should use it to answer customer security and compliance questionnaires.

## Data retention

### Active workspace data

Records, files and comments are kept for as long as the customer's subscription is active. Items deleted by users go to the **Trash**, where they can be restored for **30 days**. After 30 days they are permanently deleted from live systems.

### Audit logs

| Plan | Audit log retention |
|---|---|
| Starter | 90 days |
| Business | 1 year |
| Enterprise | 7 years (configurable between 1 and 7 years) |

Audit logs can be streamed to the customer's SIEM using webhooks or exported as CSV.

### After contract termination

1. The workspace becomes **read-only** for a **30-day grace period**. During this time Admins can export all data.
2. After the grace period, the workspace and its data are deleted from live systems **within 60 days**.
3. Copies in backups are purged as backups expire, **no later than 35 days** after deletion from live systems.
4. On request, OmniCorp provides a written **certificate of deletion** once step 3 is complete.

## Backups and restore

- **Backup frequency**: daily full snapshots for all plans. Enterprise workspaces additionally receive **hourly incremental** backups.
- **Backup retention**: 35 days.
- **Encryption**: backups are encrypted at rest with AES-256 and stored in the same data region as the workspace, in a separate availability zone.

| Plan | Recovery point objective (RPO) | Recovery time objective (RTO) |
|---|---|---|
| Starter and Business | 24 hours | 8 hours |
| Enterprise | 1 hour | 4 hours |

### Requesting a restore

Customers cannot restore backups themselves. A restore of an entire workspace, or a point-in-time restore of specific records, must be requested through a **P2** support ticket (see *Support Tiers, SLAs & Escalation Process*, kb-005). Single items deleted within the last 30 days should be recovered from the Trash instead. A restore overwrites changes made after the restore point, so the customer must confirm the target timestamp in writing.

## Data residency

Customers choose a data region when the workspace is created:

- **EU**: Frankfurt, Germany
- **US**: Virginia, United States
- **APAC**: Sydney, Australia

All customer content, backups and logs remain in the chosen region. Moving an existing workspace to another region is available on the **Enterprise** plan only, as a paid professional-services engagement that requires a planned maintenance window. API rate limits are the same in all regions.

## GDPR and data-protection requests

OmniCorp acts as a **data processor** for customer content. A Data Processing Agreement (DPA) including the EU Standard Contractual Clauses is available to all customers in **Admin Console → Legal**. The current list of sub-processors is published on the OmniCorp Trust Center, and customers are notified by email **30 days before** a new sub-processor is added.

### Data subject requests

Customer Admins handle requests from their own users and contacts in **Admin Console → Privacy → Data Requests**:

- **Access / portability**: generates a JSON and CSV export of all personal data about the person.
- **Rectification**: personal fields can be edited directly or via the API.
- **Erasure ("right to be forgotten")**: removes the person's personal data from live systems within **30 days**; copies in backups disappear as the backups expire (35 days).

The GDPR allows one month to answer a data subject. OmniCorp's internal target for completing processor-side actions is **10 business days**. Requests that the Admin Console cannot handle are raised as **P3** support tickets.

### Personal data of deprovisioned users

When a user is deactivated (manually or through SCIM, see kb-001), their profile is retained so that content ownership and audit history remain intact. If the customer wants the person's personal data removed, an Admin must submit an erasure request for that user.

## Data export

Admins can export the full workspace from **Admin Console → Data → Export** in JSON or CSV format, or via the Bulk Export API. At most **5 export jobs** can run concurrently per workspace (see *API Rate Limits & Quotas Reference*, kb-002). When an export finishes, OmniCorp sends an `export.completed` webhook event (see kb-004) and emails a download link valid for **7 days**.
