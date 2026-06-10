"""Motor profesional (modflow-setup) y version stamping de inputs."""

from yaku.setup.mfsetup_runner import build_from_yaml, is_available
from yaku.setup.stamp import stamp_inputs

__all__ = ["stamp_inputs", "build_from_yaml", "is_available"]
