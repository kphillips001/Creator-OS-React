# Telegram Authentication Recommendation

**Decision date:** June 19, 2026  
**Scope:** Architecture and planning only; no implementation or database changes

## 1. Executive Summary

The recommended production authentication architecture is **one Telegram Bot Token per AI creator**, using Telegram's Bot Platform as the transport boundary. The existing phone-authenticated Telethon user session should not be migrated into the production design.

Bot Token authentication is the stronger fit because Telegram explicitly provides bots for automated third-party services, bot identities are transparent to users, credentials can be isolated per creator, and update delivery can use supported long polling or webhooks. It also avoids tying production availability to a creator phone number, interactive OTP/2FA recovery, and a portable MTProto session file.

The tradeoff is deliberate: bots cannot initiate a conversation with a user who has never contacted them, and their bot status is visible. Acquisition must therefore route users through an explicit start action, such as a creator-specific `t.me` link. This improves consent and anti-spam posture but prevents the system from silently imitating an ordinary personal account. Fanvue Media Link sales remain compatible because Telegram authentication does not change the Fanvue commerce system; links can be delivered after the user initiates the Telegram conversation and identity attribution is established.

For future multi-creator support, each creator should receive a distinct bot identity and token while sharing the existing FanvueChatbot intelligence platform. If replying under an actual creator business account later becomes a hard requirement, **Telegram Business connected bots** may be evaluated as a separate, bot-based enhancement. A phone-authenticated user-session automation model should not be the default fallback.

This recommendation is conditional on a compliance gate before implementation: users must receive clear disclosure of automation/AI processing and monetization, give explicit and revocable consent where required, and have an accessible privacy policy and data-deletion route. Telegram policies should be revalidated immediately before implementation.

## 2. Current Telegram Authentication Review

The reference Telegram repository contains two incompatible authentication intentions:

- `login_amanda.py` creates a Telethon `TelegramClient` using `TG_API_ID`, `TG_API_HASH`, and a phone-authenticated session named `tg_sessions/amanda`. Its interactive `start()` flow requests the phone number, login code, and possibly 2FA, then persists authorization.
- `listener_amanda.py` reopens that same session, listens for incoming private text messages through `events.NewMessage`, reads `sender.id`, and replies with `event.respond()`.
- The configuration layer requires Ava and Amanda bot-token environment variables, but the listener never consumes those tokens. Conversely, the listener imports API credentials that the configuration module does not expose. The current repository is therefore not a coherent Bot Token implementation.
- The session directory is ignored by Git, which is appropriate, but no deployment-grade secret storage, encryption, rotation, recovery, or multi-instance ownership model exists.

