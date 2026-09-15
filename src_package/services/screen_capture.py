"""Capture only a configured physical-pixel screen rectangle.

MSS is retained as the fast/default backend. If it returns an all-black frame,
DXcam's Windows Desktop Duplication backend is tried so exclusive-fullscreen
Direct3D applications can still be analysed. Frames remain in memory only.
"""

from dataclasses import dataclass

import mss
import numpy as np

try:  # DXcam is Windows-only; keep imports safe for test and source tooling.
    import dxcam
except ImportError:  # pragma: no cover - exercised on non-Windows hosts
    dxcam = None  # type: ignore[assignment]

from src_package.config import Region

BLANK_CHANNEL_LIMIT = 8


class ScreenRegionError(ValueError):
    """The configured region does not overlap any physical monitor."""


@dataclass(frozen=True, slots=True)
class MonitorGeometry:
    """One physical monitor in the coordinates screen captures use."""

    index: int
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains(self, region: Region) -> bool:
        return (
            self.left <= region.x
            and self.top <= region.y
            and region.x + region.width <= self.right
            and region.y + region.height <= self.bottom
        )

    def overlaps(self, region: Region) -> bool:
        return (
            region.x < self.right
            and region.x + region.width > self.left
            and region.y < self.bottom
            and region.y + region.height > self.top
        )

    def overlap_area(self, region: Region) -> int:
        width = min(region.x + region.width, self.right) - max(region.x, self.left)
        height = min(region.y + region.height, self.bottom) - max(region.y, self.top)
        return max(0, width) * max(0, height)

    def describe(self) -> str:
        return f"monitor {self.index} at ({self.left}, {self.top}) {self.width}x{self.height}"


def _to_geometry(index: int, monitor: dict[str, int]) -> MonitorGeometry:
    return MonitorGeometry(
        index=index,
        left=int(monitor["left"]),
        top=int(monitor["top"]),
        width=int(monitor["width"]),
        height=int(monitor["height"]),
    )


def list_monitors() -> list[MonitorGeometry]:
    """Enumerate the individual monitors, skipping MSS's all-monitors entry."""
    with mss.MSS() as session:
        return [
            _to_geometry(index, monitor)
            for index, monitor in enumerate(session.monitors[1:], start=1)
        ]


def monitor_for_region(
    region: Region, monitors: list[MonitorGeometry]
) -> MonitorGeometry | None:
    """Return the monitor holding the region, or the most overlapped one."""
    for monitor in monitors:
        if monitor.contains(region):
            return monitor
    overlapping = [monitor for monitor in monitors if monitor.overlaps(region)]
    if not overlapping:
        return None
    return max(overlapping, key=lambda monitor: monitor.overlap_area(region))


def ensure_region_is_on_screen(
    region: Region, monitors: list[MonitorGeometry]
) -> MonitorGeometry:
    """Return the monitor holding the region or refuse to capture blindly."""
    monitor = monitor_for_region(region, monitors)
    if monitor is None:
        layout = "; ".join(item.describe() for item in monitors) or "no monitors detected"
        raise ScreenRegionError(
            f"Capture region ({region.x}, {region.y}) {region.width}x{region.height} "
            f"is outside every monitor: {layout}"
        )
    return monitor


def is_blank_frame(frame: np.ndarray, channel_limit: int = BLANK_CHANNEL_LIMIT) -> bool:
    """Report whether every colour pixel is black, ignoring BGRA alpha."""
    if not isinstance(frame, np.ndarray) or frame.ndim < 2 or frame.size == 0:
        raise ValueError("Frame must be a non-empty image array")
    colour_channels = frame[..., :3] if frame.ndim >= 3 else frame
    return bool(int(colour_channels.max()) <= channel_limit)


def _restrict_to_region(frame: np.ndarray, region: Region) -> np.ndarray:
    """Prevent a capture backend from exposing pixels outside the request."""
    if not isinstance(frame, np.ndarray) or frame.ndim < 2:
        raise ValueError("Capture backend returned an invalid frame")
    if frame.shape[0] < region.height or frame.shape[1] < region.width:
        raise ValueError(
            "Capture backend returned a frame smaller than the requested region"
        )
    return frame[: region.height, : region.width].copy()


def describe_capture_geometry(region: Region) -> str:
    """Describe where the region sits; never raises, for display purposes only."""
    try:
        monitors = list_monitors()
    except Exception as exc:  # pragma: no cover - environment dependent
        return f"Region ({region.x}, {region.y}) {region.width}x{region.height}; monitor layout unavailable: {exc}"
    monitor = monitor_for_region(region, monitors)
    if monitor is None:
        return (
            f"Region ({region.x}, {region.y}) {region.width}x{region.height} "
            f"is not on any monitor: {'; '.join(item.describe() for item in monitors)}"
        )
    note = "" if monitor.contains(region) else ", region extends past that monitor's edge"
    return (
        f"Region ({region.x}, {region.y}) {region.width}x{region.height} "
        f"on {monitor.describe()}{note}"
    )


class ScreenCapturer:
    """Return in-memory BGRA copies using MSS with a DXcam fallback."""

    def __init__(self) -> None:
        self._dxcam_cameras: dict[int, object] = {}

    def _capture_with_dxcam(
        self, region: Region, monitor: MonitorGeometry
    ) -> np.ndarray | None:
        if dxcam is None:
            return None
        camera = self._dxcam_cameras.get(monitor.index)
        if camera is None:
            camera = dxcam.create(output_idx=monitor.index - 1, output_color="BGRA")
            self._dxcam_cameras[monitor.index] = camera
        local_region = (
            region.x - monitor.left,
            region.y - monitor.top,
            region.x - monitor.left + region.width,
            region.y - monitor.top + region.height,
        )
        frame = camera.grab(
            region=local_region,
            new_frame_only=False,
        )
        if frame is None:
            return None
        return _restrict_to_region(np.asarray(frame, dtype=np.uint8), region)

    def capture(self, region: Region) -> np.ndarray:
        rectangle = {
            "left": region.x,
            "top": region.y,
            "width": region.width,
            "height": region.height,
        }
        with mss.MSS() as session:
            monitors = [
                _to_geometry(index, monitor)
                for index, monitor in enumerate(session.monitors[1:], start=1)
            ]
            monitor = ensure_region_is_on_screen(region, monitors)
            mss_frame = _restrict_to_region(
                np.asarray(session.grab(rectangle), dtype=np.uint8), region
            )
        if not is_blank_frame(mss_frame):
            return mss_frame
        try:
            dxcam_frame = self._capture_with_dxcam(region, monitor)
        except Exception:
            # MSS remains a valid fallback when Desktop Duplication is busy,
            # unsupported, or temporarily unavailable.
            dxcam_frame = None
        return mss_frame if dxcam_frame is None else dxcam_frame