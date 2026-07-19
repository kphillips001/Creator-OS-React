import { Navigate, createBrowserRouter } from "react-router-dom";

import { PlaceholderPage } from "../../features/placeholder/PlaceholderPage";
import { ContentStudioPage } from "../../features/content-studio/ContentStudioPage";
import { GenerationLibraryPage } from "../../features/generation-library/GenerationLibraryPage";
import { EditStudioPage } from "../../features/edit-studio/EditStudioPage";
import { VersionHistoryPage } from "../../features/version-history/VersionHistoryPage";
import { PostedContentPage } from "../../features/posted-content/PostedContentPage";
import { ArchivePage } from "../../features/archive/ArchivePage";
import { RemovedContentPage } from "../../features/removed-content/RemovedContentPage";
import { StoryStudioPage } from "../../features/story-studio/StoryStudioPage";
import { PhotoshootPage } from "../../features/photoshoot/PhotoshootPage";
import { ReferenceLibraryPage } from "../../features/reference-library/ReferenceLibraryPage";
import { AssetLibraryPage } from "../../features/asset-library/AssetLibraryPage";
import { BusinessAssetsPage } from "../../features/business-assets/BusinessAssetsPage";
import { BusinessProductsPage } from "../../features/business-products/BusinessProductsPage";
import { BusinessCustomersPage } from "../../features/business-customers/BusinessCustomersPage";
import { BusinessSalesPage } from "../../features/business-sales/BusinessSalesPage";
import { BusinessOperationsPage } from "../../features/business-operations/BusinessOperationsPage";
import { TestChatPage } from "../../features/test-chat/TestChatPage";
import { NotFoundPage } from "../../features/not-found/NotFoundPage";
import { AppShell } from "../layout/AppShell";
import { allNavigationItems } from "../navigation/navigation";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <Navigate to="/library/generations" replace />,
      },
      ...allNavigationItems
        .filter(
          (item) =>
            item.path !== "/library/generations" &&
            item.path !== "/studio/content" &&
            item.path !== "/content/edit" &&
            item.path !== "/content/photoshoot" &&
            item.path !== "/content/story" &&
            item.path !== "/library/references" &&
            item.path !== "/library/assets" &&
            item.path !== "/system/archive" &&
            item.path !== "/developer/test-chat" &&
            item.path !== "/business/assets" &&
            item.path !== "/business/products" &&
            item.path !== "/business/customers" &&
            item.path !== "/business/sales" &&
            item.path !== "/business/operations",
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
        path: "/library/generations",
        element: <GenerationLibraryPage />,
      },
      {
        path: "/business/assets",
        element: <BusinessAssetsPage />,
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
        path: "/system/archive",
        element: <ArchivePage />,
      },
      {
        path: "/system/archive/edited",
        element: <VersionHistoryPage />,
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
