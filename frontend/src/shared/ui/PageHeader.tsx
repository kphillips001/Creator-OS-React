import "./shared-ui.css";

type PageHeaderProps = {
  title: string;
  description: string;
};

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        <p className="page-header__eyebrow">Creative workflow</p>
        <h1>{title}</h1>
        <p className="page-header__description">{description}</p>
      </div>
    </header>
  );
}
