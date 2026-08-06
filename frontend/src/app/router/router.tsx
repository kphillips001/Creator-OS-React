import { Navigate, createBrowserRouter } from "react-router-dom";

import { PlaceholderPage } from "../../features/placeholder/PlaceholderPage";
import { ContentStudioPage } from "../../features/content-studio/ContentStudioPage";
import { GenerationLibraryPage } from "../../features/generation-library/GenerationLibraryPage";
import { EditStudioPage } from "../../features/edit-studio/EditStudioPage";
import { VersionHistoryPage } from "../../features/version-history/VersionHistoryPage";
import { PostedContentPage } from "../../features/posted-content/PostedContentPage";
import { ArchivePage } from "../../features/archive/ArchivePage";
import { PromptWorkshopArchivePage } from "../../features/archive/PromptWorkshopArchivePage";
import { RemovedContentPage } from "../../features/removed-content/RemovedContentPage";
import { StoryStudioPage } from "../../features/story-studio/StoryStudioPage";
import { PhotoshootPage } from "../../features/photoshoot/PhotoshootPage";
import { PhotoshootGalleryPage } from "../../features/photoshoot-gallery/PhotoshootGalleryPage";
import { ReferenceLibraryPage } from "../../features/reference-library/ReferenceLibraryPage";
import { AssetLibraryPage } from "../../features/asset-library/AssetLibraryPage";
import { BusinessAssetsPage } from "../../features/business-assets/BusinessAssetsPage";
import { BusinessProductsPage } from "../../features/business-products/BusinessProductsPage";
import { BusinessCustomersPage } from "../../features/business-customers/BusinessCustomersPage";
import { BusinessSalesPage } from "../../features/business-sales/BusinessSalesPage";
import { BusinessOperationsPage } from "../../features/business-operations/BusinessOperationsPage";
import { AvailableInventoryPage } from "../../features/available-inventory/AvailableInventoryPage";
import { CommercialOfferingsPage } from "../../features/commercial-offerings/CommercialOfferingsPage";
import { CommercialAdministrationPage } from "../../features/commercial-administration/CommercialAdministrationPage";
import { TestChatPage } from "../../features/test-chat/TestChatPage";
import { CommerceSalesExplorerPage } from "../../features/commerce-sales-explorer/CommerceSalesExplorerPage";
import { FanvueApiExplorerPage } from "../../features/fanvue-api-explorer/FanvueApiExplorerPage";
import { FanvueWebhookMonitorPage } from "../../features/fanvue-webhook-monitor/FanvueWebhookMonitorPage";
import { CustomerCommercePage } from "../../features/customer-commerce/CustomerCommercePage";
import { PurchaseIntentsPage } from "../../features/purchase-intents/PurchaseIntentsPage";
import { CustomerSalesBrainPage } from "../../features/customer-sales-brain/CustomerSalesBrainPage";
import { CommercialOfferingSelectorPage } from "../../features/offering-selector/CommercialOfferingSelectorPage";
import { CommercePage } from "../../features/commerce/CommercePage";
import { CommerceLearningPage } from "../../features/commerce-learning/CommerceLearningPage";
import { RecommendationDiagnosticsPage } from "../../features/recommendation-diagnostics/RecommendationDiagnosticsPage";
import { CreatorIntelligencePage } from "../../features/creator-intelligence/CreatorIntelligencePage";
import { CreatorPersonalityPage } from "../../features/creator-personality/CreatorPersonalityPage";
import { SocialCreativeDirectionPage } from "../../features/social-creative-direction/SocialCreativeDirectionPage";
import { CreatorLifestylePage } from "../../features/creator-lifestyle/CreatorLifestylePage";
import { CreatorWorldModelPage } from "../../features/creator-world-model/CreatorWorldModelPage";
import { AvaCoachPage } from "../../features/ava-coach/AvaCoachPage";
import { NotFoundPage } from "../../features/not-found/NotFoundPage";
import { AdministrationPage } from "../../features/administration/AdministrationPage";
import { ProviderConnectionsPage } from "../../features/administration/ProviderConnectionsPage";
import { AppShell } from "../layout/AppShell";
import { allNavigationItems } from "../navigation/navigation";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <Navigate to="/home" replace />,
      },
      ...allNavigationItems
        .filter(
          (item) =>
            item.path !== "/home" &&
            item.path !== "/creator/personality" &&
            item.path !== "/creator/social-creative-direction" &&
            item.path !== "/creator/lifestyle" &&
            item.path !== "/creator/world-model" &&
            item.path !== "/library/generations" &&
            item.path !== "/inventory/available" &&
            item.path !== "/library/photoshoots" &&
            item.path !== "/studio/content" &&
            item.path !== "/content/edit" &&
            item.path !== "/content/photoshoot" &&
            item.path !== "/content/story" &&
            item.path !== "/library/references" &&
            item.path !== "/library/assets" &&
            item.path !== "/system/archive" &&
            item.path !== "/developer/test-chat" &&
            item.path !== "/developer/commerce-learning" &&
            item.path !== "/developer/recommendations" &&
            item.path !== "/developer/commerce-sales" &&
            item.path !== "/developer/fanvue-api-explorer" &&
            item.path !== "/developer/fanvue-webhook-monitor" &&
            item.path !== "/developer/customer-commerce" &&
            item.path !== "/developer/purchase-intents" &&
            item.path !== "/developer/customer-sales-brain" &&
            item.path !== "/developer/offering-selector" &&
            item.path !== "/business/assets" &&
            item.path !== "/business/commerce-library" &&
            item.path !== "/commerce/offerings" &&
            item.path !== "/commercial-administration" &&
            item.path !== "/commerce" &&
            item.path !== "/business/products" &&
            item.path !== "/business/customers" &&
            item.path !== "/business/sales" &&
            item.path !== "/business/operations" &&
            item.path !== "/administration" &&
            item.path !== "/agents/ava-coach",
        )
        .map((item) => ({
          path: item.path,
          element: (
            <PlaceholderPage
              title={item.label}
              description={item.description}
            />
          ),
        })),
      {
        path: "/home",
        element: <CreatorIntelligencePage />,
      },
      {
        path: "/creator/personality",
        element: <CreatorPersonalityPage />,
      },
      {
        path: "/creator/social-creative-direction",
        element: <SocialCreativeDirectionPage />,
      },
      {
        path: "/creator/lifestyle",
        element: <CreatorLifestylePage />,
      },
      {
        path: "/creator/world-model",
        element: <CreatorWorldModelPage />,
      },
      {
        path: "/agents/ava-coach",
        element: <AvaCoachPage />,
      },
      {
        path: "/studio/content",
        element: <ContentStudioPage />,
      },
      {
        path: "/content/edit",
        element: <EditStudioPage />,
      },
      {
        path: "/content/story",
        element: <StoryStudioPage />,
      },
      {
        path: "/content/photoshoot",
        element: <PhotoshootPage />,
      },
      {
        path: "/library/references",
        element: <ReferenceLibraryPage />,
      },
      {
        path: "/library/assets",
        element: <AssetLibraryPage />,
      },
      {
        path: "/library/bundles",
        element: <PlaceholderPage title="Bundle Library" description="Create and manage reusable content Bundles." />,
      },
      {
        path: "/library/generations",
        element: <GenerationLibraryPage />,
      },
      {
        path: "/inventory/available",
        element: <AvailableInventoryPage />,
      },
      {
        path: "/library/photoshoots",
        element: <PhotoshootGalleryPage />,
      },
      {
        path: "/business/commerce-library",
        element: <BusinessAssetsPage />,
      },
      {
        path: "/commercial-administration",
        element: <CommercialAdministrationPage />,
      },
      {
        path: "/commerce",
        element: <CommercePage />,
      },
      {
        path: "/commerce/offerings",
        element: <CommercialOfferingsPage />,
      },
      {
        path: "/business/assets",
        element: <Navigate to="/business/commerce-library" replace />,
      },
      {
        path: "/business/products",
        element: <BusinessProductsPage />,
      },
      {
        path: "/business/customers",
        element: <BusinessCustomersPage />,
      },
      {
        path: "/business/sales",
        element: <BusinessSalesPage />,
      },
      {
        path: "/business/operations",
        element: <BusinessOperationsPage />,
      },
      {
        path: "/developer/test-chat",
        element: <TestChatPage />,
      },
      {
        path: "/developer/commerce-learning",
        element: <CommerceLearningPage />,
      },
      {
        path: "/developer/recommendations",
        element: <RecommendationDiagnosticsPage />,
      },
      {
        path: "/developer/commerce-sales",
        element: <CommerceSalesExplorerPage />,
      },
      {
        path: "/developer/fanvue-api-explorer",
        element: <FanvueApiExplorerPage />,
      },
      {
        path: "/developer/fanvue-webhook-monitor",
        element: <FanvueWebhookMonitorPage />,
      },
      {
        path: "/developer/customer-commerce",
        element: <CustomerCommercePage />,
      },
      {
        path: "/developer/purchase-intents",
        element: <PurchaseIntentsPage />,
      },
      {
        path: "/developer/customer-sales-brain",
        element: <CustomerSalesBrainPage />,
      },
      {
        path: "/developer/offering-selector",
        element: <CommercialOfferingSelectorPage />,
      },
      {
        path: "/administration",
        element: <AdministrationPage />,
      },
      {
        path: "/administration/providers",
        element: <ProviderConnectionsPage />,
      },
      {
        path: "/administration/:section",
        element: <PlaceholderPage title="Administration" description="This administration capability is not available in React yet." />,
      },
      {
        path: "/system/archive",
        element: <ArchivePage />,
      },
      {
        path: "/system/archive/edited",
        element: <VersionHistoryPage />,
      },
      {
        path: "/system/archive/prompts",
        element: <PromptWorkshopArchivePage />,
      },
      {
        path: "/system/archive/published",
        element: <PostedContentPage />,
      },
      {
        path: "/system/archive/removed",
        element: <RemovedContentPage />,
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
]);
