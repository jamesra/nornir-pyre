"""GRID Shift+Space uses one-pass RefineTransform; MESH/RBF stay per-point."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from typing import Any

from nornir_imageregistration.transforms.transform_type import TransformType

from pyre.commands.container_overrides import action_command_dp_map
from pyre.commands.stos.gridregisterallcommand import GridRegisterAllCommand
from pyre.commands.stos.registercontrolpointcommand import RegisterControlPointCommand
from pyre.interfaces.action import ControlPointAction
from pyre.settings import AngleSearchRange
from pyre.settings.app import AppSettings, ImageAndMaskPath
from pyre.ui.windows.refine_grid_settings_dialog import (
    GridSettingsDialogResult,
    RefineGridSettingsDialog,
)


def _provides_class(provider: object) -> type:
    """Unwrap a dependency-injector Factory/.provider to the constructed class."""
    current: object = provider
    for _ in range(8):
        provides = getattr(current, "provides", None)
        if isinstance(provides, type):
            return provides
        if provides is None or provides is current:
            break
        current = provides
    raise AssertionError(f"Could not resolve class from {provider!r}")


def _action_map_for(transform_type: TransformType) -> dict[Any, Any]:
    """Return the inner action-to-provider map for *transform_type*."""
    kwargs = getattr(action_command_dp_map, "kwargs", None)
    if callable(kwargs):
        kwargs = kwargs()
    if not kwargs:
        kwargs = getattr(action_command_dp_map, "_kwargs", {})
    if not isinstance(kwargs, dict):
        raise AssertionError(f"Expected dict of transform types, got {type(kwargs)!r}")
    type_provider = kwargs[transform_type]
    inner = getattr(type_provider, "kwargs", None)
    if callable(inner):
        inner = inner()
    if not inner:
        inner = getattr(type_provider, "_kwargs", {})
    if not isinstance(inner, dict):
        raise AssertionError(f"Expected dict action map, got {type(inner)!r}")
    return inner


class TestGridRegisterAllWiring(unittest.TestCase):
    """REGISTER_ALL command class by transform type."""

    def test_grid_register_all_is_one_pass_refine_command(self) -> None:
        grid = _action_map_for(TransformType.GRID)
        self.assertIs(
            _provides_class(grid[ControlPointAction.REGISTER_ALL]),
            GridRegisterAllCommand,
        )
        self.assertIs(
            _provides_class(grid[ControlPointAction.REGISTER]),
            RegisterControlPointCommand,
        )

    def test_mesh_and_rbf_register_all_stay_per_point(self) -> None:
        for transform_type in (TransformType.MESH, TransformType.RBF):
            action_map = _action_map_for(transform_type)
            self.assertIs(
                _provides_class(action_map[ControlPointAction.REGISTER_ALL]),
                RegisterControlPointCommand,
                msg=f"{transform_type} REGISTER_ALL",
            )


class TestGridRegisterAllCommand(unittest.TestCase):
    """Shift+Space on GRID prompts then submits the shared refine job."""

    def test_execute_starts_one_pass_job_and_does_not_enqueue_points(self) -> None:
        transform_controller = MagicMock()
        image_manager = MagicMock()
        window_manager = MagicMock()
        stos_window = MagicMock()
        parent = MagicMock()
        settings = AppSettings()
        settings.stos.source_image = ImageAndMaskPath(
            image_fullpath="source.png", mask_fullpath=None)
        settings.stos.target_image = ImageAndMaskPath(
            image_fullpath="target.png", mask_fullpath=None)
        result = GridSettingsDialogResult(
            num_iterations=1,
            cell_size=256,
            grid_spacing=192,
            angle_range=AngleSearchRange(max_angle=5.0, angle_step_size=3.0),
        )

        with patch.object(
                RefineGridSettingsDialog, "GetGridRefineSettings", return_value=result) as mock_dialog, \
                patch(
                    "pyre.commands.stos.gridregisterallcommand._stos_window_from_manager",
                    return_value=stos_window):
            command = GridRegisterAllCommand(
                parent=parent,
                transform_controller=transform_controller,
                image_manager=image_manager,
                window_manager=window_manager,
                settings=settings,
            )
            command.activate()

        mock_dialog.assert_called_once()
        self.assertEqual(mock_dialog.call_args.kwargs["fixed_num_iterations"], 1)
        stos_window.start_grid_refine_job.assert_called_once_with(
            result,
            title="Grid refine (one pass)",
            save_plots=False,
        )
        transform_controller.enqueue_point_registrations.assert_not_called()

    def test_cancelled_dialog_does_not_start_job(self) -> None:
        transform_controller = MagicMock()
        stos_window = MagicMock()
        settings = AppSettings()
        settings.stos.source_image = ImageAndMaskPath(
            image_fullpath="source.png", mask_fullpath=None)
        settings.stos.target_image = ImageAndMaskPath(
            image_fullpath="target.png", mask_fullpath=None)

        with patch.object(
                RefineGridSettingsDialog, "GetGridRefineSettings", return_value=None), \
                patch(
                    "pyre.commands.stos.gridregisterallcommand._stos_window_from_manager",
                    return_value=stos_window):
            command = GridRegisterAllCommand(
                transform_controller=transform_controller,
                image_manager=MagicMock(),
                window_manager=MagicMock(),
                settings=settings,
            )
            command.activate()

        stos_window.start_grid_refine_job.assert_not_called()
        transform_controller.enqueue_point_registrations.assert_not_called()


class TestMultiPassRefineStaysOneJob(unittest.TestCase):
    """Menu Refine w/ Grid must preview passes inside one RefineTransform job."""

    def test_start_grid_refine_job_wires_on_preview_and_passes_num_iterations(self) -> None:
        import inspect

        from pyre.ui.windows.stoswindow import StosWindow

        source = inspect.getsource(StosWindow.start_grid_refine_job)
        self.assertIn("num_iterations=user_iterations", source)
        self.assertIn("on_preview=_on_preview", source)
        self.assertIn("kind=\"pass preview\"", source)
        self.assertNotIn("for _ in range(user_iterations)", source)
        self.assertNotIn("GridRegisterAllCommand", source)

    def test_on_refine_grid_does_not_loop_one_pass_jobs(self) -> None:
        import inspect

        from pyre.ui.windows.stoswindow import StosWindow

        source = inspect.getsource(StosWindow.onRefineGrid)
        self.assertIn("start_grid_refine_job", source)
        self.assertNotIn("fixed_num_iterations", source)
        self.assertIn("title=\"Refine w/ Grid\"", source)