Telethon documents that a file session stores the authorization key and enough state to log in again without another code. Possession of a leaked session can therefore permit account access; an explicit path is also needed to avoid working-directory-dependent placement. Telethon additionally requires an API ID and non-revocable API hash, even when signing in a bot through Telethon. See the [Telethon session documentation](https://docs.telethon.dev/en/stable/concepts/sessions.html) and [Telethon sign-in documentation](https://docs.telethon.dev/en/stable/basic/signing-in.html).

Useful concepts from the reference implementation are limited to update listening, stable numeric Telegram identity, private-chat filtering, reply correlation, and reconnect intent. Its login script, session-file lifecycle, prompts, personas, memory, and business logic should not be migrated.

## 3. User Session Analysis

### Strengths

- Appears as an ordinary Telegram user rather than a visibly labeled bot.
- Can use broader MTProto account capabilities and can initiate conversations where Telegram account rules permit.
- May initially feel closer to a manually operated creator account.
- The existing reference listener demonstrates the basic mechanism.

### Weaknesses

- Production authentication depends on a phone number, OTP access, optional 2FA, account recovery, and a persistent authorization session.
- The session is effectively a high-value bearer credential. Copying it can transfer account control, while shared access across workers creates ownership and locking complexity.
- Every creator would require a separate Telegram account, phone lifecycle, session, recovery procedure, and health state. This scales operational burden linearly and expands the compromise radius.
- Account restrictions, flood controls, forced reauthentication, revoked sessions, SIM loss, or manual account use can interrupt automation unpredictably.
- A normal-looking account creates a serious transparency problem if users believe they are speaking directly with a human creator. The legacy persona instruction to conceal AI involvement is incompatible with a prudent production posture.
- Telegram's MTProto API terms prohibit actions on a user's behalf without their knowledge and consent and contain restrictive language concerning Telegram data and AI/ML systems. That makes a user-session AI automation architecture a materially higher policy risk. See the [Telegram API Terms](https://core.telegram.org/api/terms).

### Suitability

A user session may be retained only as a quarantined reference or used for narrowly controlled manual testing after explicit policy, legal, and security approval. It is not recommended for automated creator conversations, Fanvue sales messaging, or the multi-creator production platform.

## 4. Bot Token Analysis

### Strengths

- Telegram's Bot Platform is purpose-built for automated third-party applications and supports private-chat updates through long polling or webhooks. Bots receive messages sent to them in private chats. See [Telegram Bots](https://core.telegram.org/bots) and the [Telegram Bot FAQ](https://core.telegram.org/bots/faq).
- The visible bot designation makes the nature of the account less misleading and supports an explicit AI/automation disclosure.
- A token is straightforward to provision and isolate per creator and can be revoked or rotated through BotFather without a phone-login ceremony.
- One bot per creator produces a clean mapping from Telegram bot identity to creator persona and Fanvue account.
- Hosted deployments can use authenticated HTTPS webhooks; development or a single-worker deployment can use long polling.
- The Bot Platform's terms provide a direct framework for privacy notices, consent, secure storage, deletion, credential protection, and predictable app behavior.

### Limitations

- A bot cannot begin a conversation with a user who has never contacted it. The user must start the bot, add it to a group, or otherwise initiate contact. Creator profiles and campaigns therefore need an explicit Telegram start link.
- The bot label reduces the illusion of an ordinary human account. The system should build creator presence through branding, tone, continuity, and useful conversation—not concealed automation.
- Bots remain subject to messaging limits and anti-spam rules. Re-engagement must be consented, throttled, and easy to stop.
- Bot tokens are still full-control bearer credentials. A leaked token permits an attacker to operate the bot, so secure custody and rotation are mandatory.
- Telegram authentication does not itself solve user consent, age/content safeguards, retention, or Fanvue purchase attribution.

### Protocol and client recommendation

The architecture decision is **Bot Token authentication**. For the initial implementation, prefer the official HTTP Bot API through a maintained Bot API client rather than running a bot through Telethon's MTProto client. Telethon bot login would still add API ID/hash and session-state requirements without a demonstrated need for MTProto-only features.

Use webhooks for a stable hosted HTTPS environment and long polling for local development or a deliberately single-consumer runtime. Do not operate both update mechanisms for the same bot.

## 5. Multi-Creator Considerations

The target unit of isolation should be a creator-specific Telegram bot:

| Concern | Recommended boundary |
|---|---|
| Public Telegram identity | One bot per creator |
| Authentication | One token per bot, stored as a secret reference |
| Fanvue ownership | One explicit bot-to-`fanvue_account_id` mapping |
| Persona | Loaded from the mapped creator account, never inferred from message text |
| User identity | `(telegram_bot_id, telegram_user_id)` mapped to the canonical internal user |
| Updates | Per-bot webhook secret/path or independently owned polling stream |
| Operations | Per-bot health, rate limits, feature flags, rotation, and disable switch |
| Memory | Existing canonical user memory, scoped through the resolved creator account |

This model shares application code and the FanvueChatbot intelligence services while isolating credentials and public identities. A single bot that switches among multiple creator personas is not recommended: it weakens brand clarity, identity resolution, sales attribution, opt-out handling, and compromise isolation.

Telegram Business currently supports connecting bots that can process and answer selected private chats on behalf of a business account. This could later provide creator-account presentation while retaining bot-based authorization and explicit permissions. It should be evaluated separately because its eligibility, permissions, account ownership, user disclosure, and operational behavior differ from a normal bot. See [Telegram Bots for Business](https://core.telegram.org/bots/features#bots-for-business).

## 6. Security Considerations

- Store bot tokens in a managed secret store in production, not in source control, logs, database rows, generated reports, or plaintext deployment artifacts. The application configuration should reference the secret rather than expose it.
- Assign BotFather ownership and recovery to a controlled organizational account with documented administrators, 2FA, and an offboarding procedure.
- Use a different token for every creator. Never reuse a token across environments; separate development, staging, and production bots.
- Validate webhook requests with Telegram's webhook secret-token mechanism over TLS. Use an unguessable endpoint, strict request-size limits, schema validation, and rate limiting. IP filtering may be defense in depth, not the sole trust mechanism.
- Treat update processing as at-least-once delivery: deduplicate by bot identity and Telegram update/message identifiers before invoking the decision engine or sending sales links.
- Encrypt retained Telegram content and identity mappings at rest with keys stored separately. Minimize raw update retention and exclude message bodies, tokens, and Fanvue Media Link secrets from logs.
- Publish an accessible privacy policy and implement explicit, informed, active, and revocable consent for AI processing and memory. Define retention, export, correction, opt-out, and deletion behavior before launch. The [Telegram Bot Platform Developer Terms](https://telegram.org/tos/bot-developers) require careful handling of user data, secure storage, and deletion when data is no longer required or the user requests it.
- Clearly disclose that the conversation is automated or AI-assisted and that Fanvue links are commercial. Do not migrate persona rules that require concealing AI involvement or impersonating a human.
- Perform a dedicated legal and platform-policy review for creator content, age gating, media previews, and Fanvue outbound sales links. Authentication choice does not establish that all content or sales behavior is permitted.
- Maintain a credential-rotation and incident runbook covering token revocation, webhook replacement, queued messages, user notification, forensic logging, and per-creator isolation.

## 7. Operational Considerations

### Bot Token operations

- Provisioning is repeatable: register a bot, record its immutable bot ID, bind it to one creator/Fanvue account, store its token, configure update delivery, and verify health.
- Recovery normally consists of rotating a token or restoring update delivery; it does not require access to a creator's phone or SMS code.
- Each bot can be disabled independently without interrupting other creators or the FanvueChatbot intelligence platform.
- Webhooks fit the existing FastAPI-style hosted service, provided public TLS ingress and one authoritative update route are available. Long polling is simpler for development but requires strict single-consumer ownership.
- Health monitoring should cover last update received, last successful response, Telegram API errors, rate-limit responses, queue depth, Fanvue-link generation failures, and per-creator circuit-breaker state.
- Delivery retries must distinguish transient Telegram failures from permanent blocks, deactivated users, invalid chats, and revoked tokens.

### User Session operations

- Initial login and recovery are interactive and depend on phone, OTP, and sometimes 2FA access.
- Session files need encrypted storage, exclusive runtime ownership, backup policy, revocation monitoring, and careful transfer between hosts.
- Horizontal scaling is hazardous without a purpose-built distributed session and update-ownership design.
- Manual use of the same creator account can create conflicts with automation and complicate auditability.
- Per-creator account restrictions and reauthentication events create substantial support burden.

The Bot Token model is therefore materially simpler to deploy, monitor, rotate, and scale. It also creates clearer accountability because every action is attributable to a named bot and creator mapping.

## 8. Recommended Architecture

### Decision

Adopt **Bot Token authentication with one dedicated Telegram bot per creator**.

The Telegram layer should authenticate the bot, receive updates, normalize Telegram identifiers and message data, and deliver responses. It must not own persona selection, memory, buyer intelligence, relationship state, offer logic, or Fanvue commerce decisions. Those remain authoritative in FanvueChatbot.

The identity path should be:

```text
bot token (secret) -> authenticated Telegram bot ID
Telegram bot ID -> creator / fanvue_account_id / persona
(Telegram bot ID, Telegram user ID) -> canonical internal user
canonical user + fanvue_account_id -> existing memory and buyer intelligence
```

The normal conversation path should be:

```text
User opens creator-specific t.me link and starts bot
  -> Telegram update is authenticated and deduplicated
  -> bot ID resolves the creator/Fanvue account
  -> Telegram user resolves to the canonical internal user
  -> existing FanvueChatbot decision engine and memory produce an action
  -> Telegram adapter sends text or an approved media/link response
  -> Fanvue remains the destination and source of truth for Media Link sales
```

Bot credentials must never become user identity keys. Usernames are mutable and may be absent; the stable Telegram user ID, scoped by receiving bot ID, is the transport identity. Fanvue identity and purchase attribution remain canonical through explicit mappings rather than username matching.

### Decision comparison

| Criterion | User Session | Bot Token |
|---|---:|---:|
| Fit for automated AI service | Poor | Strong, subject to consent/compliance |
| Transparent user expectations | Poor | Strong |
| Multi-creator isolation | Weak/expensive | Strong |
| Credential rotation | Difficult | Straightforward |
| Phone/OTP dependency | Yes | No at runtime |
| User-first initiation required | No in some cases | Yes |
| Human-account appearance | Strong | Intentionally limited |
| Hosted scaling and recovery | Complex | Strong |
| Recommended for production | No | **Yes** |

## 9. Migration Impact

This decision resolves the authentication gate identified in the migration blueprint and changes what should be reused from the reference Telegram repository:

- Do not migrate `login_amanda.py`, phone login, `.session` file handling, or the existing Telethon client bootstrap.
- Do not treat the current listener as production scaffolding. Preserve only its conceptual lessons: receive an update, identify the sender with a stable numeric ID, restrict supported chat types, and reply in context.
- Replace the contradictory legacy configuration model during implementation with one explicit Bot Token mode. Existing token variable names are evidence of intent, not a secure or scalable credential design.
- Plan a bot-account registry containing non-secret bot identity, creator/Fanvue ownership, status, and a secret-manager reference. This report does not authorize or define a database migration.
- Scope Telegram identity by bot and user ID so the same Telegram user can interact with multiple creators without memory or sales attribution crossing accounts.
- Add creator-specific start links and onboarding because bots cannot contact entirely new users first.
- Preserve the FanvueChatbot decision engine, persona system, memory continuity, buyer intelligence, purchase synchronization, Media Link creation, and Fanvue commerce authority unchanged behind the transport boundary.
- Add disclosure, consent, opt-out, retention, deletion, and incident-response requirements to the implementation acceptance criteria.
- Treat Telegram Business connected bots as an optional later workstream, not a prerequisite for the initial adapter.

No Telegram user-session credentials or legacy Telegram memory should be imported. Existing Fanvue users must be linked through a controlled identity flow; Telegram usernames alone are insufficient proof of identity.

## 10. Implementation Guidance

The following is planning guidance only:

1. **Complete the compliance gate.** Approve the AI disclosure, commercial disclosure, privacy policy, consent record, retention/deletion rules, age/content controls, and acceptable Fanvue-link behavior against current Telegram and applicable legal requirements.
2. **Define the creator-bot contract.** Specify immutable bot ID, creator/Fanvue account mapping, persona ownership, environment, status, secret reference, update mode, and emergency disable behavior.
3. **Pilot one dedicated creator bot.** Use a truthful name, avatar, description, automation disclosure, privacy link, creator-specific start link, and isolated non-production credentials before any multi-creator rollout.
4. **Define the transport contract.** Normalize bot ID, Telegram user ID, chat ID, message/update ID, text or media metadata, reply context, and timestamps. Exclude Telegram library objects from the decision engine.
5. **Define identity linking.** Resolve `(bot_id, telegram_user_id)` to the canonical internal user through an explicit, auditable flow. Specify collision, unlink, relink, deletion, and cross-creator behavior before schema work begins.
6. **Choose update delivery.** Use authenticated webhooks for stable hosted production or single-owner long polling where public ingress is unsuitable. Document deduplication, retry, backpressure, ordering, and graceful shutdown.
7. **Create secret and recovery procedures.** Establish BotFather ownership, per-environment storage, rotation, revocation, incident response, access auditing, and creator offboarding before credentials reach a runtime.
8. **Validate the commerce path.** Confirm that Telegram messages carry only approved previews or Fanvue Media Links, that purchase state still synchronizes from Fanvue, and that attribution survives transport retries and multiple creator bots.
9. **Run a limited operational pilot.** Test blocked users, duplicate updates, revoked tokens, rate limits, Telegram outages, Fanvue failures, opt-out/deletion, and memory isolation before enabling sales traffic.
10. **Scale by replication, not persona switching.** Onboard each additional creator as a separately authenticated bot using the same adapter contract and shared FanvueChatbot intelligence services.

The next implementation specification should define the **Telegram bot account and canonical identity-link contracts** without yet building the listener. Authentication is now decided; reliable identity resolution remains the prerequisite for safely connecting Telegram transport to preserved FanvueChatbot memory and commerce.

