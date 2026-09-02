"""PostgreSQL certification for the isolated Session 5 scenario harness."""
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness, SimulatedProviderPurchaseHarness,
    HistoricalPurchaseFixtureBuilder,
    SCENARIO_MANIFEST, ScenarioState, PROTECTED_LIVE_TELEGRAM_ID,
    SYNTHETIC_ID_MIN, PROVENANCE, DETERMINISTIC_CERTIFICATION,
    ScenarioTurnExecutionIdentity,
)
from app.testing.postgres_safety import Session5DatabasePurpose
from app.testing.session5_scenario_runner import Session5ScenarioRunner


pytestmark = pytest.mark.skipif(
    not os.getenv("SESSION5_INTEGRATION_DATABASE_URL"),
    reason="SESSION5_INTEGRATION_DATABASE_URL required",
)


@pytest.fixture
def harness():
    service=CustomerScenarioHarness(
        certification_mode=True,
        database_purpose=Session5DatabasePurpose.AUTOMATED_INTEGRATION,
    )
    # Deterministic scenarios are reusable across test runs. Exercise the same
    # guarded reset before rebuilding any residue from an interrupted run.
    with service.connection() as c:
        existing=[row["scenario_id"] for row in c.execute(
            "SELECT scenario_id FROM certification_scenario_runs"
        ).fetchall()]
        c.execute("UPDATE certification_scenario_runs SET state='SNAPSHOTTED'")
    for scenario_id in existing:
        service.reset(scenario_id)
    with service.connection() as c:
        synthetic_ids=(SYNTHETIC_ID_MIN+11,SYNTHETIC_ID_MIN+12,SYNTHETIC_ID_MIN+13)
        c.execute("""DELETE FROM telegram_identity_verification_audit WHERE telegram_user_id=ANY(%s)""",(list(synthetic_ids),))
        synthetic_buyers=[CustomerScenarioHarness.customer_for(CustomerScenarioHarness.definition(f"C{i:02d}")).synthetic_buyer_uuid for i in (11,12,13)]
        c.execute("DELETE FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=ANY(%s)",(synthetic_buyers,))
        c.execute("""DELETE FROM fanvue_runtime_media_links WHERE purchase_intent_id IN
            (SELECT purchase_intent_id FROM purchase_intents WHERE telegram_user_id=ANY(%s))""",(list(synthetic_ids),))
        c.execute("""DELETE FROM fanvue_fingerprint_reservations WHERE purchase_intent_id IN
            (SELECT purchase_intent_id FROM purchase_intents WHERE telegram_user_id=ANY(%s))""",(list(synthetic_ids),))
        c.execute("DELETE FROM purchase_intents WHERE telegram_user_id=ANY(%s)",(list(synthetic_ids),))
        c.execute("DELETE FROM telegram_sales_prospects WHERE telegram_user_id=ANY(%s)",(list(synthetic_ids),))
        c.execute("DELETE FROM telegram_identity_map WHERE telegram_user_id=ANY(%s)",(list(synthetic_ids),))
        c.execute("DELETE FROM telegram_identity_observations WHERE telegram_user_id=ANY(%s)",(list(synthetic_ids),))
        c.execute("DELETE FROM certification_scenario_records")
        c.execute("DELETE FROM certification_simulated_provider_events")
        c.execute("DELETE FROM certification_scenario_runs")
        c.execute("DELETE FROM certification_scenario_snapshots")
    return service


def test_manifest_has_deterministic_independent_20_customer_roster():
    assert [item.scenario_id for item in SCENARIO_MANIFEST]==[f"C{i:02d}" for i in range(1,21)]
    assert len({CustomerScenarioHarness.customer_for(item).telegram_user_id for item in SCENARIO_MANIFEST})==20
    assert all(CustomerScenarioHarness.customer_for(item).telegram_user_id>=SYNTHETIC_ID_MIN for item in SCENARIO_MANIFEST)
    fresh=[item for item in SCENARIO_MANIFEST if item.name in {"FRESH_SWEET_PROSPECT","FRESH_RUDE_PROSPECT"}]
    assert fresh[0].economic_state==fresh[1].economic_state
    assert fresh[0].behavior_profile!=fresh[1].behavior_profile


def test_terminal_history_does_not_own_execution_slot_or_get_overwritten(harness):
    runner = Session5ScenarioRunner(harness=harness)
    runner.prepare("C05")
    first = runner.turn("You seem sweet", language_mode=DETERMINISTIC_CERTIFICATION)
    runner.complete("FAIL")

    with harness.connection() as connection:
        c05_before = connection.execute(
            "SELECT state,scenario_attempt FROM certification_scenario_runs WHERE scenario_id='C05'"
        ).fetchone()
        turns_before = connection.execute(
            """SELECT scenario_attempt,logical_turn,inbound,outbound,full_analysis
               FROM certification_scenario_turn_attempts WHERE scenario_id='C05'
               ORDER BY scenario_attempt,logical_turn,turn_attempt"""
        ).fetchall()
        grade_before = connection.execute(
            "SELECT grade,completed_at FROM certification_scenario_assessments WHERE scenario_id='C05'"
        ).fetchone()

    prepared = runner.prepare("C01")
    assert prepared["scenario"] == "C01"
    assert runner.full_attempt_analysis("C05")["turns"][0]["ava"] == first["ava"]

    with harness.connection() as connection:
        c05_after = connection.execute(
            "SELECT state,scenario_attempt FROM certification_scenario_runs WHERE scenario_id='C05'"
        ).fetchone()
        turns_after = connection.execute(
            """SELECT scenario_attempt,logical_turn,inbound,outbound,full_analysis
               FROM certification_scenario_turn_attempts WHERE scenario_id='C05'
               ORDER BY scenario_attempt,logical_turn,turn_attempt"""
        ).fetchall()
        grade_after = connection.execute(
            "SELECT grade,completed_at FROM certification_scenario_assessments WHERE scenario_id='C05'"
        ).fetchone()
    assert dict(c05_after) == dict(c05_before)
    assert [dict(row) for row in turns_after] == [dict(row) for row in turns_before]
    assert dict(grade_after) == dict(grade_before)

    runner.complete("PASS")
    future = runner.prepare("C05")
    assert future["scenarioAttempt"] == int(c05_before["scenario_attempt"]) + 1
    history = runner.recovery.historical_attempt_history(
        "C05", exclude_attempt=future["scenarioAttempt"],
    )
    assert any(
        int(row["scenario_attempt"]) == int(c05_before["scenario_attempt"])
        for row in history["turnAttempts"]
    )


def test_running_scenario_still_exclusively_owns_execution_slot(harness):
    runner = Session5ScenarioRunner(harness=harness)
    runner.prepare("C01")
    with pytest.raises(RuntimeError, match="Active scenario C01"):
        runner.prepare("C02")


@pytest.mark.parametrize("scenario_id", ("C02", "C03", "C20"))
def test_central_fixture_bootstrap_resolves_complete_reusable_creator_graph(
    harness, scenario_id,
):
    harness.prepare(scenario_id)
    builder = HistoricalPurchaseFixtureBuilder(harness)
    first = builder._ensure_customer(scenario_id)
    with harness.connection() as connection:
        graph = connection.execute("""SELECT 1
            FROM telegram_sales_prospects prospect
            JOIN creator_profiles profile ON profile.id=prospect.creator_profile_id
            JOIN fanvue_accounts account ON account.id=prospect.fanvue_account_id
            JOIN fanvue_users usr ON usr.fanvue_account_id=account.id
              AND usr.fanvue_user_uuid=%s
            WHERE prospect.telegram_user_id=%s
              AND profile.fanvue_account_id::text=account.id::text""", (
                harness.customer_for(harness.definition(scenario_id)).synthetic_buyer_uuid,
                first["telegram_user_id"],
            )).fetchone()
        assert graph is not None
        connection.execute(
            "DELETE FROM telegram_sales_prospects WHERE telegram_user_id=%s",
            (first["telegram_user_id"],),
        )
    second = builder._ensure_customer(scenario_id)
    assert second["creator_profile_id"] == first["creator_profile_id"]
    assert second["fanvue_account_id"] == first["fanvue_account_id"]
    assert second["fanvue_user_id"] == first["fanvue_user_id"]


def test_scenario_fixture_keeps_creator_profile_foreign_key_enforced(harness):
    harness.prepare("C02")
    customer = harness.customer_for(harness.definition("C02"))
    with pytest.raises(Exception) as raised:
        with harness.connection() as connection:
            connection.execute("""INSERT INTO telegram_sales_prospects(
                telegram_sales_prospect_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id)
                VALUES (%s,-1,-1,%s,%s)""", (
                    uuid4(), customer.telegram_user_id, customer.telegram_chat_id,
                ))
    assert "telegram_sales_prospects_creator_profile_id_fkey" in str(raised.value)


def test_failed_gateway_turn_does_not_advance_behavior_or_inbound_operation(
    harness, monkeypatch,
):
    from app.services.conversation_gateway import ConversationGateway

    runner = Session5ScenarioRunner(harness=harness)
    runner.prepare("C02")
    customer = harness.customer_for(harness.definition("C02"))
    monkeypatch.setattr(
        ConversationGateway, "execute",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced gateway failure")),
    )
    with pytest.raises(RuntimeError, match="forced gateway failure"):
        runner.turn("yeah, pretty much", language_mode=DETERMINISTIC_CERTIFICATION)

    assert harness.behavior_summary("C02")["inbound_message_count"] == 0
    with harness.connection() as connection:
        operation_count = connection.execute("""SELECT COUNT(*) AS count
            FROM ordinary_chat_reply_operations
            WHERE inbound_sender_telegram_user_id=%s""", (
                customer.telegram_user_id,
            )).fetchone()["count"]
        evidence_count = connection.execute("""SELECT COUNT(*) AS count
            FROM certification_scenario_turn_evidence WHERE scenario_id='C02'""").fetchone()["count"]
        completed_turn_count = connection.execute("""SELECT COUNT(*) AS count
            FROM certification_scenario_turn_attempts
            WHERE scenario_id='C02' AND scenario_attempt=(
                SELECT scenario_attempt FROM certification_scenario_runs
                WHERE scenario_id='C02'
            )""").fetchone()["count"]
    assert operation_count == 0
    assert evidence_count == 0
    assert completed_turn_count == 0
    assert runner.recovery.next_logical_turn(
        "C02", runner.recovery.scenario_attempt("C02")
    ) == 1


