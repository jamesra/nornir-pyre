"""CPU-side tile mesh cache shared across image transform views."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
from numpy.typing import NDArray

from pyre.space import Space


@dataclasses.dataclass
class TileMeshCpuEntry:
  """Vertex/index data for one tile before GL upload."""

  vertices: NDArray[np.floating]
  indices: NDArray[np.integer]
  simplices: NDArray[np.integer] | None = None
  point_count: int = 0
  is_rigid_quad: bool = False


class TileMeshCpuCache:
  """Caches computed tile meshes keyed by view model, display space, and tile coordinate."""

  def __init__(self) -> None:
    self._entries: dict[tuple[int, int, tuple[int, int]], TileMeshCpuEntry] = {}
    self.generation = 0

  def clear(self) -> None:
    self._entries.clear()
    self.generation += 1

  def invalidate_tiles(self, tile_coords: set[tuple[int, int]]) -> None:
    if not tile_coords:
      return
  # Keys are (vm_id, space_int, (ix, iy))
    remove = [k for k in self._entries if k[2] in tile_coords]
    for key in remove:
      del self._entries[key]
    if remove:
      self.generation += 1

  def get(self, vm_id: int, space: Space, tile_coord: tuple[int, int]) -> TileMeshCpuEntry | None:
    return self._entries.get((vm_id, int(space), tile_coord))

  def put(self, vm_id: int, space: Space, tile_coord: tuple[int, int], entry: TileMeshCpuEntry) -> None:
    self._entries[(vm_id, int(space), tile_coord)] = entry
