"""Rendered Business Chat scrolling regression at a 150%-zoom-equivalent viewport."""
import json
import sys
from urllib.parse import unquote

from playwright.sync_api import sync_playwright


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5174"
PERSON = {
    "personKey": "telegram:7:8:1", "telegramUserId": 1,
    "displayName": "Layout Fixture", "username": "layout_fixture",
    "identityStatus": "UNMAPPED", "buyerStatus": None,
    "lifetimeVerifiedRevenueMinor": None, "qualifyingPurchaseCount": None,
    "latestActivityAt": "2026-09-13T20:00:00Z",
    "latestMessagePreview": "latest fixture message",
    "activePurchaseIntent": False, "activeSalesSession": False,
    "controlMode": "AVA_AUTO", "operationalStatus": "REPLY_SCHEDULED",
    "nextAutomaticAttemptAt": "2026-09-13T20:30:00Z",
}


def fulfill(route, body):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def api_route(route):
    url = unquote(route.request.url)
    if "/messages?" in url:
        items = [{
            "eventKey": str(index), "direction": "CUSTOMER" if index % 2 else "AVA",
            "content": f"Rendered conversation message {index}",
            "timestamp": f"2026-09-13T{12 + index // 20:02d}:{index % 60:02d}:00Z",
            "telegramMessageId": index, "messageType": "ORDINARY_CHAT",
            "purchaseIntentId": None,
        } for index in range(1, 61)]
        fulfill(route, {"person": PERSON, "items": items,
                        "olderCursor": "older-page", "hasMoreOlder": True})
    elif "/intelligence" in url:
        fulfill(route, {"person": PERSON, "mappingStatus": "UNMAPPED", "partial": True,
            "operatorClassification": None, "effectiveAttentionPriority": "HIGH",
            "behavioralIntelligence": {"buyingIntent": "NONE", "currentSignal": "NONE", "salesStage": "PROSPECT"},
            "customerValue": {"buyerStatus": "UNMAPPED_PROSPECT", "valueTier": "ENGAGED_PROSPECT", "attentionTier": "HIGH", "lifetimeSpendMinor": None, "purchaseCount": None, "repeatBuyer": False, "relationshipLifecycle": "PROSPECT", "relationshipInvestment": "STANDARD", "continuationValue": "HIGH", "timeWasterRisk": "NONE", "retention": "NONE"},
            "salesPerformance": {"offersPresented": 0, "offersPurchased": 0, "offersNotPurchased": 0, "conversionRate": None, "lastOffer": None, "lastPurchase": None},
            "commercialState": {"activePurchaseIntent": None, "activeSalesSession": None, "activeOffer": None},
            "purchaseHistory": [], "relationshipIntelligence": {"location": None, "timezone": None, "interests": [], "pets": [], "music": [], "preferences": []}})
    elif "/market-tier" in url:
        fulfill(route, {"marketTier": "HIGH", "effectiveProspectInvestment": "HIGH", "highValueProspect": False, "verifiedBuyer": False, "repliesUsedToday": 0, "dailyReplyBudget": "FULL", "budgetStatus": "AVAILABLE", "nextBudgetResetAt": None, "prospectReplyLimit": None})
    elif "/control" in url:
        fulfill(route, {"mode": "AVA_AUTO", "controlVersion": 0,
                        "activePurchaseIntent": False, "activeSalesSession": False})
    else:
        fulfill(route, {"items": [PERSON], "nextCursor": None, "hasMore": False,
                        "summary": {"total": 1, "needsAttention": 0,
                                    "buyers": 0, "prospects": 1, "manual": 0}})


def metrics(page, selector):
    return page.locator(selector).evaluate("""node => { const style=getComputedStyle(node); return {
      display:style.display,height:style.height,minHeight:style.minHeight,maxHeight:style.maxHeight,
      overflow:style.overflow,overflowY:style.overflowY,clientHeight:node.clientHeight,
      scrollHeight:node.scrollHeight,flex:style.flex,gridTemplateRows:style.gridTemplateRows}; }""")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1024, "height": 600})
    page.on("console", lambda message: print("BROWSER", message.type, message.text))
    page.on("pageerror", lambda error: print("PAGEERROR", error))
    page.on("response", lambda response: print("HTTP", response.status, response.url) if response.status >= 400 else None)
    page.route("**/api/v1/**", api_route)
    page.goto(f"{BASE_URL}/business/relationships", wait_until="networkidle")
    page.locator(".relationship-row").click()
    page.locator(".relationship-transcript .message-bubble").last.wait_for()
    selectors = [".app-shell", ".app-shell__stage", ".app-shell__workspace",
                 ".relationships-page", ".relationships-inbox",
                 ".relationship-conversation", ".customer-intelligence-stack",
                 ".relationship-transcript"]
    measured = {selector: metrics(page, selector) for selector in selectors}
    transcript = page.locator(".relationship-transcript")
    inline_projection = metrics(page, ".customer-intelligence-stack")
    before = transcript.evaluate("node => node.scrollTop")
    transcript.evaluate("node => { node.scrollTop = 120; }")
    after = transcript.evaluate("node => node.scrollTop")
    page.get_by_role("button", name="Open Customer Intelligence").click()
    drawer = page.locator(".customer-intelligence-drawer")
    drawer.wait_for()
    expanded_transcript = metrics(page, ".relationship-transcript")
    expanded_details = metrics(page, ".customer-intelligence-stack")
    assert measured[".relationship-transcript"]["clientHeight"] >= 180, measured
    assert measured[".relationship-transcript"]["scrollHeight"] > measured[".relationship-transcript"]["clientHeight"], measured
    assert after != before, (before, after, measured)
    assert inline_projection["display"] == "none", inline_projection
    assert expanded_transcript["clientHeight"] == measured[".relationship-transcript"]["clientHeight"], expanded_transcript
    assert expanded_details["clientHeight"] > 0
    assert expanded_details["overflowY"] == "auto", expanded_details
    assert page.get_by_role("button", name="Load older messages").is_visible()
    assert page.get_by_text("Automatic Value").is_visible()
    assert page.get_by_text("Daily Reply Budget").is_visible()
    page.get_by_role("button", name="Close Customer Intelligence").click()
    assert transcript.evaluate("node => node.scrollTop") == after
    print(json.dumps({"viewport": [1024, 600], "collapsed": measured,
                      "inlineProjection": inline_projection, "scrollTop": [before, after], "expandedTranscript": expanded_transcript,
                      "expandedIntelligence": expanded_details}, indent=2))
    browser.close()
