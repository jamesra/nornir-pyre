# Adding a Pyre transform display strategy

Pyre STOS rendering uses **`TransformDisplayStrategy`** implementations registered by
transform type. Views call `TransformController.resolve_draw_state()`; they do not
branch on transform type directly.

## Registry

| `TransformType` | Strategy class |
|-----------------|----------------|
| RIGID | `RigidDisplayStrategy` |
| MESH | `MeshLikeDisplayStrategy` |
| GRID | `MeshLikeDisplayStrategy` |
| RBF | `MeshLikeDisplayStrategy` |

Factory: `display_strategy_for_model(model)` in
[`pyre/controllers/transform_display.py`](../pyre/controllers/transform_display.py).

## Implementing a new type

1. **Subclass `TransformDisplayStrategy`** (or `MeshLikeDisplayStrategy` / `RigidDisplayStrategy` if behavior matches).
2. **Register** the class in `TransformDisplayStrategyRegistry.for_model`.
3. **Add DI maps** (existing pattern):
   - `stos_container.transform_action_map[TransformType.T]`
   - `container_overrides.action_command_map[TransformType.T]`
4. **Add policy rows** in [`pyre/transform_edit_policy.py`](../pyre/transform_edit_policy.py)
   (`wheel_rotate_locked`, `layer_translate_locked`, etc.).
5. **Wire commands** to call `begin_interactive_edit` / `end_interactive_edit` (which delegate to `begin_gesture` / `end_gesture`).
6. **Tests** in `tests/test_transform_display.py`:
   - registry returns your strategy
   - `resolve_draw_state` for a known model
   - `on_model_changed` / `on_point_moved` refresh hints

No changes are required to `ImageTransformView.draw()` if `resolve_draw_state` returns
correct `TransformDrawState` fields.

## Refresh hints

| Hint | Meaning |
|------|---------|
| `NONE` | Repaint only (rigid during drag) |
| `INCREMENTAL` | Patch Delaunay tiles for moved control points |
| `FULL` | Clear tile mesh cache and rebuild |

## Related files

- [`transformcontroller.py`](../pyre/controllers/transformcontroller.py) — model + strategy host
- [`imagetransformview.py`](../pyre/views/imagetransformview.py) — draw loop
- [`gltiles.py`](../pyre/views/gltiles.py) — tile mesh CPU build (quad vs Delaunay)

See also `.cursor/skills/pyre-stos-rigid-transform-ui/SKILL.md` for rigid STOS invariants.
