# Ava Runtime Pipeline Comparison — 2026-08-06

## Executive conclusion

The persisted evidence does **not** show an Ava identity-reference, render-lock, render-policy, provider, or payload-schema difference between the compared runs. Both used canonical reference asset `93`, the same hosted reference URL, Seedream 5.0 Pro, `CONTENT_SPICY`, the same premium prompt builder, and one identical final identity/body lock.

The first meaningful divergence is upstream creative input structure: Inspire Me supplied a six-direction autonomous collection; Creative Direction supplied one operator concept plus an LLM-rewritten enhancement. That difference changed scene, body orientation, gaze, and expression before prompt planning.

The strongest verified facial amplifier occurs at provider time. The Creative Direction planned prompt requested a `quiet candid expression`, but deterministic expression variation appended a mandatory `laughing naturally, caught mid-laugh` profile. The Inspire Me comparison prompt received `playful expression, teasing grin`. This late instruction materially changes facial musculature and is the direct evidence-supported source of exaggerated smiling.

`CanonicalAvaService` duplicated identity/body/framing information in the enhancer context and changed instruction ordering, but its block did not survive verbatim into the final provider prompt, did not duplicate the final render lock, and did not change policy or references. The historical pair cannot prove that service alone caused the visual regression because the scenes were not controlled.

## Evidence pair

- Preferred Inspire Me: `generation_job_516d8a50ce4e427c81a14c2e7af1b682`, completed `2026-08-06T15:47:59.335927`, six successful outputs.
- Post-Phase-1 Creative Direction: `generation_job_0083201f88f84d649a9cb5e2536631f2`, completed `2026-08-06T17:48:41.114621`, five successful outputs.

The older Creative Direction job lacks persisted `workflow_origin`; it is identified from its `17:43` Creative Direction preview/provider plans and `[ORIGINAL USER TAGS] / [ENHANCED SUGGESTIONS]` lineage. New diagnostics persist the origin explicitly.

## Runtime paths

### Inspire Me

`Inspire Me button → POST /content-studio/inspire → AutonomousInspirationEngine → six private directions → ContentStudioGenerationService → canonical premium planner → premium render locks → GenerationEngine → Seedream provider expression modification → Seedream payload`

### Creative Direction

`Creative Concept → CanonicalAvaService block + CreatorAware context → ManualCreativeConceptEnhancementService → enhanced suggestions → prompt preview/canonical premium planner → premium render locks → ContentStudioGenerationService provider-ready plan → GenerationEngine → Seedream provider expression modification → Seedream payload`

## Stage-by-stage runtime diff

| Stage | Inspire Me value | Creative Direction value | Difference | Likely visual consequence |
|---|---|---|---|---|
| 1. Workflow origin | Persisted `autonomous_inspiration`. | Historically absent; verified from Creative Direction lineage. Future runs persist `manual_creative_concept`. | Metadata attribution gap only. | No direct render effect. |
| 2. Initial creative input | Six autonomous directions. First is an upright, mid-stride coastal-boardwalk moment. | `bikini, beach, lying on towel, golden hour`. | Collection versus one reclining concept; motion and body orientation differ immediately. | Upright moving subject versus side-lying subject changes face angle, crop, and visible proportions. |
| 3. Ava/creator context | Autonomous brief used Creator Intelligence, Social Creative Direction, World Model, and Creative Intelligence. Historical full brief was not persisted. | Creator-aware wrapper plus the complete new Canonical Ava block. Historical full request was not persisted. | Creative Direction gained an additional identity/body/framing contract inside an LLM enhancer. | Possible enhancer bias; isolated effect is not provable historically. New diagnostics capture it. |
| 4. Enhanced creative intent | Six directions returned directly from Autonomous Inspiration. | Added side-lying posture, hair fanned around shoulders, one arm under head, ocean angle, and `quiet candid expression`. | The enhancer rewrote presentation details, though not the immutable input tags. | Establishes a different pose, gaze, hair placement, and facial intent before planning. |
| 5. Prompt-plan input | Joined autonomous directions; `premium_teaser`; count 6. | Labeled original tags plus enhanced suggestions; `premium_teaser`; count 5. | Different structure and batch context. | Planner emphasis and variation context differ. |
| 6. PromptPlan output | First unlocked variation: 1,035 characters; mid-stride; soft smile; relaxed off-camera glance; medium-close waist-up. | First unlocked variation: 960 characters; side-lying; quiet candid expression; medium-close waist-up. | Same core identity vocabulary, different pose/gaze/expression. | Facial presentation and body geometry diverge. |
| 7. Before render locks | Persisted plan `prompt_plan_62002f3baad34d2ab7cb6e4c604c783c`; no lock marker. | Persisted preview plan `prompt_plan_10ede11b2e47446da223e3124a44e0b2`; no lock marker. | Both use the canonical Seedream premium planner. | No separate identity-planner path found. |
| 8. After render locks | First variation 6,875 characters; one Provider Optimization block and one final body lock. | First variation 6,800 characters; one Provider Optimization block and one final body lock. | Lock implementation and count match; no duplicate final lock. | Equivalent final identity/body enforcement. |
| 9. GenerationRequest | Seedream image-to-image; asset 93; six images. | Seedream image-to-image; asset 93; five images. | Only count and prompt content differ. | Count has no per-image identity consequence. |
| 10. Render policy | `CONTENT_SPICY`. | `CONTENT_SPICY`. | None. | Policy does not explain the mismatch. |
| 11. Ordered references | One reference resolving to `https://i.ibb.co/bjXLcPcP/93.jpg`. | Same single reference URL. | None. | Both condition on the same Ava identity image. |
| 12. Final provider prompt | Historical payload not stored. Exact deterministic code path selects `playful expression, teasing grin, amused smile, casual creator-photo energy`. | Historical payload not stored. Exact deterministic code path selects `laughing naturally, caught mid-laugh, genuine happiness, spontaneous camera-roll moment`. | Provider-time expression hash produces a mandatory profile that contradicts the manual plan’s quiet expression. | Direct facial divergence and exaggerated smile. New diagnostics persist the actual prompt. |
| 13. Final Seedream payload | Prompt + one asset-93 reference + PNG. | Same schema, reference, and format; different prompt text. | Schema and identity input match. | Remaining output difference is prompt semantics, chiefly pose and final expression. |

