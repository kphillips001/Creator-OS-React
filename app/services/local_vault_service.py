from pathlib import Path

from app.config import settings


class LocalVaultService:
    """
    Resolves and validates the local CMS workspace.

    This service owns folder structure only. It does not move media,
    write database rows, or change existing CMS upload behavior.
    """

    ENV_VAR = "CMS_ROOT"

    REQUIRED_DIRECTORIES = (
        "vault",
        "vault/originals",
        "vault/originals/images",
        "vault/originals/videos",
        "vault/thumbnails",
        "vault/blurred",
        "vault/transcoded",
        "vault/temp",
        "exports",
        "exports/fanvue",
        "exports/telegram",
        "exports/archive",
        "logs",
        "backups",
    )

    def __init__(self, cms_root: str | Path | None = None):
        self._cms_root = self.resolve_cms_root(cms_root)

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def resolve_cms_root(cls, cms_root: str | Path | None = None) -> Path:
        configured_root = cms_root or settings.CMS_ROOT
        root = Path(configured_root).expanduser()

        if not root.is_absolute():
            root = cls.project_root() / root

        return root.resolve()

    @property
    def cms_root(self) -> Path:
        return self._cms_root

    def path(self, relative_path: str = "") -> Path:
        return (self.cms_root / relative_path).resolve()

    def canonical_paths(self) -> dict[str, Path]:
        paths = {"cms_root": self.cms_root}

        for relative_path in self.REQUIRED_DIRECTORIES:
            key = relative_path.replace("/", "_")
            paths[key] = self.path(relative_path)

        return paths

    def create_structure(self) -> dict[str, Path]:
        self.cms_root.mkdir(parents=True, exist_ok=True)

        for relative_path in self.REQUIRED_DIRECTORIES:
            self.path(relative_path).mkdir(parents=True, exist_ok=True)

        return self.canonical_paths()

    def validate_structure(self) -> bool:
        missing_paths = [
            path
            for path in self.canonical_paths().values()
            if not path.is_dir()
        ]

        if missing_paths:
            missing = ", ".join(str(path) for path in missing_paths)
            raise FileNotFoundError(
                f"CMS workspace is missing required folders: {missing}"
            )

        return True

    def initialize(self) -> dict[str, Path]:
        paths = self.create_structure()
        self.validate_structure()
        return paths