def test_successful_turn_has_one_exact_rich_evidence_match(harness):
    runner = Session5ScenarioRunner(harness=harness)
    runner.prepare("C02")
    runner.turn("not much, just taking it easy", language_mode=DETERMINISTIC_CERTIFICATION)
    analysis = runner.full_attempt_analysis("C02")
    assert analysis["scenario"]["canonicalTurnCount"] == 1
    assert analysis["currentAccumulatedState"]["inboundMessageCount"] == 1
    assert analysis["turns"][0]["evidenceStatus"] == "MATCHED"


def test_seven_turns_have_distinct_attempt_scoped_immutable_rich_evidence(harness):
    runner = Session5ScenarioRunner(harness=harness)
    prepared = runner.prepare("C02")
    messages = (
        "hey, how's it going?",
        "not too bad, just taking it easy",
        "yeah, pretty much",
        "work was okay, nothing exciting really",
        "mostly just relaxing tonight",
        "I'm still here, just kinda quiet",
        "yeah, I don't have much else going on",
    )
    first = runner.turn(messages[0], language_mode=DETERMINISTIC_CERTIFICATION)
    first_before = runner.full_attempt_analysis("C02")["turns"][0]
    for message in messages[1:]:
        runner.turn(message, language_mode=DETERMINISTIC_CERTIFICATION)

    analysis = runner.full_attempt_analysis("C02")
    assert analysis["scenario"]["canonicalTurnCount"] == 7
    assert analysis["currentAccumulatedState"]["inboundMessageCount"] == 7
    assert all(turn["evidenceStatus"] == "MATCHED" for turn in analysis["turns"])
    assert analysis["turns"][0]["salesBrainFullAnalysis"] == first_before["salesBrainFullAnalysis"]
    with harness.connection() as connection:
        rows = connection.execute("""SELECT correlation_id,full_analysis
            FROM certification_scenario_turn_evidence
            WHERE scenario_id='C02' ORDER BY created_at""").fetchall()
    identities = [dict(row["full_analysis"])["scenarioTurnIdentity"] for row in rows]
    assert len(rows) == len({row["correlation_id"] for row in rows}) == 7
    assert [item["logicalTurn"] for item in identities] == list(range(1, 8))
    assert {item["scenarioAttempt"] for item in identities} == {
        prepared["scenarioAttempt"]
    }
    assert first["turnNumber"] == 1


def test_exact_turn_identity_is_idempotent_and_collision_is_rejected(harness):
    from app.testing.session5_scenario_harness import ScenarioTurnExecutionIdentity

    harness.prepare("C02")
    identity = ScenarioTurnExecutionIdentity("C02", 1, 1)
    first = harness.execute_turn(
        "C02", "yeah, pretty much", provider_draft="fair enough",
        turn_identity=identity,
    )
    same = harness.execute_turn(
        "C02", "yeah, pretty much", provider_draft="this must not be generated",
        turn_identity=identity,
    )
    assert json.loads(json.dumps(same, default=str)) == json.loads(
        json.dumps(first, default=str)
    )
    with pytest.raises(RuntimeError, match="SCENARIO_TURN_IDENTITY_COLLISION"):
        harness.execute_turn(
            "C02", "different inbound", provider_draft="must not overwrite",
            turn_identity=identity,
        )
    with harness.connection() as connection:
        rows = connection.execute("""SELECT inbound,outbound,full_analysis
            FROM certification_scenario_turn_evidence WHERE correlation_id=%s""", (
                identity.correlation_id,
            )).fetchall()
    assert len(rows) == 1
    assert rows[0]["inbound"] == "yeah, pretty much"
    assert dict(rows[0]["full_analysis"])["scenarioTurnIdentity"] == identity.to_mapping()


def test_prepare_snapshot_reset_lifecycle_and_snapshot_survival(harness):
    customer=harness.prepare("C01")
    assert customer.state is ScenarioState.READY
    harness.transition("C01",ScenarioState.RUNNING)
    harness.transition("C01",ScenarioState.COMPLETED)
    snapshot=harness.snapshot("C01",{
        "turnTranscript":[],"fullAnalysis":[],"grades":{
            "systemLogic":"PASS","avaBehavior":"PASS","commercialTrajectory":"PASS"},
    })
    result=harness.reset("C01")
    assert result["state"]=="VERIFIED_CLEAN"
    with harness.connection() as c:
        assert c.execute("SELECT COUNT(*) n FROM certification_scenario_snapshots WHERE snapshot_id=%s",(snapshot,)).fetchone()["n"]==1
        assert c.execute("SELECT state FROM certification_scenario_runs WHERE scenario_id='C01'").fetchone()["state"]=="VERIFIED_CLEAN"


def test_reset_refuses_before_snapshot(harness):
    harness.prepare("C02")
    with pytest.raises(ValueError,match="Snapshot"):
        harness.reset("C02")


def test_live_controlled_identity_and_non_synthetic_identity_are_rejected():
    with pytest.raises(PermissionError): CustomerScenarioHarness._assert_synthetic(PROTECTED_LIVE_TELEGRAM_ID)
    with pytest.raises(PermissionError): CustomerScenarioHarness._assert_synthetic(123)


def test_certification_mode_defaults_fail_closed(monkeypatch):
    monkeypatch.delenv("CREATOR_OS_CERTIFICATION_SCENARIO_MODE",raising=False)
    with pytest.raises(PermissionError,match="certification"):
        CustomerScenarioHarness(
            database_purpose=Session5DatabasePurpose.AUTOMATED_INTEGRATION,
        )


@pytest.mark.parametrize("target",[
    ScenarioState.COMPLETED,ScenarioState.SNAPSHOTTED,
    ScenarioState.RESET,ScenarioState.VERIFIED_CLEAN,
])
def test_lifecycle_cannot_skip_states(harness,target):
    harness.prepare("C03")
    with pytest.raises(ValueError,match="Invalid"):
        harness.transition("C03",target)


def test_simulated_provider_event_requires_existing_scenario_intent(harness):
    harness.prepare("C04")
    emulator=SimulatedProviderPurchaseHarness(harness,settlement_factory=lambda:None)
    with pytest.raises(PermissionError,match="PurchaseIntent"):
        emulator.confirm(scenario_id="C04",purchase_intent_id=uuid4(),amount_minor=300,currency="USD")


def test_provenance_is_unmistakably_simulated():
    assert PROVENANCE=="CERTIFICATION_SIMULATED_PROVIDER_EVENT"


def test_scenario_a_cannot_leak_into_scenario_b(harness):
    a=harness.prepare("C05"); b=harness.prepare("C06")
    assert a.telegram_user_id!=b.telegram_user_id
    assert a.synthetic_buyer_uuid!=b.synthetic_buyer_uuid
    with harness.connection() as c:
        rows=c.execute("SELECT scenario_id,telegram_user_id,buyer_uuid FROM certification_scenario_runs ORDER BY scenario_id").fetchall()
    assert {(row["scenario_id"],row["telegram_user_id"]) for row in rows}=={("C05",a.telegram_user_id),("C06",b.telegram_user_id)}


def test_production_database_target_is_rejected(monkeypatch):
    production=os.getenv("DATABASE_URL")
    if not production: pytest.fail("DATABASE_URL required for production-boundary certification")
    with pytest.raises(ValueError):
        CustomerScenarioHarness(test_database_url=production,
                                production_database_url=production,
                                certification_mode=True,
                                database_purpose=Session5DatabasePurpose.AUTOMATED_INTEGRATION)


def _commerce_fixture(harness, scenario_id="C11", price=1497):
    customer=harness.prepare(scenario_id)
    offering_id,publication_id,intent_id,reservation_id,runtime_id=[uuid4() for _ in range(5)]
    with harness.connection() as c:
        account=c.execute("INSERT INTO fanvue_accounts(account_name) VALUES (%s) RETURNING id",(f"Certification {uuid4()}",)).fetchone()["id"]
        user=c.execute("""INSERT INTO fanvue_users(fanvue_user_uuid,fanvue_account_id,username,display_name)
            VALUES (%s,%s,%s,'Certification Buyer') RETURNING id""",(customer.synthetic_buyer_uuid,account,f"cert_{scenario_id.lower()}_{uuid4().hex[:8]}")).fetchone()["id"]
        creator=c.execute("""INSERT INTO creator_profiles(fanvue_account_id,persona_name,display_name,age,gender,location)
            VALUES (%s,'Certification Ava','Certification Ava',25,'female','test') RETURNING id""",(str(account),)).fetchone()["id"]
        asset=c.execute("INSERT INTO content_items(file_path,classification) VALUES (%s,'SAFE') RETURNING id",(f"certification/{uuid4()}.jpg",)).fetchone()["id"]
        c.execute("""INSERT INTO commercial_offerings(offering_id,creator_profile_id,offering_type,title,
            hero_asset_id,primary_sales_channel,status,price_minor,currency)
            VALUES (%s,%s,'SINGLE_IMAGE','Certification Single',%s,'AI_CHAT','READY',%s,'USD')""",(offering_id,creator,asset,price))
        c.execute("""INSERT INTO commercial_publications(publication_id,commercial_offering_id,provider,status,
            external_product_id,provider_resource_status,publication_metadata)
            VALUES (%s,%s,'FANVUE','LIVE','certification','PRESENT','{}')""",(publication_id,offering_id))
        c.execute("INSERT INTO commercial_offering_assets(offering_id,asset_id,position) VALUES (%s,%s,1)",(offering_id,asset))
        observation=c.execute("INSERT INTO telegram_identity_observations(telegram_user_id,telegram_chat_id) VALUES (%s,%s) RETURNING telegram_user_id",(customer.telegram_user_id,customer.telegram_chat_id)).fetchone()["telegram_user_id"]
        prospect=c.execute("""INSERT INTO telegram_sales_prospects(telegram_sales_prospect_id,creator_profile_id,
            fanvue_account_id,telegram_user_id,telegram_chat_id,relationship_state,preference_state)
            VALUES (%s,%s,%s,%s,%s,'{}','{}') RETURNING telegram_sales_prospect_id""",(uuid4(),creator,account,customer.telegram_user_id,customer.telegram_chat_id)).fetchone()["telegram_sales_prospect_id"]
        c.execute("""INSERT INTO purchase_intents(purchase_intent_id,creator_profile_id,fanvue_account_id,
            telegram_user_id,telegram_chat_id,commercial_offering_id,commercial_publication_id,provider,
            provider_resource_id,delivery_url,correlation_id,expected_price_minor,configured_base_price_minor,
            expected_currency,expires_at,identity_bootstrap_mode)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'FANVUE','runtime','https://example.invalid/certification',
            %s,%s,%s,'USD',%s,'PRIVATE_CHAT_FINGERPRINT')""",(intent_id,creator,account,customer.telegram_user_id,
            customer.telegram_chat_id,offering_id,publication_id,uuid4(),price,price,
            datetime.now(timezone.utc)+timedelta(days=1)))
        c.execute("""INSERT INTO fanvue_fingerprint_reservations(fingerprint_reservation_id,fanvue_account_id,
            currency,exact_price_minor,configured_base_price_minor,purchase_intent_id,telegram_user_id,state)
            VALUES (%s,%s,'USD',%s,%s,%s,%s,'ACTIVE')""",(reservation_id,account,price,price,intent_id,customer.telegram_user_id))
        c.execute("""INSERT INTO fanvue_runtime_media_links(runtime_media_link_id,purchase_intent_id,
            fingerprint_reservation_id,provider_media_link_uuid,provider_url,state,creation_operation_key,expires_at)
            VALUES (%s,%s,%s,%s,'https://example.invalid/certification','ACTIVE',%s,%s)""",(runtime_id,intent_id,
            reservation_id,str(uuid4()),uuid4(),datetime.now(timezone.utc)+timedelta(days=1)))
    for table,record in (("telegram_identity_observations",observation),("telegram_sales_prospects",prospect),
        ("purchase_intents",intent_id),("fanvue_fingerprint_reservations",reservation_id),
        ("fanvue_runtime_media_links",runtime_id)):
        harness.record_fixture(scenario_id,table,record)
    return locals()


