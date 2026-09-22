import {describe,expect,it,vi} from "vitest";
import type {ConversationAnalysisResponse} from "./api";
import {conversationAnalysisFilename,downloadConversationAnalysis,sanitizeAnalysisFilenamePart,serializeConversationAnalysisMarkdown} from "./conversationAnalysisDownload";

const analysis:ConversationAnalysisResponse={
  analysisId:"analysis-1",staleState:"CURRENT",
  analysis:{overallQuality:"MATERIAL",conversationSummary:"A very long summary ".repeat(500),operatorSummary:"Review the full evidence.",validatedScope:"CONVERSATION_ONLY",globalRepairCandidate:false,analyzedAt:"2026-09-17T15:00:00Z",schemaVersion:"CONVERSATION_ANALYSIS_V1"},
  findings:[{findingId:"finding-1",targetMessageReference:"telegram:42",severity:"MATERIAL",category:"CONTEXTUAL_RELEVANCE",whatHappened:"The reply missed the current turn.",whyItIsProblematic:"Continuity broke.",rootCauseCategory:"CONTEXT_SELECTION",validatedScope:"CONVERSATION_ONLY",proposedScope:"CONVERSATION_ONLY",confidence:.91,similarCaseCount:0,suggestedCorrection:"Require current-turn relevance.",repairCandidate:false,authorityConflict:false,authoritativeEvidenceSummary:"CURRENT_TURN_MISMATCH"}],
  similarCaseSummary:{similarCaseCount:0,relationshipReferences:["relationship:abc"],searchBasis:"MATCHING_SERVER_FAILURE_SIGNATURE"},
};
const context={personKey:"telegram:2:2:42",displayName:"Jöhnny / Rules:*?",username:"JohnnyXRules",transcript:[{eventKey:"e1",direction:"CUSTOMER" as const,content:"Good morning 😊",timestamp:"2026-09-17T10:00:00-05:00",telegramMessageId:42,messageType:"ORDINARY_CHAT",purchaseIntentId:null},{eventKey:"e2",direction:"AVA" as const,content:"Morning!",timestamp:"2026-09-17T10:01:00-05:00",telegramMessageId:43,messageType:"ORDINARY_CHAT",purchaseIntentId:null}]};

describe("conversation analysis Markdown download",()=>{
  it("serializes every operator-visible section, diagnostics, transcript, unicode, and untruncated text",()=>{
    const markdown=serializeConversationAnalysisMarkdown(analysis,context);
    expect(markdown).toContain("# Creator-OS Chat Analysis");
    expect(markdown).toContain("## Summary");
    expect(markdown).toContain("### Operator Summary");
    expect(markdown).toContain("## Findings");
    expect(markdown).toContain("CURRENT_TURN_MISMATCH");
    expect(markdown).toContain("## Similar Case Diagnostics");
    expect(markdown).toContain("## Analyzed Conversation Context");
    expect(markdown).toContain("Good morning 😊");
    expect(markdown).toContain(analysis.analysis.conversationSummary);
  });
  it("creates a readable Windows-safe filename",()=>{
    expect(sanitizeAnalysisFilenamePart("Jöhnny / Rules:*?")).toBe("johnny-rules");
    expect(conversationAnalysisFilename(analysis,context)).toBe("creator-os-chat-analysis-johnny-rules-2026-09-17.md");
  });
  it("downloads repeatedly from memory without fetch or mutation",()=>{
    const createObjectURL=vi.fn(()=>"blob:test"),revokeObjectURL=vi.fn();
    Object.defineProperty(URL,"createObjectURL",{configurable:true,value:createObjectURL});
    Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:revokeObjectURL});
    const click=vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});
    const fetchSpy=vi.spyOn(globalThis,"fetch");
    downloadConversationAnalysis(analysis,context);downloadConversationAnalysis(analysis,context);
    expect(createObjectURL).toHaveBeenCalledTimes(2);expect(click).toHaveBeenCalledTimes(2);
    expect(revokeObjectURL).toHaveBeenCalledTimes(2);expect(fetchSpy).not.toHaveBeenCalled();
  });
});
