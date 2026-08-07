export type DeveloperNoteSection = {
  heading: string;
  paragraphs?: readonly string[];
  items?: readonly string[];
};

export type DeveloperNote = {
  id: string;
  title: string;
  status: "Planned" | "In Progress" | "Completed" | "Paused";
  dateCreated: string;
  sections: readonly DeveloperNoteSection[];
};

export const developerNotes: readonly DeveloperNote[] = [
  {
    id: "migrating-to-one-canonical-ava",
    title: "Migrating to One Canonical Ava",
    status: "In Progress",
    dateCreated: "August 6, 2026",
    sections: [
      {
        heading: "Purpose",
        paragraphs: ["Establish one reusable, authoritative definition of Ava for every Creator_OS generation workflow."],
      },
      {
        heading: "Problem Statement",
        paragraphs: ["Creator_OS currently contains multiple workflow-specific interpretations of Ava. Identity, body, hair, framing, and provider continuity rules can drift as each workflow evolves independently."],
      },
      {
        heading: "Architectural Goal",
        paragraphs: ["Creator_OS should have exactly one canonical Ava. Every workflow should contribute only creative intent; no workflow should redefine Ava."],
      },
      {
        heading: "Current Phase",
        paragraphs: ["Runtime pipeline comparison. Phase 1 implemented the centralized prompt-contract proof of concept in Creative Direction, but its generated Ava did not visually match Inspire Me. The approach is under investigation and Inspire Me remains the visual gold standard."],
      },
      {
        heading: "Completed Work",
        items: [
          "Identified the complete Ava definition used by the Inspire Me generation path.",
          "Created a centralized, provider-neutral Canonical Ava identity contract.",
          "Separated identity responsibilities from scene, activity, wardrobe, pose, location, lighting, expression, and editorial variation.",
          "Integrated Canonical Ava into the Creative Direction enhancement flow before prompt planning.",
          "Observed that the Phase 1 Creative Direction result did not visually match the preferred Inspire Me Ava.",
          "Added temporary, correlated runtime diagnostics for both workflows without changing generation behavior.",
        ],
      },
      {
        heading: "Remaining Work",
        items: [
          "Complete a controlled runtime comparison using the same creative intent where needed.",
          "Identify the first meaningful divergence and approve the smallest corrective change.",
          "Do not migrate any additional workflow until the runtime differences are understood.",
        ],
      },
      {
        heading: "Next Milestone",
        paragraphs: ["Identify the first meaningful runtime divergence between Inspire Me and Creative Direction, then approve the smallest evidence-supported corrective change before resuming migration."],
      },
      {
        heading: "Future Migration Plan",
        items: [
          "Migrate Prompt Workshop.",
          "Migrate Canonical Prompt Planner.",
          "Migrate Explicit Content.",
          "Migrate Photoshoot Studio.",
          "Migrate Edit Studio.",
          "Migrate Generation Library.",
          "Migrate remaining generation workflows until all workflows supply creative intent only.",
        ],
      },
    ],
  },
];
