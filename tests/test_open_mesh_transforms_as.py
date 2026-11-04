"""``stos.open_mesh_transforms_as`` picks the editing type for mesh transforms on load.

A ``.stos`` file stores RBF transforms as an ordinary ``MeshTransform``, so a file
saved in RBF mode reopened as a mesh. The preference converts loaded mesh
transforms to RBF; grid and rigid transforms open unchanged.
"""
from __future__ import annotations

import unittest

import nornir_imageregistration
import numpy as np
from nornir_imageregistration.transforms import TransformType
from pyre.settings.app import AppSettings, StosSettings
from pyre.stos_registration import load_stos_transform


def _mesh_string() -> str:
    fixed = np.array([[i * 100.0, j * 100.0] for i in range(3) for j in range(3)])
    points = np.hstack([fixed, fixed + np.array([5.0, -3.0])])
    return nornir_imageregistration.transforms.MeshWithRBFFallback(points).ToITKString()


class TestOpenMeshTransformsAs(unittest.TestCase):

    def test_default_is_mesh(self) -> None:
        self.assertEqual("mesh", AppSettings().stos.open_mesh_transforms_as)

    def test_mesh_opens_as_mesh_by_default(self) -> None:
        transform = load_stos_transform(_mesh_string())
        self.assertEqual(TransformType.MESH, transform.type)

    def test_mesh_opens_as_rbf_when_preferred(self) -> None:
        transform = load_stos_transform(_mesh_string(), open_mesh_as="rbf")
        self.assertEqual(TransformType.RBF, transform.type)
        self.assertIsInstance(transform, nornir_imageregistration.transforms.IControlPointAddRemove)
        self.assertEqual(9, transform.NumControlPoints)

    def test_rigid_ignores_the_preference(self) -> None:
        rigid = nornir_imageregistration.transforms.Rigid((3.0, 4.0), (0.0, 0.0), angle=0.0)
        transform = load_stos_transform(rigid.ToITKString(), open_mesh_as="rbf")
        self.assertEqual(TransformType.RIGID, transform.type)

    def test_unknown_value_opens_as_mesh(self) -> None:
        transform = load_stos_transform(_mesh_string(), open_mesh_as="no-such-type")
        self.assertEqual(TransformType.MESH, transform.type)

    def test_setting_round_trips(self) -> None:
        settings = AppSettings(stos=StosSettings(open_mesh_transforms_as="rbf"))
        restored = AppSettings.model_validate_json(settings.model_dump_json())
        self.assertEqual("rbf", restored.stos.open_mesh_transforms_as)


if __name__ == '__main__':
    unittest.main()
