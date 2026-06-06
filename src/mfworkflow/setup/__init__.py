"""Motor profesional (modflow-setup) y version stamping de inputs."""

from mfworkflow.setup.mfsetup_runner import build_from_yaml, is_available
from mfworkflow.setup.stamp import stamp_inputs

__all__ = ["stamp_inputs", "build_from_yaml", "is_available"]
