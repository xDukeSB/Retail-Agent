"""
Heatmap accumulator — builds a spatial density grid from person positions.
Periodically flushed to the backend. No images stored.
"""
import logging
import time
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger("cv-pipeline.heatmap")


class HeatmapAccumulator:
    """
    Accumulates person position density on a NxN grid.
    Normalized coordinates (0-1) are mapped to grid cells.
    """

    def __init__(self, grid_size: int = 100):
        self.grid_size = grid_size
        self._grid = np.zeros((grid_size, grid_size), dtype=np.float32)
        self._visit_counts = np.zeros((grid_size, grid_size), dtype=np.int32)
        self._last_flush = time.time()

    def add_position(self, x: float, y: float):
        """Add a person position to the heatmap. x, y are normalized 0-1."""
        gx = int(np.clip(x * self.grid_size, 0, self.grid_size - 1))
        gy = int(np.clip(y * self.grid_size, 0, self.grid_size - 1))
        self._grid[gy, gx] += 1.0
        self._visit_counts[gy, gx] += 1

    def add_batch(self, positions: List[Tuple[float, float]]):
        """Add multiple positions at once."""
        for x, y in positions:
            self.add_position(x, y)

    def get_cells_for_export(self) -> List[Dict]:
        """Returns only non-zero cells for efficient API push."""
        nonzero = np.argwhere(self._grid > 0)
        cells = []
        for gy, gx in nonzero:
            cells.append({
                "x": int(gx),
                "y": int(gy),
                "density": float(self._grid[gy, gx]),
                "visits": int(self._visit_counts[gy, gx]),
            })
        return cells

    def reset(self):
        """Reset accumulator after flush."""
        self._grid.fill(0)
        self._visit_counts.fill(0)
        self._last_flush = time.time()

    def should_flush(self, interval_seconds: int) -> bool:
        return time.time() - self._last_flush >= interval_seconds

    @property
    def total_density(self) -> float:
        return float(self._grid.sum())
