import { PageHeader } from "../../shared/ui/PageHeader";
import { PlaceholderPanel } from "../../shared/ui/PlaceholderPanel";

export type PlaceholderPageDefinition = {
  title: string;
  description: string;
};

export function PlaceholderPage({
  title,
  description,
}: PlaceholderPageDefinition) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <PlaceholderPanel featureName={title} />
    </>
  );
}
