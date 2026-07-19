import {
  Aperture,
  Archive,
  Bot,
  BookOpen,
  Camera,
  Clapperboard,
  CircleGauge,
  Code2,
  MessagesSquare,
  Image,
  Library,
  Paintbrush,
  Send,
  Settings,
  Sparkles,
  BriefcaseBusiness,
  Boxes,
  Users,
  BadgeDollarSign,
  Activity,
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
    label: "Content Creation",
    items: [
      {
        label: "Generation Library",
        path: "/library/generations",
        icon: Image,
        description:
          "Review and organize generated creative outputs.",
      },
      {
        label: "Content Studio",
        path: "/studio/content",
        icon: Sparkles,
        description:
          "Create original content through a focused suite of creative tools.",
      },
      {
        label: "Edit Studio",
        path: "/content/edit",
        icon: Paintbrush,
        description: "Refine and transform creative media.",
      },
      {
        label: "Photoshoot Studio",
        path: "/content/photoshoot",
        icon: Camera,
        description:
          "Direct persistent photoshoot sessions from seed image to final set.",
      },
      {
        label: "Story Studio",
        path: "/content/story",
        icon: BookOpen,
        description: "Coming Soon",
      },
      {
        label: "Video Studio",
        path: "/studio/video",
        icon: Clapperboard,
        description: "Create and refine video content.",
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
        label: "Assets",
        path: "/business/assets",
        icon: BriefcaseBusiness,
        description: "Monitor approved assets from intelligence through commerce readiness.",
      },
      {
        label: "Products",
        path: "/business/products",
        icon: Boxes,
        description: "Build and manage the offers available to the Sales Agent.",
      },
      {
        label: "Customers",
        path: "/business/customers",
        icon: Users,
        description: "Understand customer relationships, ownership, and buying history.",
      },
      {
        label: "Sales",
        path: "/business/sales",
        icon: BadgeDollarSign,
        description: "Review sales activity, recommendations, and commercial outcomes.",
      },
      {
        label: "Operations",
        path: "/business/operations",
        icon: Activity,
        description: "Monitor business workflows, fulfillment, and items needing attention.",
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
          "Coordinate content queues, destinations, and publishing history.",
      },
    ],
  },
  {
    label: "AI",
    items: [
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
    ],
  },
  {
    label: "Developer Tools",
    items: [
      {
        label: "Test Chat",
        path: "/developer/test-chat",
        icon: MessagesSquare,
        description: "Exercise the Sales Agent brain with a synthetic customer.",
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
