import {
  Aperture,
  Archive,
  Bot,
  BookOpen,
  Camera,
  Clapperboard,
  Film,
  CircleGauge,
  Code2,
  MessagesSquare,
  Image,
  Library,
  Paintbrush,
  Send,
  Settings,
  Sparkles,
  Users,
  BadgeDollarSign,
  Activity,
  ShoppingBasket,
  ShieldCheck,
  ScanSearch,
  RadioTower,
  RotateCw,
  UserRoundSearch,
  UserRound,
  ListChecks,
  BrainCircuit,
  GraduationCap,
  ChartNoAxesCombined,
  Instagram,
  ListFilter,
  type LucideIcon,
} from "lucide-react";

export type NavigationItem = {
  label: string;
  path: string;
  icon: LucideIcon;
  description: string;
};

export type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};

export const navigationGroups: NavigationGroup[] = [
  {
    label: "Studios",
    items: [
      {
        label: "Content Studio",
        path: "/studio/content",
        icon: Sparkles,
        description:
          "Create original content through a focused suite of creative tools.",
      },
      {
        label: "Photoshoot Studio",
        path: "/content/photoshoot",
        icon: Camera,
        description:
          "Direct persistent photoshoot sessions from seed image to final set.",
      },
      {
        label: "Video Studio",
        path: "/studio/video",
        icon: Clapperboard,
        description: "Create and refine video content.",
      },
      {
        label: "Edit Studio",
        path: "/content/edit",
        icon: Paintbrush,
        description: "Refine and transform creative media.",
      },
      {
        label: "Regeneration Studio",
        path: "/studio/regeneration",
        icon: RotateCw,
        description: "Create new variations from captured generation recipes.",
      },
    ],
  },
  {
    label: "Libraries",
    items: [
      {
        label: "Generation Library",
        path: "/library/generations",
        icon: Image,
        description: "Review and organize generated creative outputs.",
      },
      {
        label: "Photoshoot Gallery",
        path: "/library/photoshoots",
        icon: Camera,
        description: "Browse completed multi-image Photoshoot sets.",
      },
      {
        label: "Video Gallery",
        path: "/gallery/videos",
        icon: Film,
        description: "Browse and continue completed generated videos.",
      },
      {
        label: "Reference Library",
        path: "/library/references",
        icon: Library,
        description:
          "Curate visual references that guide future creative work.",
      },
      {
        label: "Asset Library",
        path: "/library/assets",
        icon: Archive,
        description: "Manage creative media assets and their lifecycle.",
      },
    ],
  },
  {
    label: "Business",
    items: [
      {
        label: "Overview",
        path: "/home",
        icon: CircleGauge,
        description:
          "Operational priorities, opportunities, and evidence in one executive console.",
      },
      {
        label: "Commerce",
        path: "/commerce",
        icon: BadgeDollarSign,
        description:
          "Author, manage, and publish AI Chat commercial offerings.",
      },
      {
        label: "Customers",
        path: "/business/customers",
        icon: Users,
        description:
          "Understand customer relationships, ownership, and buying history.",
      },
      {
        label: "Sales",
        path: "/business/sales",
        icon: BadgeDollarSign,
        description:
          "Review sales activity, recommendations, and commercial outcomes.",
      },
    ],
  },
  {
    label: "Advanced",
    items: [
      {
        label: "Operations",
        path: "/business/operations",
        icon: Activity,
        description:
          "Monitor business workflows, fulfillment, and items needing attention.",
      },
      {
        label: "Commercial Administration",
        path: "/commercial-administration",
        icon: ShieldCheck,
        description:
          "Operate the creator-scoped commercial platform from one supported workspace.",
      },
    ],
  },
  {
    label: "Publishing",
    items: [
      {
        label: "Publishing",
        path: "/publishing",
        icon: Send,
        description:
          "Publication history and distribution across every platform.",
      },
    ],
  },
  {
    label: "AI",
    items: [
      {
        label: "Ava Coach",
        path: "/agents/ava-coach",
        icon: Sparkles,
        description:
          "Evidence-based conversation coaching for operator review.",
      },
      {
        label: "Creator Agent",
        path: "/agents/creator",
        icon: Bot,
        description:
          "Collaborate with the operational intelligence for creator work.",
      },
      {
        label: "Developer Agent",
        path: "/agents/developer",
        icon: Code2,
        description:
          "Explore architecture and system behavior through a read-only agent.",
      },
      {
        label: "AI Training",
        path: "/agents/ai-training",
        icon: GraduationCap,
        description:
          "Control account-wide conversational guidance used by Creator_OS AI.",
      },
    ],
  },
  {
    label: "Developer Tools",
    items: [
      {
        label: "Test Chat",
        path: "/developer/test-chat",
        icon: MessagesSquare,
        description:
          "Exercise the Sales Agent brain with a synthetic customer.",
      },
      {
        label: "Commerce Learning",
        path: "/developer/commerce-learning",
        icon: BrainCircuit,
        description:
          "Inspect observed customer recommendation preferences and outcomes.",
      },
      {
        label: "Recommendation Diagnostics",
        path: "/developer/recommendations",
        icon: ListFilter,
        description: "Inspect exact ranking traces and observed outcomes.",
      },
      {
        label: "Commerce Sales Explorer",
        path: "/developer/commerce-sales",
        icon: ShoppingBasket,
        description:
          "Inspect the fulfillable offerings currently available to AI Chat.",
      },
      {
        label: "Fanvue API Explorer",
        path: "/developer/fanvue-api-explorer",
        icon: ScanSearch,
        description:
          "Inspect official Fanvue API responses through the authenticated creator connection.",
      },
      {
        label: "Fanvue Webhook Monitor",
        path: "/developer/fanvue-webhook-monitor",
        icon: RadioTower,
        description: "Monitor incoming Fanvue webhook traffic in this process.",
      },
      {
        label: "Customer Commerce",
        path: "/developer/customer-commerce",
        icon: UserRoundSearch,
        description:
          "Inspect read-only customer purchase aggregates and commerce identity state.",
      },
      {
        label: "Purchase Intents",
        path: "/developer/purchase-intents",
        icon: ListChecks,
        description:
          "Inspect read-only offer presentation and payment-reference lifecycle state.",
      },
      {
        label: "Customer Sales Brain",
        path: "/developer/customer-sales-brain",
        icon: BrainCircuit,
        description:
          "Inspect deterministic customer commercial-action decisions.",
      },
      {
        label: "Commercial Offering Selector",
        path: "/developer/offering-selector",
        icon: ListFilter,
        description:
          "Inspect deterministic offering eligibility, exclusions, and selection.",
      },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        label: "Administration",
        path: "/administration",
        icon: ShieldCheck,
        description:
          "Manage provider connections and operational configuration.",
      },
      {
        label: "Personality",
        path: "/creator/personality",
        icon: UserRound,
        description: "Review and edit the canonical creator personality.",
      },
      {
        label: "Social Creative Direction",
        path: "/creator/social-creative-direction",
        icon: Paintbrush,
        description:
          "Maintain the canonical creative vision for public social content.",
      },
      {
        label: "Lifestyle",
        path: "/creator/lifestyle",
        icon: BookOpen,
        description:
          "Maintain the canonical description of the creator's everyday life.",
      },
      {
        label: "World Model",
        path: "/creator/world-model",
        icon: CircleGauge,
        description:
          "Maintain canonical environments, location privacy, and seasonal context.",
      },
      {
        label: "Developer Notes",
        path: "/administration/developer-notes",
        icon: BookOpen,
        description:
          "Review architecture decisions, migrations, and technical debt.",
      },
    ],
  },
  {
    label: "Tools",
    items: [
      {
        label: "AI Developer Notes",
        path: "/tools/ai-training",
        icon: GraduationCap,
        description:
          "Capture implementation notes and ideas for future Creator_OS AI improvements.",
      },
      {
        label: "X Competitor Intelligence",
        path: "/tools/x-intelligence",
        icon: ChartNoAxesCombined,
        description:
          "Track competitors, audience growth, and X market intelligence over time.",
      },
      {
        label: "IG Competitor Intelligence",
        path: "/tools/ig-intelligence",
        icon: Instagram,
        description:
          "Track Instagram competitors and build durable market intelligence over time.",
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        label: "Settings",
        path: "/settings",
        icon: Settings,
        description:
          "Configure Creator_OS preferences, accounts, and connections.",
      },
      {
        label: "Diagnostics",
        path: "/diagnostics",
        icon: CircleGauge,
        description:
          "Review system health, jobs, providers, and operational signals.",
      },
      {
        label: "Archive",
        path: "/system/archive",
        icon: Archive,
        description:
          "Browse Creator_OS history and previously published content.",
      },
    ],
  },
];

export const allNavigationItems = navigationGroups.flatMap(
  (group) => group.items,
);

export const brandIcon = Aperture;
