import subprocess
from .base import PackageManager


def _which(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def _detect_aur_helper() -> str | None:
    for helper in ("yay", "paru"):
        if _which(helper):
            return helper
    return None


class PacmanManager(PackageManager):
    @classmethod
    def name(cls) -> str:
        return "pacman"

    @classmethod
    def is_available(cls) -> bool:
        return _which("pacman")

    def export(self) -> dict[str, list[str]]:
        explicit = subprocess.run(["pacman", "-Qqen"], capture_output=True, text=True, check=True).stdout.strip().splitlines()
        aur = subprocess.run(["pacman", "-Qqem"], capture_output=True, text=True, check=True).stdout.strip().splitlines()
        return {"explicit": explicit, "aur": aur}

    def diff(self, other: dict[str, list[str]]) -> dict[str, list[str]]:
        current = set(self.export().get("explicit", []) + self.export().get("aur", []))
        other_all = set(other.get("explicit", []) + other.get("aur", []))
        return {"missing": sorted(other_all - current), "extra": sorted(current - other_all)}

    def install(self, packages: list[str]) -> None:
        if packages:
            subprocess.run(["sudo", "pacman", "-S", "--needed", *packages], check=True)


class AurManager(PackageManager):
    @classmethod
    def name(cls) -> str:
        return "aur"

    @classmethod
    def is_available(cls) -> bool:
        return _detect_aur_helper() is not None

    def export(self) -> dict[str, list[str]]:
        aur = subprocess.run(["pacman", "-Qqem"], capture_output=True, text=True, check=True).stdout.strip().splitlines()
        return {"aur": aur}

    def diff(self, other: dict[str, list[str]]) -> dict[str, list[str]]:
        current = set(self.export().get("aur", []))
        other_set = set(other.get("aur", []))
        return {"missing": sorted(other_set - current), "extra": sorted(current - other_set)}

    def install(self, packages: list[str]) -> None:
        helper = _detect_aur_helper()
        if not helper:
            raise RuntimeError("No AUR helper found (yay or paru)")
        if packages:
            subprocess.run([helper, "-S", "--needed", *packages], check=True)


class PipManager(PackageManager):
    @classmethod
    def name(cls) -> str:
        return "pip"

    @classmethod
    def is_available(cls) -> bool:
        return _which("pip")

    def export(self) -> dict[str, list[str]]:
        result = subprocess.run(["pip", "list", "--format=freeze"], capture_output=True, text=True, check=True)
        return {"packages": result.stdout.strip().splitlines()}

    def diff(self, other: dict[str, list[str]]) -> dict[str, list[str]]:
        current = set(self.export().get("packages", []))
        other_set = set(other.get("packages", []))
        return {"missing": sorted(other_set - current), "extra": sorted(current - other_set)}

    def install(self, packages: list[str]) -> None:
        if packages:
            subprocess.run(["pip", "install", *packages], check=True)


class NpmManager(PackageManager):
    @classmethod
    def name(cls) -> str:
        return "npm"

    @classmethod
    def is_available(cls) -> bool:
        return _which("npm")

    def export(self) -> dict[str, list[str]]:
        result = subprocess.run(["npm", "list", "-g", "--depth=0", "--parseable"], capture_output=True, text=True, check=True)
        packages = [line.strip().split("/")[-1] for line in result.stdout.strip().splitlines() if line.strip()]
        return {"packages": packages}

    def diff(self, other: dict[str, list[str]]) -> dict[str, list[str]]:
        current = set(self.export().get("packages", []))
        other_set = set(other.get("packages", []))
        return {"missing": sorted(other_set - current), "extra": sorted(current - other_set)}

    def install(self, packages: list[str]) -> None:
        if packages:
            subprocess.run(["npm", "install", "-g", *packages], check=True)


def get_available_managers() -> list[PackageManager]:
    classes = [PacmanManager, AurManager, PipManager, NpmManager]
    return [cls() for cls in classes if cls.is_available()]
