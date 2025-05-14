from __future__ import annotations
import abc
import os
import sys
import pydantic
from typing import Generator

from dependency_injector import containers, providers
from dependency_injector.providers import AbstractFactory, Factory, Dict, AbstractSingleton

import nornir_imageregistration
from pyre.interfaces.managers import (ICommandHistory, IControlPointActionMap, IGLContextManager, IImageLoader,
                                      IImageManager,
                                      IMousePositionHistoryManager,
                                      IRegionMap, ITransformControllerGLBufferManager, IImageViewModelManager,
                                      IWindowManager, IControlPointMapManager, ControlPointManagerKey, IActionMap)
from pyre.interfaces.viewtype import ViewType
from pyre.interfaces.action import ControlPointAction
from pyre.command_interfaces import ICommand, IInstantCommand
from pyre.interfaces.readonlycamera import IReadOnlyCamera
from pyre.settings import AppSettings
from pyre.space import Space
from nornir_imageregistration.transforms.transform_type import TransformType

ControlPointActionCommandMapType = Dict[ControlPointAction, AbstractFactory[ICommand]]


def find_file_in_syspath(filename) -> Generator[str, None, None]:
    for directory in sys.path:
        potential_path = os.path.join(directory, filename)
        if os.path.isfile(potential_path):
            yield potential_path
    return None


def load_yaml_settings() -> object:
    try:
        current_directory = os.path.dirname(__file__)
        cwd_config = os.path.join(current_directory, 'config.yaml')
        with open(cwd_config, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader)
    except:
        print("Failed to load configuration file: " + cwd_config)

    for configuration in find_file_in_syspath('config.yaml'):
        try:
            with open(configuration, 'r') as file:
                return yaml.load(file, Loader=yaml.FullLoader)
        except:
            print("Failed to load configuration file: " + configuration)

    raise ValueError(f"Failed to find config.yaml configuration file in {sys.path}")


def load_json_settings() -> AppSettings:
    try:
        current_directory = os.path.dirname(__file__)
        cwd_config = os.path.join(current_directory, 'settings.json')
        return AppSettings.parse_file(cwd_config)

    except Exception as e:
        print(f"Failed to load configuration file: {cwd_config}\n{e}")

    for configuration in find_file_in_syspath('settings.json'):
        try:
            return AppSettings.parse_file(cwd_config)
        except:
            print("Failed to load configuration file: " + configuration)

    raise ValueError(f"Failed to find config.yaml configuration file in {sys.path}")


class IContainer(containers.DeclarativeContainer):
    """Interface to the dependency injection container for the application components."""
    config: providers.Configuration = providers.Configuration()
    logger: providers.Resource = None

    history_manager: providers.AbstractSingleton[ICommandHistory] = providers.AbstractSingleton(ICommandHistory)
    region_map: providers.Factory[IRegionMap] = providers.AbstractFactory(IRegionMap)
    mouse_position_history: providers.AbstractSingleton[IMousePositionHistoryManager] = providers.AbstractSingleton(
        IMousePositionHistoryManager)
    command_history: providers.AbstractSingleton[ICommandHistory] = providers.AbstractSingleton(ICommandHistory)
    image_manager: providers.AbstractSingleton[IImageManager] = providers.AbstractSingleton(IImageManager)
    transform_glbuffermanager: providers.AbstractSingleton[
        ITransformControllerGLBufferManager] = providers.AbstractSingleton(ITransformControllerGLBufferManager)
    imageviewmodel_manager: providers.AbstractSingleton[IImageViewModelManager] = providers.AbstractSingleton(
        IImageViewModelManager)
    glcontext_manager: providers.AbstractSingleton[IGLContextManager] = providers.AbstractSingleton(IGLContextManager)
    window_manager: providers.AbstractSingleton[IWindowManager] = providers.AbstractSingleton(IWindowManager)

    image_loader: providers.AbstractFactory[IImageLoader] = providers.AbstractFactory()
    transform_controller: providers.AbstractSingleton = providers.AbstractSingleton()

    control_point_manager_key = providers.AbstractFactory(
        ControlPointManagerKey)  # Returns the key for the configured transform controller and space
    controlpointmap_manager: providers.AbstractSingleton[IControlPointMapManager] = providers.AbstractSingleton()

    transform_control_point_action_maps: providers.Dict[
        TransformType, providers.AbstractFactory[IControlPointActionMap]] = providers.Dict()

    action_command_map: providers.Dict[TransformType, providers.Dict[ControlPointAction, AbstractFactory[ICommand]]] = \
        providers.Dict({t: \
                            {action: providers.AbstractFactory(ICommand) for action in iter(ControlPointAction)} \
                        for t in iter(TransformType)}
                       )

    # We want a different set of transform commands for each type of transform
    # action_command_map: providers.Dict[TransformType, ControlPointActionCommandMapType] = providers.Dict({})

    transform_action_map: providers.Dict[TransformType, IControlPointActionMap] = \
        providers.Dict({
            TransformType.GRID: providers.AbstractFactory(IControlPointActionMap),
            TransformType.MESH: providers.AbstractFactory(IControlPointActionMap),
            TransformType.RIGID: providers.AbstractFactory(IActionMap),
            TransformType.RBF: providers.AbstractFactory(IControlPointActionMap)
        })

    settings = providers.Resource(load_json_settings)
