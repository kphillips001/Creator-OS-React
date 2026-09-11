from pathlib import Path
import subprocess


WORKER = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "cloudflare"
    / "workers"
    / "avablackthorne-link"
    / "worker.js"
)


def test_authoritative_worker_preserves_redirect_and_card_contract():
    source = WORKER.read_text(encoding="utf-8")

    assert 'const TELEGRAM_URL = "https://t.me/+zqVdLYlEbqc3M2Ix";' in source
    assert 'const CARD_IMAGE = "https://ava-x-card.knphillips01.workers.dev/?v=2";' in source
    assert 'if (url.pathname === "/go")' in source
    assert "Response.redirect(TELEGRAM_URL, 302)" in source
    assert '<meta name="twitter:card" content="summary">' in source
    assert '<meta name="twitter:title" content="Ava Blackthorne">' in source
    assert '<meta name="twitter:description" content="Come find me over here 💋">' in source
    assert '<meta property="og:title" content="Ava Blackthorne">' in source
    assert '<meta property="og:description" content="Come find me over here 💋">' in source
    assert "window.location.replace(${JSON.stringify(redirectPath)})" in source
    assert '"content-type": "text/html; charset=utf-8"' in source
    assert ': "public, max-age=300"' in source
    assert '"private, no-store"' in source


def test_non_go_paths_share_the_html_response_and_preserve_unattributed_redirect():
    source = WORKER.read_text(encoding="utf-8")

    redirect_branch = source.index('if (url.pathname === "/go")')
    html_response = source.index("return new Response(html")
    assert redirect_branch < html_response
    assert 'url.pathname === "/me"' not in source
    assert 'let redirectPath = "/go"' in source
    assert 'event.waitUntil(X_LINK_CLICKS.send(message))' in source
    assert 'eventType: "X_TELEGRAM_CTA_HANDOFF"' in source
    assert 'classification: "LIKELY_BROWSER"' in source
    assert "ip.src" not in source
    assert "request.cf" not in source
    assert "Boolean(userAgent)" in source


def test_worker_runtime_handoff_security_card_parity_and_redirect_resilience():
    subprocess.run(
        ["node", str(Path(__file__).with_name("avablackthorne_link_worker_runtime.cjs"))],
        check=True,
    )
