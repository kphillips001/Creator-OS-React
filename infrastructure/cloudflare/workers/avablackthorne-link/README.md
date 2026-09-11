# avablackthorne-link

Source-controlled capture of the authoritative production Cloudflare Worker.

The Worker preserves the existing `avablackthorne.com` card page and `/go`
Telegram redirect. Attributed `/me?p=...` visits receive a short-lived signed
handoff. Valid `/go` handoffs enqueue a privacy-bounded click event without
delaying the Telegram redirect.

The Wrangler file declares `ava-x-link-clicks` and its dead-letter queue, but
does not create either resource. Before deployment, create those queues and add
the `X_LINK_HANDOFF_SECRET` and `X_LINK_INGESTION_SECRET` Worker secrets. Use
the same ingestion secret in Creator-OS as
`X_LINK_ANALYTICS_INGESTION_SECRET`.

Nothing in the Creator-OS test or build workflow deploys this Worker. A future,
explicit deployment from the repository root would be:

```powershell
npx wrangler deploy --config infrastructure/cloudflare/workers/avablackthorne-link/wrangler.toml
```

Run that command only after reviewing the target Cloudflare account and the
live Worker diff.
