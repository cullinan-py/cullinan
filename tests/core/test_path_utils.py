# -*- coding: utf-8 -*-
"""Test path_utils and controller exports."""


def test_path_utils():
    """Test the path_utils module."""
    from cullinan import Inject, controller, get_api, post_api
    from cullinan.core import Registry, injectable
    from cullinan.support import (
        get_base_path,
        get_cullinan_package_path,
        get_executable_dir,
        get_module_file_path,
        get_packaging_mode,
        get_path_info,
        get_resource_path,
        get_user_data_dir,
        is_frozen,
        is_nuitka_compiled,
        is_pyinstaller_frozen,
    )
    from cullinan.web.controller import get_controller_registry

    assert isinstance(is_frozen(), bool)
    assert isinstance(is_nuitka_compiled(), bool)
    assert isinstance(is_pyinstaller_frozen(), bool)
    assert isinstance(get_packaging_mode(), str)
    assert get_base_path() is not None
    assert get_cullinan_package_path().exists()
    assert get_executable_dir() is not None
    assert get_user_data_dir() is not None
    assert isinstance(get_path_info(), dict)

    controller_path = (
        get_module_file_path('web/controller/__init__.py', relative_to_cullinan=True)
        or get_module_file_path('web/controller.py', relative_to_cullinan=True)
    )
    assert controller_path is not None
    assert controller_path.exists()

    config_path = get_resource_path('config.yaml')
    assert config_path.name == 'config.yaml'

    assert callable(controller)
    assert callable(get_api)
    assert callable(post_api)
    assert callable(get_controller_registry)
    assert isinstance(Registry, type)
    assert callable(Inject)
    assert callable(injectable)


def test_controller_loading():
    """Test importing main APIs from controller package."""
    from cullinan.web.controller import Handler, controller, get_api, post_api, response
    from cullinan.web.handler.base import BaseHandler

    assert callable(controller)
    assert callable(get_api)
    assert callable(post_api)
    assert callable(response)
    assert isinstance(Handler, type)
    assert issubclass(Handler, BaseHandler)
