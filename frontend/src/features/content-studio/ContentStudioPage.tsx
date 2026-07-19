import { ContentStudioHeader } from "./components/ContentStudioHeader";
import { ContentStudioWorkflow } from "./components/ContentStudioWorkflow";
import { useContentStudioContext } from "./hooks/useContentStudioContext";
import "./styles/content-studio.css";

export function ContentStudioPage() {
  const contextState = useContentStudioContext();

  return (
    <section className="content-studio">
      <ContentStudioHeader />
      <ContentStudioWorkflow {...contextState} />
    </section>
  );
}
