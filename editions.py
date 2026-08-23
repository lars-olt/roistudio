"""Build-edition metadata shared by startup, UI, and packaging."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Edition:
    key: str
    product_name: str
    algorithm_enabled: bool
    settings_name: str


FULL = Edition(
    key="full",
    product_name="ROIStudio",
    algorithm_enabled=True,
    settings_name="ROIStudio",
)

LITE = Edition(
    key="lite",
    product_name="ROIStudio Lite",
    algorithm_enabled=False,
    settings_name="ROIStudio Lite",
)

