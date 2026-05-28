from abc import ABC, abstractmethod


class PackageManager(ABC):
    @abstractmethod
    def export(self) -> dict[str, list[str]]:
        """Returns a dict of category → list of package names."""
        ...

    @abstractmethod
    def diff(self, other: dict[str, list[str]]) -> dict[str, list[str]]:
        """Returns {"missing": [...], "extra": [...]} relative to other."""
        ...

    @abstractmethod
    def install(self, packages: list[str]) -> None:
        ...

    @abstractmethod
    def uninstall(self, packages: list[str]) -> None:
        ...

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        ...

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        ...
