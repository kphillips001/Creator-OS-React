import {
  Aperture,
  Archive,
  BookOpen,
  Camera,
  Clapperboard,
  Film,
  CircleGauge,
  MessagesSquare,
  Image,
  Library,
  Paintbrush,
  Sparkles,
  Activity,
  ShoppingBasket,
  ScanSearch,
  RadioTower,
  RotateCw,
  UserRoundSearch,
  UserRound,
  ListChecks,
  BrainCircuit,
  GraduationCap,
  ChartNoAxesCombined,
  ListFilter,
  SlidersHorizontal,
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
        label: "Chat",
        path: "/business/relationships",
        icon: MessagesSquare,
        description: "Read Ava's Telegram conversations in one operator inbox.",
      },
      {
        label: "Controls",
        path: "/business/controls",
        icon: SlidersHorizontal,
        description: "Control when Ava chats and what she is allowed to sell.",
      },
      {
        label: "Ask Creator_OS",
        path: "/business/ask",
        icon: Sparkles,
        description: "Ask read-only questions about Ava's business.",
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
  {
    label: "Tools",
    items: [
      {
        label: "X Competitor Intelligence",
        path: "/tools/x-intelligence",
        icon: ChartNoAxesCombined,
        description:
          "Track competitors, audience growth, and X market intelligence over time.",
      },
    ],
  },
  {
    label: "Training",
    items: [{
      label: "AI Training",
      path: "/training/ai-training",
      icon: GraduationCap,
      description: "Refine how Ava responds globally and with individual customers.",
    }],
  },
  {
    label: "Administration",
    items: [
      { label: "Ava Configuration", path: "/administration/ava", icon: UserRound, description: "Manage Ava's identity, creative direction, lifestyle, and world." },
      { label: "Ava Rules", path: "/agents/ai-training", icon: GraduationCap, description: "Manage the rules and policies that shape Ava's live behavior." },
      { label: "Provider Connections", path: "/administration/providers", icon: RadioTower, description: "Inspect and authorize account-scoped provider connections." },
      { label: "Developer Notes", path: "/administration/developer-notes", icon: BookOpen, description: "Track Creator_OS coding and implementation work." },
    ],
  },
  {
    label: "Developer Tools",
    items: [
      {
        label: "Operations",
        path: "/business/operations",
        icon: Activity,
        description:
          "Monitor business workflows, fulfillment, and items needing attention.",
      },
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
];

export const allNavigationItems = navigationGroups.flatMap(
  (group) => group.items,
);

export const brandIcon = Aperture;