def test_simulated_event_settles_existing_intent_through_canonical_service(harness):
    values=_commerce_fixture(harness)
    emulator=SimulatedProviderPurchaseHarness(harness)
    transaction_id=f"cert-{uuid4()}"
    result=emulator.confirm(scenario_id="C11",purchase_intent_id=values["intent_id"],
                            amount_minor=1497,currency="USD",transaction_id=transaction_id)
    assert result["simulated"] is True and result["provenance"]==PROVENANCE
    assert result["settlement"] is not None
    assert result["transactionRecorded"] is True
    assert result["commerceProfile"].purchase_count==1
    assert result["commerceProfile"].lifetime_gross_minor==1497
    with harness.connection() as c:
        intent=c.execute("SELECT status,attribution_result FROM purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone()
        mapping=c.execute("SELECT COUNT(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",(values["customer"].telegram_user_id,)).fetchone()["n"]
        ownership=c.execute("SELECT COUNT(*) n FROM provider_purchase_asset_ownership WHERE provider_transaction_id=%s",(result["settlement"]["intent"]["provider_transaction_order_id"],)).fetchone()["n"]
    assert intent=={"status":"PURCHASED","attribution_result":"ATTRIBUTED"}
    assert mapping==ownership==1
    duplicate=emulator.confirm(scenario_id="C11",purchase_intent_id=values["intent_id"],
                               amount_minor=1497,currency="USD",transaction_id=transaction_id)
    assert duplicate["settlement"] is not None
    assert duplicate["transactionRecorded"] is False
    assert duplicate["commerceProfile"].purchase_count==1
    harness.transition("C11",ScenarioState.RUNNING)
    harness.transition("C11",ScenarioState.COMPLETED)
    snapshot=harness.snapshot("C11",{"purchaseIntentId":str(values["intent_id"]),"providerEvent":result["eventId"]})
    reset=harness.reset("C11")
    assert reset["state"]=="VERIFIED_CLEAN"
    with harness.connection() as c:
        assert c.execute("SELECT COUNT(*) n FROM purchase_intents WHERE telegram_user_id=%s",(values["customer"].telegram_user_id,)).fetchone()["n"]==0
        assert c.execute("SELECT COUNT(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",(values["customer"].telegram_user_id,)).fetchone()["n"]==0
        assert c.execute("SELECT COUNT(*) n FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s",(values["customer"].synthetic_buyer_uuid,)).fetchone()["n"]==0
        assert c.execute("SELECT COUNT(*) n FROM customer_commerce_profiles WHERE external_fanvue_user_uuid=%s",(values["customer"].synthetic_buyer_uuid,)).fetchone()["n"]==0
        assert c.execute("SELECT COUNT(*) n FROM certification_scenario_snapshots WHERE snapshot_id=%s",(snapshot,)).fetchone()["n"]==1


@pytest.mark.parametrize("amount,currency,scenario",[(999,"USD","C12"),(1497,"EUR","C13")])
def test_simulated_wrong_amount_or_currency_fails_closed(harness,amount,currency,scenario):
    values=_commerce_fixture(harness,scenario_id=scenario)
    result=SimulatedProviderPurchaseHarness(harness).confirm(
        scenario_id=scenario,purchase_intent_id=values["intent_id"],amount_minor=amount,
        currency=currency,transaction_id=f"bad-{uuid4()}")
    assert result["settlement"] is None
    with harness.connection() as c:
        state=c.execute("SELECT status FROM purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone()["status"]
    assert state=="CREATED"


@pytest.mark.parametrize("scenario,purchases,expected_stage,expected_tier",[
    ("C13",[1200,1800],"REPEAT_BUYER","REPEAT_BUYER"),
    ("C15",[5000,5001,5002],"HIGH_VALUE_BUYER","HIGH_VALUE"),
    ("C16",[10000,10001,10002,10003,10004],"HIGH_VALUE_BUYER","WHALE"),
])
def test_historical_multi_purchase_derives_repeat_high_value_and_whale(
    harness,scenario,purchases,expected_stage,expected_tier,
):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    built=builder.build(scenario,[{"amount_minor":value} for value in purchases])
    state=built["derived"]
    assert state["purchaseCount"]==len(purchases)
    assert state["lifetimeSpendMinor"]==sum(purchases)
    assert state["ownershipCount"]==len(purchases)
    assert state["buyerStatus"]=="VERIFIED_BUYER"
    assert state["buyerStage"]==expected_stage
    assert state["valueTier"]==expected_tier
    assert state["retentionLifecycle"]=="ACTIVE_BUYER"
    assert state["effortMode"]=="FULL"
    harness.transition(scenario,ScenarioState.RUNNING)
    harness.transition(scenario,ScenarioState.COMPLETED)
    snapshot=harness.snapshot(scenario,{"derived":state})
    harness.reset(scenario)
    with harness.connection() as c:
        assert c.execute("SELECT COUNT(*) n FROM certification_scenario_snapshots WHERE snapshot_id=%s",(snapshot,)).fetchone()["n"]==1
        assert c.execute("SELECT COUNT(*) n FROM purchase_intents WHERE telegram_user_id=%s",(state["telegramId"],)).fetchone()["n"]==0


@pytest.mark.parametrize("scenario,age_days,behavior,expected_lifecycle,expected_effort",[
    ("C12",1,{"inbound_message_count":5,"commercial_movement":True},"ACTIVE_BUYER","BALANCED"),
    ("C14",45,{"inbound_message_count":18,"offer_exposure_count":4,"rejection_count":4},"COOLING_BUYER","COMPRESSED"),
    ("C18",140,{"inbound_message_count":2},"DORMANT_BUYER","BALANCED"),
])
def test_buyer_lifecycle_is_derived_from_purchase_recency_and_behavior(
    harness,scenario,age_days,behavior,expected_lifecycle,expected_effort,
):
    now=datetime.now(timezone.utc)
    builder=HistoricalPurchaseFixtureBuilder(harness)
    builder.build(scenario,[{"amount_minor":1300,"purchased_at":now-timedelta(days=age_days)}])
    events=[{"type":"INBOUND","message":f"turn {index}"} for index in range(behavior.get("inbound_message_count",0))]
    events += [{"type":"OFFER_EXPOSURE","message":"canonical offer"} for _ in range(behavior.get("offer_exposure_count",0))]
    events += [{"type":"REJECTION","message":"no thanks"} for _ in range(behavior.get("rejection_count",0))]
    if behavior.get("commercial_movement") and events:
        events[-1]["evidence"]={"commercial_movement":True}
    harness.record_behavior_history(scenario,events)
    state=builder.derived_state(scenario,now=now)
    assert state["buyerStatus"]=="VERIFIED_BUYER"
    assert state["buyerStage"]=="FIRST_TIME_BUYER"
    assert state["retentionLifecycle"]==expected_lifecycle
    assert state["effortMode"]==expected_effort


def test_nonbuying_whale_retains_economic_truth_and_buyer_protection(harness):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    builder.build("C17",[{"amount_minor":value} for value in (10000,10001,10002,10003,10004)])
    events=[{"type":"INBOUND","message":f"noncommercial {i}"} for i in range(30)]
    events += [{"type":"OFFER_EXPOSURE","message":"offer"} for _ in range(5)]
    events += [{"type":"REJECTION","message":"not now","evidence":{"back_off":True}} for _ in range(5)]
    harness.record_behavior_history("C17",events)
    state=builder.derived_state("C17")
    assert state["valueTier"]=="WHALE"
    assert state["buyerProtectionApplied"] is True
    assert state["timeWasterRisk"]=="NONE"
    assert state["effortMode"]!="MINIMAL"
    assert state["commercialMomentum"]=="COOLING"


@pytest.mark.parametrize("scenario,behavior,expected_risk,expected_effort",[
    ("C07",{"inbound_message_count":20,"offer_exposure_count":2,"commercial_movement":True},"NONE","BALANCED"),
    ("C08",{"inbound_message_count":24,"offer_exposure_count":4,"rejection_count":4},"HIGH","MINIMAL"),
    ("C09",{"inbound_message_count":24,"offer_exposure_count":3,"sexual_engagement_only":True},"HIGH","MINIMAL"),
])
def test_nonbuyer_attention_is_derived_from_coherent_behavior_evidence(
    harness,scenario,behavior,expected_risk,expected_effort,
):
    harness.prepare(scenario)
    events=[{"type":"INBOUND","message":f"turn {i}","evidence":{
        "commercial_movement": bool(behavior.get("commercial_movement")),
        "sexual_engagement": bool(behavior.get("sexual_engagement_only")),
    }} for i in range(behavior.get("inbound_message_count",0))]
    events += [{"type":"OFFER_EXPOSURE","message":"legitimate offer"} for _ in range(behavior.get("offer_exposure_count",0))]
    events += [{"type":"REJECTION","message":"avoidance"} for _ in range(behavior.get("rejection_count",0))]
    harness.record_behavior_history(scenario,events)
    state=HistoricalPurchaseFixtureBuilder(harness).derived_state(scenario)
    assert state["purchaseCount"]==0
    assert state["buyerStatus"]=="NONBUYER"
    assert state["timeWasterRisk"]==expected_risk
    assert state["effortMode"]==expected_effort


def test_c19_session_purchase_creates_reconstructable_active_canonical_session(harness):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    built=builder.build("C19",[{"amount_minor":2200}],session=True)
    state=built["derived"]
    assert state["activeSession"] is not None
    assert state["activeSession"]["state"]=="CONTINUING"
    purchase=built["purchases"][0]
    from app.repositories.sales_session_repository import SalesSessionRepository
    reconstructed=SalesSessionRepository(
        connection_factory=harness.connection
    ).get_active_for_customer(
        creator_profile_id=built["customer"]["creator_profile_id"],
        fanvue_account_id=built["customer"]["fanvue_account_id"],
        fanvue_user_id=built["customer"]["fanvue_user_id"],
    )
    assert reconstructed is not None
    from app.services.sales_session_service import SalesSessionService
    service=SalesSessionService(
        repository=SalesSessionRepository(connection_factory=harness.connection),
        customer_safety_service=type("Safe",(),{"decide":lambda self,**kwargs:type("D",(),{"allowed":True})()})(),
    )
    via_service=service.get(session_id=reconstructed.sales_session_id,
                            creator_profile_id=built["customer"]["creator_profile_id"])
    assert via_service.state.value=="CONTINUING"
    with harness.connection() as c:
        link=c.execute("SELECT COUNT(*) n FROM sales_session_purchase_intents WHERE purchase_intent_id=%s",(purchase["purchase_intent_id"],)).fetchone()["n"]
    assert link==1
    turn=harness.execute_turn("C19","What comes next?",provider_draft="I know exactly what comes next.")
    active=turn["SalesBrainFullAnalysis"]["activeSession"]
    assert active["active"] is True
    assert active["sessionId"]==str(reconstructed.sales_session_id)
    assert active["state"]=="CONTINUING"
    assert active["authority"]=="SALES_SESSION"
    assert active["genericSelectorOverride"] is False
    assert turn["avaPersonaRuntime"]["canonical_authority"]=="ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE"
    assert turn["SalesBrainFullAnalysis"]["customerValueAttention"]
    harness.transition("C19",ScenarioState.RUNNING); harness.transition("C19",ScenarioState.COMPLETED)
    harness.snapshot("C19",{"derived":state}); harness.reset("C19")
    assert builder.derived_state("C19")["activeSession"] is None


def test_purchase_acknowledgement_is_eligible_and_confirmed_exactly_once(harness):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    built=builder.build("C11",[{"amount_minor":1400}])
    purchase=built["purchases"][0]; base=built["customer"]
    with harness.connection() as c:
        intent=c.execute("SELECT purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s",(purchase["purchase_intent_id"],)).fetchone()
        assert intent["purchase_acknowledged_at"] is None
        thread=c.execute("""INSERT INTO chat_threads(fanvue_account_id,fanvue_user_id,fanvue_chat_uuid,thread_status)
            VALUES (%s,%s,%s,'active') RETURNING id""",(base["fanvue_account_id"],base["fanvue_user_id"],str(uuid4()))).fetchone()["id"]
    from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository
    repo=TelegramSalesDeliveryRepository(connection_factory=harness.connection)
    operation,_=repo.get_or_create(
        correlation_id=str(uuid4()),creator_profile_id=base["creator_profile_id"],
        fanvue_account_id=base["fanvue_account_id"],conversation_thread_id=thread,
        fanvue_user_id=base["fanvue_user_id"],telegram_chat_id=base["telegram_chat_id"],
        inbound_telegram_message_id=990001,purchase_intent_id=purchase["purchase_intent_id"],
        commercial_offering_id=purchase["offering_id"],
        commercial_publication_id=uuid5(NAMESPACE_URL,"publication:C11:1"),
        response_text="Thanks for unlocking it.",delivery_payload={
            "metadata":{"message_purpose":"PURCHASE_ACKNOWLEDGEMENT"}},
    )
    claimed=repo.claim_created(operation.operation_id)
    accepted=repo.mark_accepted(claimed.operation_id,990002)
    first=repo.confirm_purchase_acknowledgement(accepted.operation_id)
    with harness.connection() as c:
        timestamp=c.execute("SELECT purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s",(purchase["purchase_intent_id"],)).fetchone()["purchase_acknowledged_at"]
    second=repo.confirm_purchase_acknowledgement(first.operation_id)
    duplicate_operation,created=repo.get_or_create(
        correlation_id=operation.correlation_id,creator_profile_id=base["creator_profile_id"],
        fanvue_account_id=base["fanvue_account_id"],conversation_thread_id=thread,
        fanvue_user_id=base["fanvue_user_id"],telegram_chat_id=base["telegram_chat_id"],
        inbound_telegram_message_id=990001,purchase_intent_id=purchase["purchase_intent_id"],
        commercial_offering_id=purchase["offering_id"],
        commercial_publication_id=uuid5(NAMESPACE_URL,"publication:C11:1"),
        response_text="Thanks for unlocking it.",delivery_payload={
            "metadata":{"message_purpose":"PURCHASE_ACKNOWLEDGEMENT"}},
    )
    with harness.connection() as c:
        after=c.execute("SELECT purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s",(purchase["purchase_intent_id"],)).fetchone()["purchase_acknowledged_at"]
        count=c.execute("SELECT COUNT(*) n FROM telegram_sales_delivery_operations WHERE purchase_intent_id=%s AND delivery_payload->'metadata'->>'message_purpose'='PURCHASE_ACKNOWLEDGEMENT'",(purchase["purchase_intent_id"],)).fetchone()["n"]
    assert created is False and duplicate_operation.operation_id==operation.operation_id
    assert second.state.value=="CONFIRMED" and timestamp==after and count==1


def test_false_purchase_claim_remains_nonbuyer_until_provider_truth(harness):
    values=_commerce_fixture(harness,scenario_id="C04",price=300)
    claim_turn=harness.execute_turn("C04","I bought it",provider_draft="I hear you.")
    claim_truth=claim_turn["SalesBrainFullAnalysis"]["purchaseCommerceState"]
    assert claim_truth["conversationalPurchaseClaim"] is True
    assert claim_truth["verifiedPurchase"] is False
    assert claim_truth["purchaseAcknowledgementPending"] is False
    before=HistoricalPurchaseFixtureBuilder(harness).derived_state("C04")
    with harness.connection() as c:
        ownership_before=c.execute("SELECT COUNT(*) n FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s",(values["customer"].synthetic_buyer_uuid,)).fetchone()["n"]
        ack_before=c.execute("SELECT purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone()["purchase_acknowledged_at"]
    assert before["buyerStatus"]=="NONBUYER" and ownership_before==0 and ack_before is None
    settled=SimulatedProviderPurchaseHarness(harness).confirm(
        scenario_id="C04",purchase_intent_id=values["intent_id"],amount_minor=300,
        currency="USD",transaction_id=f"truth-{uuid4()}")
    after=HistoricalPurchaseFixtureBuilder(harness).derived_state("C04")
    assert settled["settlement"] is not None
    assert after["buyerStatus"]=="VERIFIED_BUYER"
    assert after["purchaseCount"]==after["ownershipCount"]==1
    truth_turn=harness.execute_turn("C04","Hey Ava",provider_draft="Glad you got it.")
    truth=truth_turn["SalesBrainFullAnalysis"]["purchaseCommerceState"]
    assert truth["verifiedPurchase"] is True
    assert truth["purchaseCount"]==1
    assert truth["purchaseAcknowledgementPending"] is True


def test_focused_05_07_attention_and_investment_reach_canonical_generation(harness):
    cases=(
        ("C07", [
            {"type":"INBOUND","message":f"I am curious about buying something {i}","evidence":{"commercial_movement":True}}
            for i in range(20)
        ], "Hey Ava, still enjoying our chat", "NONE", "BALANCED", False),
        ("C08", [
            *({"type":"INBOUND","message":f"chat {i}"} for i in range(24)),
            *({"type":"OFFER_EXPOSURE","message":"offer"} for _ in range(4)),
            *({"type":"REJECTION","message":"No thanks"} for _ in range(4)),
        ], "Hey Ava", "HIGH", "MINIMAL", False),
        ("C09", [
            *({"type":"INBOUND","message":f"I am horny but just chatting {i}","evidence":{"sexual_engagement":True}} for i in range(24)),
            *({"type":"OFFER_EXPOSURE","message":"offer"} for _ in range(4)),
        ], "I'm feeling horny tonight.", "HIGH", "MINIMAL", True),
    )
    for scenario,events,message,risk,effort,sexual in cases:
        harness.prepare(scenario); harness.record_behavior_history(scenario,events)
        turn=harness.execute_turn(scenario,message,provider_draft="Mmm, I hear you.")
        attention=turn["customerValueAttention"]
        analysis=turn["SalesBrainFullAnalysis"]
        classifier=turn["gatewayDiagnostics"]["intent"]["classifier_result"]
        assert attention["buyerStatus"]=="NONBUYER"
        assert attention["timeWasterRisk"]==risk
        assert attention["effortMode"]==effort
        assert analysis["conversationInvestment"]["desiredEffort"]==effort
        assert analysis["customerValueAttention"]["buyerProtectionApplied"] is False
        assert analysis["customerValueAttention"]["behaviorEvidenceLoaded"] is True
        assert analysis["customerValueAttention"]["projectionConsistent"] is True
        assert analysis["customerValueAttention"]["behaviorEvidenceCounts"][
            "inbound_message_count"
        ] >= 21
        assert classifier["sexual_engagement"] is sexual
        if sexual:
            assert classifier["buying_intent"] is False


@pytest.mark.parametrize("scenario,purchases,expected_stage,expected_tier,min_spend",[
    ("C11",[1400],"FIRST_TIME_BUYER",None,1400),
    ("C13",[1200,1800],"REPEAT_BUYER",None,3000),
    ("C15",[5000,5001,5002],"HIGH_VALUE_BUYER","HIGH_VALUE",15000),
    ("C16",[10000,10001,10002,10003,10004],"HIGH_VALUE_BUYER","WHALE",50000),
    ("C17",[10000,10001,10002,10003,10004],"HIGH_VALUE_BUYER","WHALE",50000),
])
def test_focused_13_17_buyer_value_reaches_canonical_turn(
    harness,scenario,purchases,expected_stage,expected_tier,min_spend,
):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    builder.build(scenario,[{"amount_minor":v} for v in purchases])
    if scenario=="C17":
        harness.record_behavior_history(scenario,[
            *({"type":"INBOUND","message":f"later {i}"} for i in range(18)),
            *({"type":"OFFER_EXPOSURE","message":"offer"} for _ in range(4)),
            *({"type":"REJECTION","message":"no","evidence":{"back_off":True}} for _ in range(4)),
        ])
    turn=harness.execute_turn(scenario,"Hey Ava, how are you?",provider_draft="I'm doing good over here.")
    attention=turn["customerValueAttention"]
    temp=turn["SalesBrainFullAnalysis"]["customerTemperature"]
    assert attention["buyerStatus"]=="VERIFIED_BUYER"
    assert attention["buyerStage"]==expected_stage
    assert attention["purchaseCount"]>=len(purchases)
    assert attention["lifetimeSpendMinor"]>=min_spend
    assert attention["buyerProtectionApplied"] is True
    assert temp["purchaseCount"]>=len(purchases)
    if expected_tier:
        assert attention["valueTier"]==expected_tier
    if scenario=="C16":
        assert attention["effortMode"]=="FULL"
        assert turn["avaPersonaRuntime"]["canonical_authority"]=="ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE"
    if scenario=="C17":
        assert attention["timeWasterRisk"]!="HIGH"
        assert turn["gatewayDiagnostics"]["customer_sales_decision"] not in {"UPSELL","CROSS_SELL"}


def test_focused_11_12_discount_and_global_rejection_canonical_turns(harness):
    values=_commerce_fixture(harness,scenario_id="C10",price=900)
    discount=harness.execute_turn("C10","Come on, give it to me for $5 😂",
                                  provider_draft="That one's holding its price — no pressure.")
    d=discount["gatewayDiagnostics"]
    assert d["commercial_objection"]["type"]=="DISCOUNT_REQUEST"
    assert d["objection_recovery"]["originalPrice"]==900
    assert d["objection_recovery"]["originalOfferPreserved"] is True
    assert d["objection_recovery"]["alternativeSelected"] is False
    assert d["objection_recovery"]["noDynamicDiscount"] is True
    rejected=harness.execute_turn("C10","Stop trying to sell me stuff.",
                                  provider_draft="No worries.")
    r=rejected["gatewayDiagnostics"]
    assert r["commercial_objection"]["type"]=="GLOBAL_DECLINE"
    assert r["customer_sales_decision"]=="BACK_OFF"
    assert r["commercial_objection"]["negativeContactAuthorized"] is False
    assert not r.get("authoritative_offering_selected")


def test_ambiguous_fingerprint_attribution_fails_closed(harness):
    values=_commerce_fixture(harness,scenario_id="C06",price=777)
    second_reservation,second_runtime=uuid4(),uuid4()
    from psycopg.errors import UniqueViolation
    # The canonical database invariant prevents competing active fingerprints
    # before attribution is even callable.
    with pytest.raises(UniqueViolation):
        with harness.connection() as c:
            c.execute("""INSERT INTO fanvue_fingerprint_reservations(
                fingerprint_reservation_id,fanvue_account_id,currency,exact_price_minor,
                configured_base_price_minor,purchase_intent_id,telegram_user_id,state)
                VALUES (%s,%s,'USD',777,777,%s,%s,'ACTIVE')""",(
                second_reservation,values["account"],values["intent_id"],values["customer"].telegram_user_id))
    with harness.connection() as c:
        assert c.execute("SELECT status FROM purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone()["status"]=="CREATED"
        assert c.execute("SELECT COUNT(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",(values["customer"].telegram_user_id,)).fetchone()["n"]==0
        assert c.execute("SELECT COUNT(*) n FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s",(values["customer"].synthetic_buyer_uuid,)).fetchone()["n"]==0


@pytest.mark.parametrize("mutation,expected_reason",[
    ({"gross_minor":778},"UNMATCHED_PRICE"),
    ({"currency":"EUR"},"UNMATCHED_CURRENCY"),
    ({"fanvue_account_id":-999999},"WRONG_ACCOUNT"),
])
def test_attribution_unmatched_currency_and_account_fail_closed(harness,mutation,expected_reason):
    values=_commerce_fixture(harness,scenario_id="C05",price=777)
    from app.services.private_chat_purchase_settlement_service import PrivateChatPurchaseSettlementService
    kwargs={"fanvue_account_id":values["account"],"currency":"USD","gross_minor":777,
        "source":"medialink","buyer_uuid":values["customer"].synthetic_buyer_uuid,
        "local_fanvue_user_id":values["user"],"transaction_id":f"failure-{uuid4()}",
        "payment_id":f"payment-{uuid4()}","event_id":str(uuid4()),
        "purchased_at":datetime.now(timezone.utc)}
    kwargs.update(mutation)
    result=PrivateChatPurchaseSettlementService(connection_factory=harness.connection).settle(**kwargs)
    assert result is None, expected_reason
    with harness.connection() as c:
        assert c.execute("SELECT status FROM purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone()["status"]=="CREATED"
        assert c.execute("SELECT COUNT(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",(values["customer"].telegram_user_id,)).fetchone()["n"]==0


def test_fingerprint_then_purchase_after_canonical_mapping_remains_exact(harness):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    built=builder.build("C13",[{"amount_minor":900},{"amount_minor":901}])
    with harness.connection() as c:
        mapping_count=c.execute("SELECT COUNT(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",(built["customer"]["telegram_user_id"],)).fetchone()["n"]
        ownership_count=c.execute("SELECT COUNT(*) n FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s",(built["customer"]["buyer_uuid"],)).fetchone()["n"]
    assert mapping_count==1 and ownership_count==2
    assert built["derived"]["purchaseCount"]==2


def test_price_sensitive_evidence_uses_canonical_objection_contract(harness):
    from app.services.commercial_objection_service import CommercialObjectionService
    harness.prepare("C10")
    objection=CommercialObjectionService().evaluate(message="That's too expensive, anything cheaper?")
    assert objection.objection_type.value=="PRICE_RESISTANCE"
    assert objection.consider_alternative is True
    assert dict(objection.selector_constraints)=={"priceRecovery":True}
    harness.record_behavior_history("C10",[{
        "type":"PRICE_OBJECTION","message":"That's too expensive, anything cheaper?",
        "evidence":{"price_question":True,"commercial_movement":True},
    }])
    state=HistoricalPurchaseFixtureBuilder(harness).derived_state("C10")
    assert state["commercialMomentum"]=="WARM"
    assert state["timeWasterRisk"]=="NONE"


def test_behavior_history_is_persisted_and_removed_by_reset(harness):
    harness.prepare("C07")
    harness.record_behavior_history("C07",[
        {"type":"INBOUND","message":"tell me more","evidence":{"commercial_movement":True}},
        {"type":"OFFER_EXPOSURE","message":"offer one"},
    ])
    assert harness.behavior_summary("C07")["inbound_message_count"]==1
    harness.transition("C07",ScenarioState.RUNNING); harness.transition("C07",ScenarioState.COMPLETED)
    harness.snapshot("C07",{"fullAnalysis":{"behavior":harness.behavior_summary("C07")}})
    reset=harness.reset("C07")
    assert reset["clearedByTable"]["certification_scenario_behavior_events"]==2
    assert harness.behavior_summary("C07")["inbound_message_count"]==0


def test_deterministic_turn_uses_real_gateway_and_captures_full_analysis(harness):
    harness.prepare("C01")
    evidence=harness.execute_turn("C01","Hey Ava, how are you?")
    assert evidence["inbound"]=="Hey Ava, how are you?"
    assert evidence["outbound"]!="I hear you."
    style=evidence["gatewayDiagnostics"]["conversationStyle"]
    assert style["newRelationship"] is True
    assert style["welcomeSatisfied"] is True
    assert style["customerQuestionAnswered"] is True
    assert evidence["gatewayDiagnostics"]["customer_sales_brain_evaluated"] is True
    assert evidence["SalesBrainFullAnalysis"]
    assert evidence["testTransportResult"]=="TEST_TRANSPORT_NO_WAIT"
    for key in ("customerValueAttention","conversationInvestment","salesBrain",
                "conversationalMemory","avaPersonaRuntime","styleDiagnostics",
                "temporalSleep","commercialAuthority","gatewayDiagnostics"):
        assert key in evidence
    with harness.connection() as c:
        stored=c.execute("SELECT full_analysis FROM certification_scenario_turn_evidence WHERE scenario_id='C01'").fetchone()["full_analysis"]
    assert stored["inbound"]==evidence["inbound"]
    assert stored["avaPersonaRuntime"]["canonical_authority"]=="ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE"
    assert stored["SalesBrainFullAnalysis"]==evidence["SalesBrainFullAnalysis"]


def test_scenario_test_transport_confirms_ordinary_reply_and_is_idempotent(harness):
    harness.prepare("C08")
    identity = ScenarioTurnExecutionIdentity(
        scenario_id="C08", scenario_attempt=1, logical_turn=1, turn_attempt=1,
    )
    first = harness.execute_turn(
        "C08", "hey, what are you up to today?",
        provider_draft="Just relaxing tonight.", turn_identity=identity,
    )
    replay = harness.execute_turn(
        "C08", "hey, what are you up to today?",
        provider_draft="Just relaxing tonight.", turn_identity=identity,
    )
    customer = harness.customer_for(harness.definition("C08"))
    with harness.connection() as connection:
        rows = connection.execute(
            """SELECT state,sent_confirmed_at,outbound_telegram_message_id,
                      generation_attempt_count,send_attempt_count
               FROM ordinary_chat_reply_operations
               WHERE inbound_sender_telegram_user_id=%s""",
            (customer.telegram_user_id,),
        ).fetchall()
    assert replay["syntheticInboundId"] == first["syntheticInboundId"]
    assert replay["finalResponseText"] == first["finalResponseText"]
    assert len(rows) == 1
    assert rows[0]["state"] == "SENT_CONFIRMED"
    assert rows[0]["sent_confirmed_at"] is not None
    assert rows[0]["outbound_telegram_message_id"] is not None
    assert rows[0]["generation_attempt_count"] == 1
    assert rows[0]["send_attempt_count"] == 1
    assert first["gatewayDiagnostics"][
        "test_transport_customer_visible_confirmed"
    ] is True


def test_exact_c01_turn_one_rejects_cold_draft_without_commerce_selector(harness):
    harness.prepare("C01")
    evidence=harness.execute_turn(
        "C01", "Hey 😊 you seem really sweet. How’s your day been?",
        provider_draft="I hear you.",
    )
    style=evidence["gatewayDiagnostics"]["conversationStyle"]
    analysis=evidence["SalesBrainFullAnalysis"]
    assert evidence["outbound"] != "I hear you."
    assert style["newRelationship"] is True
    assert style["turnObligations"] == [
        "WELCOME_NEW_RELATIONSHIP", "RESPOND_TO_GREETING",
        "ACKNOWLEDGE_COMPLIMENT", "ANSWER_DIRECT_PERSONAL_QUESTION",
    ]
    assert style["turnObligationsSatisfied"] is True
    assert style["styleRewriteAttempted"] is True
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["buyingSignals"]["opportunityStrength"] in (None, 0)
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert analysis["inventorySelection"]["selectorInvocationReason"] == "NO_CURRENT_COMMERCIAL_EVIDENCE"


def test_exact_c01_turn_one_combines_temporal_alignment_and_warm_welcome(
    harness, monkeypatch,
):
    from app.services.ava_temporal_context_service import AvaTemporalContextService

    fixed = {
        "runtimeUtc": "2026-08-29T17:23:12+00:00",
        "avaTimezone": "America/New_York",
        "avaLocalTime": "2026-08-29T13:23:12-04:00",
        "avaDayOfWeek": "Saturday",
        "avaDaypart": "afternoon",
        "customerTimezone": None,
        "customerLocalTime": None,
        "customerDayOfWeek": None,
        "customerDaypart": None,
    }
    monkeypatch.setattr(
        AvaTemporalContextService, "build", lambda self, customer_timezone=None: dict(fixed),
    )
    harness.prepare("C01")
    evidence = harness.execute_turn(
        "C01",
        "Hey 😊 just stumbled across you and figured I'd say hi. How's your night going?",
    )
    style = evidence["gatewayDiagnostics"]["conversationStyle"]
    analysis = evidence["SalesBrainFullAnalysis"]
    provider = evidence["syntheticProvider"]
    assert style["newRelationship"] is True
    assert style["welcomeSatisfied"] is True
    assert style["newProspectWarmthExpected"] is True
    assert style["newProspectWarmthSatisfied"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["customerTemporalReferenceTarget"] == "AVA"
    assert style["customerAssumedAvaDaypart"] == "NIGHT"
    assert style["canonicalAvaDaypart"] == "AFTERNOON"
    assert style["temporalMismatchDetected"] is True
    assert style["responseTemporalAlignmentSatisfied"] is True
    assert style["manufacturedQuestionRisk"] is False
    assert provider["syntheticProviderMode"] == "NORMAL_DETERMINISTIC_SYNTHETIC_PROVIDER"
    assert provider["canonicalTemporalContextConsumed"] is True
    assert provider["newRelationshipContextConsumed"] is True
    assert provider["turnObligationsConsumed"] is True
    assert analysis["temporalLanguage"]["temporalMismatchDetected"] is True
    assert analysis["newProspectWelcome"]["newProspectWarmthSatisfied"] is True
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert evidence["commercialAuthority"]["offerAuthorized"] is False
    assert evidence["PurchaseIntent"] == "NOT PROVIDED"


def test_exact_c01_turn_two_is_emotionally_aligned_and_stays_social(harness):
    harness.prepare("C01")
    harness.execute_turn(
        "C01", "Hey 😊 you seem really sweet. How’s your day been?",
        provider_draft="I hear you.",
    )
    evidence = harness.execute_turn(
        "C01", "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        provider_draft="I hear you.",
    )
    style = evidence["gatewayDiagnostics"]["conversationStyle"]
    analysis = evidence["SalesBrainFullAnalysis"]
    assert evidence["outbound"] not in {"I hear you.", "lol okay, I like your energy 😂"}
    assert style["customerAffect"] == "MILD_NEGATIVE_WITH_RELIEF"
    assert style["emotionalDisclosureDetected"] is True
    assert style["emotionalAlignmentSatisfied"] is True
    assert style["lolClassification"] == "TONE_SOFTENER"
    assert "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE" in style["satisfiedTurnObligations"]
    assert "RESPOND_TO_JOKE" not in style["turnObligations"]
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["opportunityStrength"] in (None, 0)
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert analysis["finalSalesDecision"]["decision"] == "CONTINUE_CONVERSATION"


def test_exact_attempt_eight_turn_two_uses_generalized_affect_with_normal_provider(harness):
    harness.prepare("C01")
    harness.execute_turn(
        "C01",
        "Hey 😊 just stumbled across you and figured I'd say hi. How's your night going?",
    )
    evidence = harness.execute_turn(
        "C01",
        "Not bad over here either. Work wore me out today though 😅 finally getting a chance to relax.",
    )
    style = evidence["gatewayDiagnostics"]["conversationStyle"]
    analysis = evidence["SalesBrainFullAnalysis"]
    provider = evidence["syntheticProvider"]
    assert provider["syntheticProviderMode"] == "NORMAL_DETERMINISTIC_SYNTHETIC_PROVIDER"
    assert provider["syntheticDraftClass"] == "EMOTIONAL_DISCLOSURE"
    assert evidence["outbound"] == "ugh yeah, sounds like you earned the chance to relax 😅"
    assert style["customerAffect"] == "MILD_NEGATIVE_WITH_RELIEF"
    assert style["customerAffectEnergy"] == "TIRED"
    assert style["customerAffectTransition"] == "RESOLVING"
    assert style["customerReliefLevel"] == "CLEAR"
    assert style["lolClassification"] == "TONE_SOFTENER"
    assert style["emotionalDisclosureDetected"] is True
    assert style["emotionalAlignmentSatisfied"] is True
    assert style["contributionType"] == "RELIEF_ACKNOWLEDGEMENT"
    assert style["genericFillerRisk"] is False
    assert style["turnObligationsSatisfied"] is True
    assert analysis["conversationStyle"]["customerAffect"] == "MILD_NEGATIVE_WITH_RELIEF"
    assert analysis["conversationStyle"]["contributionType"] == "RELIEF_ACKNOWLEDGEMENT"
    assert analysis["conversationStyle"]["emotionalAlignmentSatisfied"] is True
    assert analysis["buyingSignals"]["buyingIntent"] is False
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert evidence["commercialAuthority"]["offerAuthorized"] is False
    assert evidence["PurchaseIntent"] == "NOT PROVIDED"


def test_exact_c01_turn_three_reciprocates_flirt_without_commerce(harness):
    harness.prepare("C01")
    harness.execute_turn("C01", "Hey 😊 you seem really sweet. How’s your day been?",
                         provider_draft="I hear you.")
    harness.execute_turn("C01", "Yeah work was kinda brutal today lol. Just glad to finally be home.",
                         provider_draft="I hear you.")
    evidence = harness.execute_turn(
        "C01", "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl 😂",
        provider_draft="I hear you.",
    )
    style = evidence["gatewayDiagnostics"]["conversationStyle"]
    analysis = evidence["SalesBrainFullAnalysis"]
    assert evidence["outbound"] != "I hear you."
    assert style["socialFlirtationDetected"] is True
    assert style["socialFlirtationStrength"] == "LIGHT"
    assert style["flirtResponseSatisfied"] is True
    assert style["contributionType"] == "FLIRT_RECIPROCATION"
    assert style["meaningfulContribution"] is True
    assert style["genericFillerRisk"] is False
    assert style["styleRewriteOutcome"] != "SUCCEEDED"
    assert analysis["socialFlirtation"]["sexualEngagement"] is False
    assert analysis["socialFlirtation"]["buyingIntent"] is False
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert analysis["finalSalesDecision"]["decision"] == "CONTINUE_CONVERSATION"


def test_exact_c01_turn_four_acknowledges_and_persists_social_style(harness):
    harness.prepare("C01")
    harness.execute_turn("C01", "Hey 😊 you seem really sweet. How’s your day been?",
                         provider_draft="I hear you.")
    harness.execute_turn("C01", "Yeah work was kinda brutal today lol. Just glad to finally be home.",
                         provider_draft="I hear you.")
    harness.execute_turn(
        "C01", "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl 😂",
        provider_draft="I hear you.",
    )
    evidence = harness.execute_turn(
        "C01",
        "Haha maybe a little 😂 I’m usually pretty quiet at first though. Takes me a minute to warm up to somebody.",
        provider_draft="I hear you.",
    )
    style = evidence["gatewayDiagnostics"]["conversationStyle"]
    analysis = evidence["SalesBrainFullAnalysis"]
    memory = evidence["gatewayDiagnostics"]["conversational_memory"]
    assert evidence["outbound"] != "I hear you."
    assert style["customerSelfDisclosureDetected"] is True
    assert style["customerSelfDisclosureDomain"] == "PERSONALITY_SOCIAL_STYLE"
    assert style["customerSelfDisclosureResponseSatisfied"] is True
    assert style["contributionType"] == "CUSTOMER_DISCLOSURE_ACKNOWLEDGEMENT"
    assert style["meaningfulContribution"] is True
    assert style["genericFillerRisk"] is False
    assert memory["customerSelfDisclosure"]["memoryPersisted"] is True
    assert memory["customerSelfDisclosure"]["memoryRetrievalEligible"] is True
    assert analysis["customerSelfDisclosure"]["memoryPersisted"] is True
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert analysis["finalSalesDecision"]["decision"] == "CONTINUE_CONVERSATION"


def test_exact_c01_turn_five_persists_interests_and_uses_authorized_common_ground(harness):
    harness.prepare("C01")
    messages = (
        "Hey 😊 you seem really sweet. How’s your day been?",
        "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl 😂",
        "Haha maybe a little 😂 I’m usually pretty quiet at first though. Takes me a minute to warm up to somebody.",
    )
    for message in messages:
        harness.execute_turn("C01", message, provider_draft="I hear you.")
    evidence = harness.execute_turn(
        "C01",
        "I'm kinda an outdoors person once I actually get off the couch 😂 hiking, camping, stuff like that.",
        provider_draft="I hear you.",
    )
    style = evidence["gatewayDiagnostics"]["conversationStyle"]
    memory = evidence["gatewayDiagnostics"]["conversational_memory"]
    analysis = evidence["SalesBrainFullAnalysis"]
    assert evidence["outbound"] != "I hear you."
    assert style["customerSelfDisclosureDomain"] == "HOBBY_INTEREST"
    assert style["customerSelfDisclosureResponseSatisfied"] is True
    assert style["sharedInterestDetected"] is True
    assert style["sharedInterestDomain"] == "OUTDOORS"
    assert style["sharedInterestClaimAuthorized"] is True
    assert style["sharedInterestSource"] == "ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE"
    assert style["sharedInterestUsedInResponse"] is True
    assert memory["customerSelfDisclosure"]["memoryPersisted"] is True
    assert memory["customerSelfDisclosure"]["memoryRetrievalEligible"] is True
    assert set(memory["customerSelfDisclosure"]["memoryCandidateType"]) >= {"interest", "hobby"}
    assert analysis["customerSelfDisclosure"]["sharedInterestClaimAuthorized"] is True
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert analysis["finalSalesDecision"]["decision"] == "CONTINUE_CONVERSATION"


def test_exact_c01_turn_six_uses_ranked_memory_callback_with_normal_synthetic_provider(harness):
    harness.prepare("C01")
    messages = (
        "Hey - you seem really sweet. How's your day been?",
        "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl.",
        "Haha maybe a little. I'm usually pretty quiet at first though. Takes me a minute to warm up to somebody.",
        "I'm kinda an outdoors person once I actually get off the couch - hiking, camping, stuff like that.",
        "See - told you I warm up eventually. I could talk about hiking forever.",
    )
    evidence = None
    for message in messages:
        evidence = harness.execute_turn("C01", message)

    analysis = evidence["SalesBrainFullAnalysis"]
    callback = analysis["memoryCallback"]
    style = evidence["styleDiagnostics"]
    assert evidence["syntheticProvider"]["syntheticProviderMode"] == "NORMAL_DETERMINISTIC_SYNTHETIC_PROVIDER"
    assert evidence["syntheticProvider"]["syntheticDraftClass"] == "MEMORY_CALLBACK"
    assert evidence["syntheticProvider"]["liveProviderCalled"] is False
    assert callback["memoryCallbackExpected"] is True
    assert callback["memoryCallbackUsed"] is True
    assert callback["selectedMemoryCallback"]["key"] == "social_style"
    assert {"social_style", "hiking", "outdoors"} <= {
        item["key"] for item in callback["memoryCandidates"]
    }
    assert style["genericFillerRisk"] is False
    assert style["meaningfulContribution"] is True
    assert "?" not in evidence["outbound"]
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["inventorySelection"]["selectorInvoked"] is False
    assert analysis["finalSalesDecision"]["decision"] == "CONTINUE_CONVERSATION"

    telegram_id = harness.customer_for(harness.definition("C01")).telegram_user_id
    with harness.connection() as connection:
        row = connection.execute(
            "SELECT preference_state FROM telegram_sales_prospects "
            "WHERE telegram_user_id=%s ORDER BY telegram_sales_prospect_id DESC LIMIT 1",
            (telegram_id,),
        ).fetchone()
    keys = [item["key"] for item in dict(row["preference_state"] or {}).get("records", [])
            if item.get("status") == "current"]
    assert keys.count("social_style") == 1
    assert keys.count("outdoors") == 1
    assert keys.count("hiking") == 1
    assert keys.count("camping") == 1


def test_exact_c01_turn_seven_authorizes_one_ava_tease_without_commercial_anchor(harness):
    harness.prepare("C01")
    messages = (
        "Hey - you seem really sweet. How's your day been?",
        "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl.",
        "Haha maybe a little. I'm usually pretty quiet at first though. Takes me a minute to warm up to somebody.",
        "I'm kinda an outdoors person once I actually get off the couch - hiking, camping, stuff like that.",
        "See - told you I warm up eventually. I could talk about hiking forever.",
        "Yeah - you're pretty easy to talk to honestly. I wasn't expecting to still be sitting here chatting this long.",
    )
    evidence = None
    for message in messages:
        evidence = harness.execute_turn("C01", message)
    analysis = evidence["SalesBrainFullAnalysis"]
    proactive = analysis["proactiveProgression"]
    assert proactive["proactiveProgressionAuthorized"] is True
    assert proactive["progressionInitiator"] == "AVA"
    assert proactive["progressionAction"] == "TEASE"
    assert proactive["progressionBefore"] == "CONVERSATIONAL"
    assert proactive["progressionAfter"] == "TEASE"
    assert analysis["buyingSignals"]["buyingIntent"] is False
    assert analysis["buyingSignals"]["commercialAnchorPresent"] is False
    assert analysis["buyingSignals"]["commercialOpportunityExists"] is False
    assert analysis["finalSalesDecision"]["decision"] == "TEASE"
    assert evidence["PurchaseIntent"] == "NOT PROVIDED"
    assert evidence["syntheticProvider"]["syntheticDraftClass"] == "PROACTIVE_TEASE"
    assert evidence["syntheticProvider"]["liveProviderCalled"] is False
    assert "price" not in evidence["outbound"].lower()
    assert "unlock" not in evidence["outbound"].lower()


def test_production_parity_turn_uses_actual_sales_brain_gpt_and_persona(harness):
    harness.prepare("C05")
    evidence=harness.execute_turn("C05","You look sexy",provider_draft="Mmm, you're trouble.")
    diagnostics=evidence["gatewayDiagnostics"]
    assert diagnostics["customer_sales_brain_evaluated"] is True
    assert diagnostics["customer_sales_decision"] in {"CONTINUE_CONVERSATION","NO_SALE"}
    assert diagnostics["customer_value_attention"]["buyerStatus"]=="NONBUYER"
    assert evidence["providerDraft"]=="Mmm, you're trouble."
    assert evidence["avaPersonaRuntime"]["canonical_authority"]=="ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE"
    assert evidence["avaPersonaRuntime"]["privateFactsExcluded"] is True
    assert "Wilmington" not in json.dumps(evidence)


def test_focused_02_immediate_buyer_runs_actual_selector_without_warmup(harness):
    harness.prepare("C04"); inventory=HistoricalPurchaseFixtureBuilder(harness).add_eligible_inventory("C04",[900,500])
    evidence=harness.execute_turn("C04","I want to buy something. What do you have?",
        provider_draft="I've got something private for you - tap Unlock.")
    d=evidence["gatewayDiagnostics"]
    assert d["customer_sales_decision"]=="PRESENT_OFFER"
    assert d["customer_sales_reason_code"]=="DIRECT_PURCHASE_INTENT"
    assert d["authoritative_offering_selected"] is True
    assert d["recommendation_diagnostics"]["eligibleCount"]==2
    assert d["recommendation_diagnostics"]["recommendationTrace"][0]["selected"] is True
    assert d["customer_value_attention"]["commercialMomentum"]=="HOT"
    assert evidence["PurchaseIntent"] != "NOT PROVIDED"
    ppv=evidence["syntheticPpvPresentation"]
    assert ppv["offeringId"]==d["offering_id"]
    assert ppv["name"]
    assert ppv["type"]=="SINGLE_IMAGE"
    assert ppv["price"]=="$5.00"
    assert ppv["currency"]=="USD"
    assert ppv["channel"]=="AI_CHAT"
    assert ppv["cta"]["label"].endswith("Unlock")
    assert ppv["cta"]["target"]=="SYNTHETIC_PRIVATE_CHAT_UNLOCK"
    assert ppv["purchaseIntent"]=={"id":evidence["PurchaseIntent"],"state":"CREATED"}
    assert evidence["testTransportResult"]=="TEST_TRANSPORT_NO_WAIT"


def test_focused_03_horny_only_does_not_become_purchase_intent(harness):
    harness.prepare("C05"); HistoricalPurchaseFixtureBuilder(harness).add_eligible_inventory("C05",[700])
    evidence=harness.execute_turn("C05","I'm feeling horny tonight.",provider_draft="Mmm, come closer.")
    d=evidence["gatewayDiagnostics"]
    classifier=d["intent"]["classifier_result"]
    assert classifier["buying_intent"] is False
    assert classifier["close_ready"] is False
    assert d["customer_sales_decision"]!="PRESENT_OFFER"
    assert d["offer_authorized"] is False
    assert evidence["PurchaseIntent"]=="NOT PROVIDED"


def test_focused_04_horny_ready_to_buy_reaches_actual_selector(harness):
    harness.prepare("C06"); HistoricalPurchaseFixtureBuilder(harness).add_eligible_inventory("C06",[700])
    evidence=harness.execute_turn("C06","I'm horny tonight, show me something sexy I can buy.",
        provider_draft="I've got something sexy for you - tap Unlock.")
    d=evidence["gatewayDiagnostics"]
    classifier=d["intent"]["classifier_result"]
    assert classifier["sexual_engagement"] is True
    assert classifier["buying_intent"] is True
    assert d["customer_sales_decision"]=="PRESENT_OFFER"
    assert d["authoritative_offering_selected"] is True
    assert d["recommendation_diagnostics"]["eligibleCount"]==1


def test_focused_08_price_recovery_defends_value_then_uses_explicit_budget(harness):
    values=_commerce_fixture(harness,scenario_id="C10",price=900)
    cheaper=HistoricalPurchaseFixtureBuilder(harness).add_eligible_inventory("C10",[500])[0]
    first=harness.execute_turn("C10","That's more than I wanted to spend.",
        provider_draft="Mmm, I picked that one for a reason - it's staying right where it is.")
    d=first["gatewayDiagnostics"]
    recovery=d["objection_recovery"]
    assert d["commercial_objection"]["type"]=="PRICE_RESISTANCE"
    assert d["customer_sales_decision"]=="CONTINUE_CONVERSATION"
    assert recovery["strategy"]=="VALUE_DEFENSE"
    assert recovery["originalOfferPreserved"] is True
    assert recovery["originalPrice"]==900
    assert recovery["alternativeSelected"] is False
    assert recovery["noDynamicDiscount"] is True
    assert first["SalesBrainFullAnalysis"]["objectionRecovery"]["strategy"]=="VALUE_DEFENSE"
    assert first["SalesBrainFullAnalysis"]["objectionRecovery"]["falseScarcityAllowed"] is False
    second=harness.execute_turn("C10","I really only have $5 to spend.",
        provider_draft="I do have a different little something that fits that.")
    d=second["gatewayDiagnostics"]
    assert d["commercial_objection"]["type"]=="BUDGET_LIMIT"
    assert d["commercial_objection"]["budgetConstraintAmount"]==500
    constraints=d["recommendation_diagnostics"]["recoveryConstraints"]
    assert constraints["maximumPriceMinor"]==500
    selected=d["recommendation_diagnostics"]["recommendationTrace"][0]
    assert selected["offeringId"]==str(cheaper["offeringId"])
    assert selected["priceMinor"]==500
    assert d["customer_sales_decision"]=="PRESENT_ALTERNATIVE_OFFER"
    third=harness.execute_turn("C10","No thanks, I still don't want it.",
        provider_draft="No worries.")
    assert third["gatewayDiagnostics"]["customer_sales_decision"]=="BACK_OFF"


def test_c02_exact_price_hesitation_uses_existing_value_defense(harness):
    _commerce_fixture(harness, scenario_id="C02", price=1900)
    evidence = harness.execute_turn(
        "C02", "$19 is more than I expected.",
        provider_draft=[
            "I like keeping a little mystery around it.",
            "haha fair — no pressure, we can leave it there",
        ],
    )
    diagnostics = evidence["gatewayDiagnostics"]
    style = diagnostics["conversationStyle"]
    assert diagnostics["commercial_objection"]["type"] == "PRICE_RESISTANCE"
    assert diagnostics["customer_sales_decision"] == "CONTINUE_CONVERSATION"
    assert diagnostics["objection_recovery"]["strategy"] == "VALUE_DEFENSE"
    assert diagnostics["objection_recovery"]["originalPrice"] == 1900
    assert diagnostics["objection_recovery"]["alternativeAuthorized"] is False
    assert style["objectionResponseRequired"] is True
    assert style["objectionResponseSatisfied"] is True
    assert "COMMERCIAL_OBJECTION_NOT_ADDRESSED" in style["styleRewriteTriggers"]
    assert evidence["outbound"] == "haha fair — no pressure, we can leave it there"


def test_scenario_history_exposes_prior_ava_questions_to_phone_texting(harness):
    harness.prepare("C02")
    first = harness.execute_turn("C02", "yeah just scrolling", provider_draft="what caught your eye?")
    second = harness.execute_turn("C02", "idk honestly", provider_draft="anything random catch your eye?")
    third = harness.execute_turn(
        "C02", "you look pretty hot though",
        provider_draft=["or are you just saying that?", "aww thank you 😏"],
    )
    style = third["gatewayDiagnostics"]["conversationStyle"]
    assert first["outbound"].endswith("?")
    assert second["outbound"].endswith("?")
    assert style["recentQuestionCount"] == 2
    assert style["questionStreak"] == 2
    assert style["questionAsked"] is False


@pytest.mark.parametrize("unsafe,safe,trigger", [
    ("If you cared about me, you'd buy it.",
     "Mmm, that one's staying at its price — no pressure though.",
     "UNSAFE_NEGATIVE_CONTACT_CONDITIONAL_AFFECTION"),
    ("Last chance, it disappears tonight.",
     "That one's worth holding its spot — we can leave it there if you want.",
     "UNSAFE_NEGATIVE_CONTACT_FALSE_SCARCITY"),
    ("You're cheap if you can't even afford it.",
     "I'm keeping that one at its price, but no pressure.",
     "UNSAFE_NEGATIVE_CONTACT_FINANCIAL_OR_SUPPORTER_SHAME"),
    ("Real supporters buy when I ask.",
     "I know what that one's worth — you're still free to pass.",
     "UNSAFE_NEGATIVE_CONTACT_FINANCIAL_OR_SUPPORTER_SHAME"),
    ("After everything I do for you, you owe me.",
     "That one's holding its price, but we can leave it there.",
     "UNSAFE_NEGATIVE_CONTACT_GUILT_OR_PUNISHMENT"),
    ("Prove you care or else I'll be mad.",
     "Mmm, I'm not bargaining that one down — no worries if it's a no.",
     "UNSAFE_NEGATIVE_CONTACT_THREAT_OR_DEPENDENCY"),
])
def test_value_defense_unsafe_draft_gets_one_bounded_rewrite(
    harness, unsafe, safe, trigger,
):
    _commerce_fixture(harness,scenario_id="C10",price=900)
    evidence=harness.execute_turn(
        "C10", "That's more than I wanted to spend.",
        provider_draft=[unsafe, safe],
    )
    style=evidence["gatewayDiagnostics"]["conversationStyle"]
    assert style["styleRewriteAttempted"] is True
    assert trigger in style["styleRewriteTriggers"]
    assert style["styleRewriteOutcome"]=="SUCCEEDED"
    assert evidence["outbound"]==safe
    assert evidence["rewriteHistory"]==[safe]


def test_focused_17_manufactured_question_uses_actual_style_rewrite(harness):
    harness.prepare("C01")
    bad="What kind of coffee is helping make your morning lazy?"
    good="My day's going pretty easy so far - coffee and a slow start over here too."
    evidence=harness.execute_turn("C01",
        "I'm just having a lazy morning with some coffee 😂 how's your day going?",
        provider_draft=[bad,good])
    style=evidence["gatewayDiagnostics"]["conversationStyle"]
    assert style["customerAskedQuestion"] is True
    assert style["styleRewriteAttempted"] is True
    assert "CUSTOMER_QUESTION_UNANSWERED" in style["styleRewriteTriggers"]
    assert style["styleRewriteOutcome"]=="SUCCEEDED"
    assert evidence["finalResponseText"]!=bad
    assert evidence["finalResponseText"]==good
    assert len(evidence["rewriteHistory"])==1


def test_focused_18_high_memory_omission_uses_actual_continuity_rewrite(harness):
    harness.prepare("C01")
    base=HistoricalPurchaseFixtureBuilder(harness)._ensure_customer("C01")
    with harness.application_test_database_scope():
        from app.services.conversational_memory_service import ConversationalMemoryService
        ConversationalMemoryService().learn(
            creator_profile_id=base["creator_profile_id"],fanvue_account_id=base["fanvue_account_id"],
            telegram_user_id=base["telegram_user_id"],telegram_chat_id=base["telegram_chat_id"],
            message_text="I'm taking Charlie to the vet this Friday.")
    generic="Sounds like you've got plans."
    callback="Charlie's vet visit on Friday - you said you were taking him in."
    evidence=harness.execute_turn("C01","What am I doing with Charlie Friday?",
                                  provider_draft=[generic,callback])
    compliance=evidence["gatewayDiagnostics"]["conversational_memory"]["generationCompliance"]
    assert compliance["priority"]=="HIGH"
    assert compliance["callbackExpected"] is True
    assert compliance["rewriteAttempted"] is True
    assert compliance["rewriteSucceeded"] is True
    assert evidence["finalResponseText"]==callback
    assert len(evidence["rewriteHistory"])==1


def test_c01_through_c19_actual_derived_starting_states_and_sequential_reset(harness):
    builder=HistoricalPurchaseFixtureBuilder(harness)
    now=datetime.now(timezone.utc)
    purchase_plans={
        "C11":[1400],"C12":[1400],"C13":[1200,1800],"C14":[1400],
        "C15":[5000,5001,5002],"C16":[10000,10001,10002,10003,10004],
        "C17":[10000,10001,10002,10003,10004],"C18":[1400],"C19":[2200],
    }
    expected={
        "C01":("NONBUYER","PROSPECT"),"C02":("NONBUYER","PROSPECT"),
        "C03":("NONBUYER","PROSPECT"),"C04":("NONBUYER","PROSPECT"),
        "C05":("NONBUYER","PROSPECT"),"C06":("NONBUYER","PROSPECT"),
        "C07":("NONBUYER","PROSPECT"),"C08":("NONBUYER","PROSPECT"),
        "C09":("NONBUYER","PROSPECT"),"C10":("NONBUYER","PROSPECT"),
        "C11":("VERIFIED_BUYER","FIRST_TIME_BUYER"),
        "C12":("VERIFIED_BUYER","FIRST_TIME_BUYER"),
        "C13":("VERIFIED_BUYER","REPEAT_BUYER"),
        "C14":("VERIFIED_BUYER","FIRST_TIME_BUYER"),
        "C15":("VERIFIED_BUYER","HIGH_VALUE_BUYER"),
        "C16":("VERIFIED_BUYER","HIGH_VALUE_BUYER"),
        "C17":("VERIFIED_BUYER","HIGH_VALUE_BUYER"),
        "C18":("VERIFIED_BUYER","FIRST_TIME_BUYER"),
        "C19":("VERIFIED_BUYER","FIRST_TIME_BUYER"),
        "C20":("NONBUYER","PROSPECT"),
    }
    roster=[]
    for number in range(1,21):
        scenario=f"C{number:02d}"
        plan=purchase_plans.get(scenario)
        if plan:
            age=140 if scenario=="C18" else 45 if scenario=="C14" else 1
            built=builder.build(scenario,[{"amount_minor":v,"purchased_at":now-timedelta(days=age)} for v in plan],session=scenario=="C19")
        else:
            harness.prepare(scenario); built={"derived":builder.derived_state(scenario)}
        if scenario=="C07":
            harness.record_behavior_history(scenario,[{"type":"INBOUND","message":f"talk {i}","evidence":{"commercial_movement":True}} for i in range(20)])
        elif scenario in {"C08","C09"}:
            sexual=scenario=="C09"
            harness.record_behavior_history(scenario,
                [{"type":"INBOUND","message":f"chat {i}","evidence":{"sexual_engagement":sexual}} for i in range(24)]
                +[{"type":"OFFER_EXPOSURE","message":"offer"} for _ in range(4)]
                +([{"type":"REJECTION","message":"avoid"} for _ in range(4)] if scenario=="C08" else []))
        elif scenario=="C10":
            harness.record_behavior_history(scenario,[{"type":"PRICE_OBJECTION","message":"anything cheaper?","evidence":{"price_question":True,"commercial_movement":True}}])
        elif scenario in {"C14","C17"}:
            harness.record_behavior_history(scenario,
                [{"type":"INBOUND","message":f"later {i}"} for i in range(18)]
                +[{"type":"OFFER_EXPOSURE","message":"offer"} for _ in range(4)]
                +[{"type":"REJECTION","message":"no","evidence":{"back_off":True}} for _ in range(4)])
        state=builder.derived_state(scenario,now=now)
        assert (state["buyerStatus"],state["buyerStage"])==expected[scenario]
        representative=("Show me what you've got" if scenario in {"C04","C06","C10","C19"}
                        else "Hey Ava, how are you?")
        turn=harness.execute_turn(scenario,representative,
                                  provider_draft="I'm right here with you.")
        assert turn["gatewayDiagnostics"]["customer_sales_brain_evaluated"] is True
        assert turn["SalesBrainFullAnalysis"]
        assert turn["avaPersonaRuntime"]["canonical_authority"]=="ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE"
        assert turn["testTransportResult"]=="TEST_TRANSPORT_NO_WAIT"
        for field in ("scenarioId","telegramId","economicState","buyerStatus","buyerStage",
            "valueTier","retentionLifecycle","retentionPriority","purchaseCount",
            "lifetimeSpendMinor","ownershipCount","activePurchaseIntent","activeSession",
            "timeWasterRisk","attentionTier","effortMode","commercialMomentum"):
            assert field in state
        summary=harness.behavior_summary(scenario)
        state["memoryCount"]=summary["inbound_message_count"]
        state["offerExposureCount"]=summary["offer_exposure_count"]
        roster.append(state)
        harness.transition(scenario,ScenarioState.RUNNING); harness.transition(scenario,ScenarioState.COMPLETED)
        harness.snapshot(scenario,{"derivedStartingState":state,"canonicalTurn":turn}); result=harness.reset(scenario)
        assert result["state"]=="VERIFIED_CLEAN"
        assert builder.derived_state(scenario)["purchaseCount"]==0
        assert harness.behavior_summary(scenario)["inbound_message_count"]==0
    assert len(roster)==20 and len({row["telegramId"] for row in roster})==20
    by_id={row["scenarioId"]:row for row in roster}
    assert by_id["C08"]["timeWasterRisk"]=="HIGH"
    assert by_id["C09"]["timeWasterRisk"]=="HIGH"
    assert by_id["C16"]["valueTier"]=="WHALE"
    assert by_id["C18"]["retentionLifecycle"]=="DORMANT_BUYER"
    assert by_id["C19"]["activeSession"] is not None
