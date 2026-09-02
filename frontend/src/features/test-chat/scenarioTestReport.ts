import type { FullScenarioAnalysis, ScenarioLabSnapshot } from "../../infrastructure/api/testChatApi";
import { redactObserverSnapshot } from "./fullAnalysisExport";

const NOT_PROVIDED = "NOT PROVIDED";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

function at(source: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => record(value)[key], source);
}

function first(source: unknown, paths: string[]): unknown {
  for (const path of paths) {
    const value = at(source, path);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function printable(value: unknown): string {
  if (value === undefined || value === null || value === "") return NOT_PROVIDED;
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function field(label: string, value: unknown): string {
  return `${label}:\n${printable(value)}`;
}

function transcript(snapshot: ScenarioLabSnapshot): string {
  if (!snapshot.transcript.length) return "No conversation yet.";
  let turn = 0;
  return snapshot.transcript.map((item) => {
    if (item.role === "user") turn += 1;
    return `${item.role === "user" ? `Turn ${turn}\nCustomer` : "Ava"}: ${item.content}`;
  }).join("\n\n");
}

function stateChanges(latest: Record<string, unknown>): string {
  const changes = latest.stateChangesThisTurn;
  if (!Array.isArray(changes) || !changes.length) return "NO MATERIAL STATE CHANGE";
  const lines = changes.map((item) => {
    const change = record(item);
    if (change.field === "materialState" && change.after === "NO_MATERIAL_STATE_CHANGE") {
      return "NO MATERIAL STATE CHANGE";
    }
    const before = printable(change.before);
    const after = printable(change.after);
    return change.before === undefined ? `${printable(change.field)}: ${after}`
      : `${printable(change.field)}: ${before} -> ${after}`;
  });
  return lines.join("\n");
}

export function buildScenarioTestReport(snapshot: ScenarioLabSnapshot): string {
  const active = snapshot.activeScenario;
  if (!active) throw new Error("Prepare a scenario before copying a test report.");
  const state = active.state || {};
  const latest = record(snapshot.turns.at(-1));
  const analysis = snapshot.latestAnalysis;
  const decision = analysis || {};
  const customerValue = record(first(latest, ["customerValue", "customerValueAttention"]));
  const ava = record(latest.avaDiagnostics);
  const style = record(ava.style);
  const persona = record(ava.persona);
  const temporal = record(latest.temporal);
  const time = record(temporal.time);
  const latestCustomer = snapshot.transcript.filter((item) => item.role === "user").at(-1)?.content;
  const latestAva = snapshot.transcript.filter((item) => item.role === "assistant").at(-1)?.content;
  const turnNumber = latest.turnNumber ?? snapshot.turns.length;
  const pick = (paths: string[]) => first({ latest, decision, state, customerValue, ava, style, persona, temporal, time }, paths);
  const section = (title: string, fields: string[]) => `## ${title}\n\n${fields.join("\n\n")}`;
  const simulated = snapshot.simulatedProviderPurchase
    ? `${snapshot.simulatedProviderPurchase.provenance}\nNO REAL FANVUE PURCHASE\n${printable(snapshot.simulatedProviderPurchase.result)}`
    : NOT_PROVIDED;

  return [
    "# SESSION 5 SYNTHETIC TEST REPORT",
    section("Scenario", [
      field("Scenario", `${active.scenario} - ${active.name.replaceAll("_", " ")}`),
      field("Scenario Lifecycle", active.lifecycle),
      field("Scenario Attempt", active.scenarioAttempt),
      field("Synthetic Customer ID", active.syntheticTelegramId),
      field("Economic State", active.economicState),
      field("Turn", turnNumber),
      field("Turn Attempt", latest.turnAttempt),
      field("Language Certification", snapshot.languageCertification),
      field("Transport", snapshot.transport),
    ]),
    section("Starting / Current Customer State", [
      field("Buyer Status", state.buyerStatus), field("Buyer Stage", state.buyerStage),
      field("Value Tier", state.valueTier), field("Purchase Count", state.purchaseCount),
      field("Lifetime Spend", state.lifetimeSpendMinor), field("Ownership", state.ownershipCount),
      field("Retention", state.retentionLifecycle), field("Time-Waster Risk", state.timeWasterRisk),
      field("Attention", state.attentionTier), field("Effort", state.effortMode),
      field("Commercial Momentum", state.commercialMomentum),
      field("Active PurchaseIntent", state.activePurchaseIntent), field("Active Session", state.activeSession),
    ]),
    section("Latest Conversation", [field("Customer", latestCustomer), field("Ava", latestAva)]),
    `### Full Scenario Transcript\n\n${transcript(snapshot)}`,
    section("Latest Turn", [field("Logical Turn", turnNumber), field("Attempt", latest.turnAttempt),
      field("Customer", latestCustomer), field("Ava", latestAva)]),
    section("Retry History", (snapshot.recovery?.history.turnAttempts || []).length
      ? snapshot.recovery!.history.turnAttempts.map((item) => {
        const value = record(item);
        return field(`Turn ${printable(value.logical_turn)} Attempt ${printable(value.turn_attempt)}`,
          `${printable(value.status)}\nAva: ${printable(value.outbound)}`);
      }) : ["No retries recorded."]),
    section("Previous Scenario Attempts", (snapshot.recovery?.history.scenarioAttempts || []).length
      ? snapshot.recovery!.history.scenarioAttempts.map((item) => {
        const value = record(item); return field(`Attempt ${printable(value.scenario_attempt)}`, value.status);
      }) : ["No previous scenario attempts."]),
    `## State Changes This Turn\n\n${stateChanges(latest)}`,
    section("Decision Summary", [
      field("Sales Brain Decision", pick(["latest.systemLogic.decision", "decision.finalSalesDecision.decision"])),
      field("Reason", pick(["latest.systemLogic.reason", "decision.finalSalesDecision.reasonCode"])),
      field("Customer Temperature", pick(["decision.customerTemperature", "decision.customerTemperature.temperature"])),
      field("Commercial Receptiveness", pick(["latest.systemLogic.receptiveness", "decision.commercialReceptiveness"])),
      field("Buying Intent", pick(["decision.buyingIntent", "decision.purchaseCommerceState.buyingIntent"])),
      field("Sexual Engagement", pick(["decision.sexualEngagement"])),
      field("Close Readiness", pick(["decision.closeReadiness"])),
      field("Objection", pick(["latest.systemLogic.objection", "decision.objection"])),
      field("Objection Recovery Strategy", pick(["decision.objectionRecovery.strategy", "decision.objectionRecoveryStrategy"])),
      field("Sales Progression", pick(["latest.systemLogic.progression", "decision.salesProgression"])),
      field("Selected Offering", pick(["latest.systemLogic.offeringSelected", "decision.inventorySelection.selectedOfferingId"])),
      field("Offer Authorized", pick(["decision.policyGate.offerAuthorized", "decision.offerAuthorized"])),
      field("PurchaseIntent", pick(["latest.systemLogic.purchaseIntent", "state.activePurchaseIntent"])),
      field("Verified Purchase", pick(["latest.systemLogic.verifiedPurchase", "decision.purchaseCommerceState.verifiedPurchase"])),
      field("Session Authority", pick(["latest.systemLogic.activeSession", "decision.activeSession", "state.activeSession"])),
    ]),
    section("Customer Value / Attention", [
      field("Buyer Status", state.buyerStatus), field("Buyer Stage", state.buyerStage),
      field("Value Tier", state.valueTier), field("Retention Lifecycle", state.retentionLifecycle),
      field("Retention Priority", pick(["customerValue.retentionPriority", "decision.customerValueAttention.retentionPriority"])),
      field("Time-Waster Risk", state.timeWasterRisk), field("Attention Tier", state.attentionTier),
      field("Effort Mode", state.effortMode), field("Commercial Momentum", state.commercialMomentum),
      field("Buyer Protection", pick(["customerValue.buyerProtection", "decision.customerValueAttention.buyerProtection"])),
      field("Conversation Continuation Value", pick(["customerValue.conversationContinuationValue", "decision.customerValueAttention.conversationContinuationValue"])),
    ]),
    section("Ava Response Quality Diagnostics", [
      field("Persona Runtime", persona), field("Persona Intensity", pick(["persona.intensity", "persona.personaIntensity"])),
      field("Relevant Persona Domains", pick(["persona.relevantDomains", "persona.relevantPersonaDomains"])),
      field("Question Asked", pick(["style.questionAsked", "ava.questionAsked"])),
      field("Question Reason", pick(["style.questionReason", "ava.questionReason"])),
      field("Question Value", pick(["style.questionValue", "ava.questionValue"])),
      field("Manufactured Question Risk", pick(["style.manufacturedQuestionRisk", "ava.manufacturedQuestionRisk"])),
      field("Response Word Count", ava.responseWords), field("Response Character Count", ava.responseChars),
      field("Response Structure", pick(["style.responseStructure", "ava.responseStructure"])),
      field("Paraphrase Risk", pick(["style.paraphraseRisk", "ava.paraphraseRisk"])),
      field("Generic Filler Risk", pick(["style.genericFillerRisk", "ava.genericFillerRisk"])),
      field("Self Disclosure Used", pick(["style.selfDisclosureUsed", "ava.selfDisclosureUsed"])),
      field("Memory Callback Used", pick(["style.memoryCallbackUsed", "ava.memoryCallbackUsed"])),
      field("Style Rewrite Attempted", style.styleRewriteAttempted),
      field("Style Rewrite Reason", style.styleRewriteReason), field("Style Rewrite Outcome", style.styleRewriteOutcome),
      field("Continuity Priority", style.continuityPriority),
      field("Continuity Rewrite Attempted", style.continuityRewriteAttempted),
      field("Continuity Rewrite Outcome", style.continuityRewriteOutcome),
    ]),
    section("Temporal / Pacing / Sleep", [
      field("Ava Timezone", pick(["time.avaTimezone", "time.ava_timezone"])),
      field("Ava Local Time", pick(["time.avaLocalTime", "time.ava_local_time"])),
      field("Daypart", pick(["time.avaDaypart", "time.daypart"])),
      field("Customer Timezone", pick(["time.customerTimezone", "time.customer_timezone"])),
      field("Sleep State", temporal.sleep), field("Pacing Mode", pick(["latest.pacingMode", "decision.pacingMode"])),
      field("Calculated Production Delay", pick(["latest.calculatedProductionDelay", "decision.calculatedProductionDelay"])),
      field("Applied Delay", pick(["latest.appliedDelay", "decision.appliedDelay"])),
      field("Transport Mode", snapshot.transport),
    ]),
    section("Synthetic / Test Commerce", [
      field("Current Offering", pick(["decision.inventorySelection.selectedOfferingId", "latest.systemLogic.offeringSelected"])),
      field("Offering Type", pick(["decision.inventorySelection.offeringType"])),
      field("Authoritative Price", pick(["decision.inventorySelection.authoritativePrice", "decision.currentOffer.price"])),
      field("Selector Reason", pick(["decision.inventorySelection.reason", "decision.inventorySelection.selectorReason"])),
      field("PurchaseIntent ID", state.activePurchaseIntent),
      field("PurchaseIntent Status", pick(["decision.purchaseCommerceState.purchaseIntentStatus"])),
      field("Destination / Link Metadata", pick(["decision.purchaseCommerceState.destination", "decision.currentOffer.destination"])),
      field("Ownership State", state.ownershipCount),
      field("Simulated Provider Purchase State", simulated),
      field("Acknowledgement State", pick(["decision.purchaseCommerceState.acknowledgementState"])),
    ]),
    `## COMPLETE CANONICAL FULL ANALYSIS\n\n${analysis ? JSON.stringify(analysis, null, 2) : "No Full Analysis available yet."}`,
  ].join("\n\n");
}

function diagnosticBlock(title: string, value: unknown): string {
  return `### ${title}\n\n${printable(value)}`;
}

export function buildFullScenarioAnalysisReport(payload: FullScenarioAnalysis): string {
  const safe = redactObserverSnapshot(payload) as FullScenarioAnalysis;
  const scenario = safe.scenario;
  const turns = [...safe.turns].sort((left, right) =>
    left.logicalTurn - right.logicalTurn || left.turnAttempt - right.turnAttempt);
  const turnBlocks = turns.map((turn) => {
    const evidence = turn.evidenceStatus === "MATCHED" ? [
      diagnosticBlock("State", {
        preTurn: turn.preTurnState, final: turn.finalState, changes: turn.stateChanges,
      }),
      diagnosticBlock("Sales Brain", turn.salesBrainFullAnalysis),
      diagnosticBlock("Customer Value / Conversation Investment", {
        customerValueAttention: turn.customerValueAttention,
        conversationInvestment: turn.conversationInvestment,
      }),
      diagnosticBlock("Memory", {
        conversationalMemory: turn.conversationalMemory,
        memoryDiagnostics: turn.memoryDiagnostics,
        note: "No canonical memory write-delta is claimed unless present in these persisted diagnostics.",
      }),
      diagnosticBlock("Time / Sleep", {
        temporalContext: turn.temporalContext, sleep: turn.sleep,
      }),
      diagnosticBlock("Ava Response Quality / Provider", {
        persona: turn.avaPersonaRuntime, style: turn.styleDiagnostics,
        pacing: turn.pacingCalculation, providerDraft: turn.providerDraft,
        rewriteHistory: turn.rewriteHistory, syntheticProvider: turn.syntheticProvider,
      }),
      diagnosticBlock("Commerce", {
        authority: turn.commerceAuthority, diagnostics: turn.commerceDiagnostics,
        purchaseIntent: turn.purchaseIntent, ownership: turn.ownership,
        session: turn.session, syntheticPpvPresentation: turn.syntheticPpvPresentation,
      }),
      diagnosticBlock("Gateway / Safety / Fallbacks", turn.gatewayDiagnostics),
      diagnosticBlock("Behavior / Test Transport", {
        customerBehavioralPhase: record(turn.adaptiveCustomer).behavioral_phase,
        customerState: record(turn.adaptiveCustomer).customer_constraints,
        adaptiveCustomerAudit: turn.adaptiveCustomer,
        behavior: turn.behavior, testTransportResult: turn.testTransportResult,
      }),
    ] : [diagnosticBlock("Rich Evidence", {
      status: turn.evidenceStatus,
      reason: turn.evidenceUnavailableReason,
      attached: false,
    })];
    return [
      `## TURN ${turn.logicalTurn} — ATTEMPT ${turn.turnAttempt} — ${turn.status}`,
      diagnosticBlock("Turn Identity", {
        attemptId: turn.attemptId, checkpointId: turn.checkpointId,
        persistenceTimestamp: turn.persistenceTimestamp,
        evidenceTimestamp: turn.evidenceTimestamp,
        evidenceStatus: turn.evidenceStatus,
      }),
      `### Conversation\n\nCustomer:\n${turn.customer}\n\nAva:\n${turn.ava}`,
      ...evidence,
    ].join("\n\n");
  });
  return [
    "# FULL SCENARIO ANALYSIS",
    diagnosticBlock("Scenario", {
      scenarioId: scenario.scenarioId, name: scenario.name,
      scenarioAttempt: scenario.scenarioAttempt, lifecycle: scenario.lifecycle,
      economicState: scenario.economicState,
      syntheticTelegramId: scenario.syntheticTelegramId,
      databaseName: safe.databaseEnvironment.databaseName,
      databasePurpose: safe.databaseEnvironment.purpose,
      transport: scenario.transport,
      canonicalTurnCount: scenario.canonicalTurnCount,
    }),
    diagnosticBlock("Current Accumulated State", safe.currentAccumulatedState),
    ...turnBlocks,
    diagnosticBlock("Final Accumulated State", safe.finalAccumulatedState),
    diagnosticBlock("Attempt Audit — Metadata Only", safe.attemptAudit),
  ].join("\n\n");
}
