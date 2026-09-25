---
id: kb-001
title: SSO & User Provisioning Guide
product: OmniCorp Platform
lang: en
updated: 2026-08-14
tags: [sso, saml, oidc, scim, security, identity]
---

# SSO & User Provisioning Guide

This guide explains how to configure Single Sign-On (SSO) and automated user provisioning for an OmniCorp Platform workspace. It is intended for Customer Success Managers (CSMs) supporting customer IT administrators during onboarding and for troubleshooting.

## Plan availability

| Capability | Starter | Business | Enterprise |
|---|---|---|---|
| Password + MFA login | Yes | Yes | Yes |
| SAML 2.0 SSO | No | Yes | Yes |
| OpenID Connect (OIDC) SSO | No | No | Yes |
| Just-in-time (JIT) provisioning | No | Yes | Yes |
| SCIM 2.0 provisioning | No | No | Yes |
| SSO enforcement (block password login) | No | Yes | Yes |

Customers on the Starter plan who ask for SSO must upgrade to Business (SAML) or Enterprise (SAML, OIDC and SCIM).

## Configuring SAML 2.0

SSO is configured by a workspace **Owner** or **Admin** in **Admin Console → Security → Single Sign-On**.

1. Select **Add identity provider** and choose **SAML 2.0**.
2. Copy the service-provider values into the customer's identity provider (IdP), e.g. Okta, Microsoft Entra ID or Google Workspace:
   - **ACS URL**: `https://<tenant>.omnicorp.io/auth/saml/acs`
   - **Entity ID (Audience)**: `https://<tenant>.omnicorp.io/saml/metadata`
   - **Name ID format**: `emailAddress`
3. Upload the IdP metadata XML, or paste the IdP SSO URL and X.509 signing certificate manually.
4. Map the required attributes: `email` (required), `firstName`, `lastName`, and optionally `omni_role` (see *Role mapping*).
5. Click **Test connection**. The test must succeed before SSO can be enabled.
6. Enable SSO. Optionally turn on **Enforce SSO**, which blocks password login for everyone except break-glass accounts.

### Certificate rotation

IdP signing certificates usually expire every one to three years. A new certificate can be uploaded **up to 30 days before** the current one expires. During this overlap window both certificates are accepted, so the customer can switch their IdP to the new certificate without downtime. If a certificate expires without a replacement, all SSO logins fail with error `SSO-401`.

## Configuring OpenID Connect (Enterprise)

OIDC is available on the Enterprise plan only. In **Admin Console → Security → Single Sign-On**, choose **OpenID Connect** and provide the issuer URL, client ID and client secret from the IdP. The redirect URI to register at the IdP is `https://<tenant>.omnicorp.io/auth/oidc/callback`. OmniCorp requests the scopes `openid email profile` and, if role mapping is used, `groups`.

## Role mapping

OmniCorp has four workspace roles: **Viewer**, **Editor**, **Admin** and **Owner**. Roles can be assigned from the IdP by sending the attribute (SAML) or claim (OIDC) `omni_role` with one of these values. If the attribute is missing, new users receive the **default role** configured under Single Sign-On settings (Viewer by default). The Owner role can never be assigned through SSO; it must be granted manually by an existing Owner.

## Just-in-time (JIT) provisioning

With JIT provisioning enabled, a user account is created automatically the first time a person signs in through SSO. JIT does **not** deactivate users: when someone leaves the customer's company their OmniCorp account remains active until an Admin deactivates it. Customers who need automatic deprovisioning should use SCIM (Enterprise).

## SCIM 2.0 provisioning (Enterprise)

SCIM lets the customer's IdP create, update and deactivate OmniCorp users and groups automatically.

- **SCIM base URL**: `https://api.omnicorp.io/scim/v2`
- **Authentication**: bearer token generated in **Admin Console → Security → Provisioning**. The token is shown only once and is valid for **365 days**. Admins receive an email reminder 14 days before it expires.
- **Rate limit**: SCIM requests use a dedicated bucket of **300 requests per minute** per workspace and do not consume the general API rate limit (see *API Rate Limits & Quotas Reference*, kb-002).

### Deprovisioning behaviour

When the IdP deactivates a user through SCIM, the OmniCorp account is suspended, all active sessions and personal API tokens are revoked **within 5 minutes**, and a `user.deprovisioned` webhook event is emitted (see *Webhooks & Integrations Configuration Manual*, kb-004). The user's content is kept and ownership can be transferred by an Admin. Personal data of deprovisioned users is handled according to the *Data Retention, Backup & GDPR Policy* (kb-003).

## Break-glass access

When **Enforce SSO** is enabled, at least one **Owner** account must remain able to sign in with password and MFA. This break-glass account is used if the IdP is unavailable or misconfigured. OmniCorp recommends two break-glass Owners stored in the customer's password vault. If every administrator is locked out, the customer must open a **P1** support ticket and pass identity verification (see *Support Tiers, SLAs & Escalation Process*, kb-005).

## Troubleshooting

| Error | Meaning | Typical fix |
|---|---|---|
| `SSO-401` | Signature validation failed | Certificate expired or wrong certificate uploaded; upload the current IdP certificate |
| `SSO-403` | User not assigned to the OmniCorp app in the IdP | Assign the user or group in the IdP |
| `SSO-408` | Assertion expired | Clock skew between IdP and OmniCorp exceeds **3 minutes**; fix NTP on the IdP |
| `SSO-409` | Email already belongs to another workspace | Remove the user from the other workspace or use a different email |
| `SCIM-429` | SCIM rate limit exceeded | IdP is sending more than 300 requests per minute; reduce sync frequency |

If an SSO outage affects only some users, open a **P2** ticket. If all users are locked out and no break-glass account works, open a **P1** ticket.