## First meaningful divergence and amplifiers

1. **First divergence:** workflow input structure and creative presentation. Inspire Me provides a balanced six-direction collection; Creative Direction sends one concept through an enhancer that adds pose, gaze, hair placement, and expression.
2. **Planner amplification:** those presentation differences become concrete prompt clauses while the identity/body contract remains substantially the same.
3. **Provider amplification:** the full prompt hash selects a different mandatory expression. In the manual run it changes `quiet candid` into `laughing naturally`.

## Root-cause answers

1. **Is CanonicalAvaService causing or worsening the bad output?** It definitely duplicates identity/body/framing concepts at the enhancer-context stage and changes ordering. There is no evidence it changes the final reference, locks, policy, or payload schema. Its isolated visual causality is not proven by the non-controlled historical pair.
2. **Different prompt-planning path?** Both ultimately use the canonical Seedream premium planner. Creative Direction adds a separate enhancement and preview/provider-ready-plan sequence before generation; Inspire Me plans directly from its private directions.
3. **Different input structure?** Yes. Six autonomous directions versus labeled original tags plus one enhanced narrative.
4. **Same builder, locks, policy, provider, references, schema?** Yes for this pair.
5. **Materially different final prompt?** Yes: scene, pose, gaze, and provider-selected expression differ.
6. **Duplicated or contradicted identity/body/framing rules?** Duplicated in the Creative Direction enhancer context, not duplicated in the persisted final lock. No final identity/body contradiction was found. The clear contradiction is expression: quiet/candid upstream versus mandatory laughing downstream.
7. **Source of exaggerated smiling?** Provider-time expression variation. It is deterministically selected from the complete prompt and overrides the upstream quiet-expression intent with `laughing naturally`.

## Smallest recommended fix

Do not migrate another workflow and do not broaden Canonical Ava yet.

The smallest output-correcting change is to constrain provider-time expression variation so it cannot contradict an explicit expression already present in the planned prompt. For this recorded Creative Direction run, `quiet candid expression` should have remained authoritative instead of being replaced by the hash-selected laughing profile.

Separately, keep `CanonicalAvaService` preserved but remove it from the LLM enhancement step when the corrective change is approved. If centralized later, centralize only the final identity/body/framing contract at the deterministic planning/render boundary. Injecting it into creative enhancement duplicates existing creator-aware and premium-planner instructions without replacing the authoritative downstream contract.

No behavioral fix was implemented in this investigation.

## Diagnostic coverage

Future `autonomous_inspiration` and `manual_creative_concept` runs now persist all 13 stages to `data/developer_diagnostics/generation_request_traces.json`. A shared trace ID follows manual enhancement, preview, generation, and provider payload creation; Inspire Me uses its operation/run ID. Secret-like keys are recursively redacted, and HTTP authorization headers are never supplied to the diagnostic.
