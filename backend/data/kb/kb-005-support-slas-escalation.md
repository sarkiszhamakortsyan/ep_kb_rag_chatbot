---
id: kb-005
title: Support Tiers, SLAs & Escalation Process
product: OmniCorp Customer Success
lang: en
updated: 2026-09-10
tags: [support, sla, priority, escalation, uptime, service-credits]
---

# Support Tiers, SLAs & Escalation Process

This document defines OmniCorp's support tiers, ticket priorities, response-time commitments, uptime SLA and the internal escalation path. CSMs use it to set customer expectations and to decide when and how to escalate.

## Support tiers

| Tier | Included with | Channels | Hours |
|---|---|---|---|
| Standard | Starter | Email, Support Portal | Business hours (Mon–Fri, 09:00–18:00 in the customer's region) |
| Premium | Business | Email, Support Portal, chat | 24/5 (Monday 00:00 to Friday 24:00, customer's region) |
| Enterprise | Enterprise | Email, Support Portal, chat, phone hotline | 24/7/365, with a named Technical Account Manager (TAM) |

Business customers can purchase Enterprise-tier support separately as the **Premier Support** add-on.

## Ticket priorities

| Priority | Definition | Examples |
|---|---|---|
| **P1 – Critical** | Production unavailable, security incident, or data loss with no workaround | Platform down for all users; all admins locked out by SSO (kb-001); suspected data breach |
| **P2 – High** | Major function degraded for many users; workaround difficult | SSO failing for some users; webhooks failing platform-wide; backup restore request (kb-003) |
| **P3 – Normal** | Minor function impaired, workaround available | Single integration misbehaving; GDPR request the Admin Console cannot handle (kb-003) |
| **P4 – Low** | Question, configuration help, feature request, planned change | How-to questions; temporary API limit increase for a migration (kb-002) |

Only P1 tickets can be opened by phone. P1 tickets opened by email or portal are automatically upgraded to phone callback for Enterprise customers.

## First-response targets

| Priority | Standard | Premium | Enterprise |
|---|---|---|---|
| P1 | 4 business hours | 1 hour | 15 minutes |
| P2 | 8 business hours | 4 hours | 1 hour |
| P3 | 2 business days | 1 business day | 4 hours |
| P4 | 5 business days | 2 business days | 1 business day |

First response means a human engineer has acknowledged and started working on the ticket. For P1 tickets on the Enterprise tier, OmniCorp provides status updates at least **every hour** until resolution.

## Uptime SLA and service credits

| Plan | Monthly uptime commitment |
|---|---|
| Starter | No SLA (best effort) |
| Business | 99.9% |
| Enterprise | 99.95% |

Scheduled maintenance announced **at least 72 hours in advance** is excluded from uptime calculations. If the monthly uptime falls below the commitment, the customer receives a service credit:

| Monthly uptime | Credit (% of monthly fee) |
|---|---|
| Below commitment, but at least 99.0% | 10% |
| Below 99.0% | 25% |

Credits must be requested by the customer through the CSM **within 30 days** after the end of the affected month. Credits are applied to the next invoice and are the customer's sole remedy for downtime.

## Escalation path

CSMs escalate when a ticket misses its response target, when a customer relationship is at risk, or when a technical issue needs senior attention:

1. **Support ticket** with the correct priority. Always the first step.
2. **Support Duty Manager**: if the first-response target is missed, or the customer is dissatisfied with progress. Reach them via the **"Escalate" button** in the Support Portal.
3. **Escalation Manager**: automatically engaged for any P1 not resolved within **4 hours**, or on Duty Manager request.
4. **VP Customer Success**: for P1 incidents lasting more than **24 hours**, contract-threatening situations, or executive-level complaints.

Every P1 incident receives a written **root-cause analysis (RCA)** within **5 business days** after resolution, which the CSM shares with the customer.

## When the knowledge base has no answer (human handoff)

If a CSM cannot find the answer in the internal knowledge base, they must not guess. Instead:

- Post the question in the **#cs-experts** Slack channel, or open an **Internal SME Request** in the Support Portal. Subject-matter experts answer within **1 business day**.
- For urgent customer-facing issues, open a customer ticket with the appropriate priority instead of an internal request.
- If the answer is missing from the documentation, tag the request with `kb-gap` so the Documentation team can add an article.

## Customer communication guidelines

- Acknowledge every escalation to the customer within **1 business hour**, even without a solution.
- Never promise a fix date that Engineering has not confirmed.
- Communicate in a professional, factual tone and reference the ticket number in every update.
