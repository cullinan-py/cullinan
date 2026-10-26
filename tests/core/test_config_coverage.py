# -*- coding: utf-8 -*-
"""
Tests for configuration management.
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

from cullinan.support.config import (
    CullinanConfig,
    get_class_config,
    get_config,
    configure,
)
from cullinan import application


class TestCullinanConfig(unittest.TestCase):
    """Test CullinanConfig class."""
    
    def setUp(self):
        """Create a fresh config instance for each test."""
        self.config = CullinanConfig()
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CullinanConfig()
        
        self.assertEqual(config.user_packages, [])
        self.assertIsNone(config.project_root)
        self.assertIsNone(config.root_module)
        self.assertFalse(config.verbose)
        self.assertTrue(config.auto_scan)
        self.assertIn('test', config.exclude_packages)
        self.assertEqual(config.server_engine, 'auto')
        self.assertEqual(config.server_host, '0.0.0.0')
        self.assertEqual(config.server_port, 4080)
    
    def test_add_user_package(self):
        """Test adding user packages."""
        self.config.add_user_package('myapp')
        self.assertIn('myapp', self.config.user_packages)
        
        # Adding same package twice should not duplicate
        self.config.add_user_package('myapp')
        self.assertEqual(self.config.user_packages.count('myapp'), 1)
    
    def test_set_project_root(self):
        """Test setting project root."""
        self.config.set_project_root('/path/to/project')
        self.assertTrue(self.config.project_root.endswith('project'))
    
    def test_set_verbose(self):
        """Test setting verbose flag."""
        self.config.set_verbose(True)
        self.assertTrue(self.config.verbose)
        
        self.config.set_verbose(False)
        self.assertFalse(self.config.verbose)
    
    def test_from_dict(self):
        """Test loading configuration from dictionary."""
        config_dict = {
            'user_packages': ['app1', 'app2'],
            'project_root': '/test/root',
            'root_module': 'RootModule',
            'verbose': True,
            'auto_scan': False,
            'exclude_packages': ['test', 'build'],
            'server_engine': 'asgi',
            'server_host': '127.0.0.1',
            'server_port': 9000,
        }
        
        self.config.from_dict(config_dict)
        
        self.assertEqual(self.config.user_packages, ['app1', 'app2'])
        self.assertEqual(self.config.project_root, '/test/root')
        self.assertEqual(self.config.root_module, 'RootModule')
        self.assertTrue(self.config.verbose)
        self.assertFalse(self.config.auto_scan)
        self.assertEqual(self.config.exclude_packages, ['test', 'build'])
        self.assertEqual(self.config.server_engine, 'asgi')
        self.assertEqual(self.config.server_host, '127.0.0.1')
        self.assertEqual(self.config.server_port, 9000)
    
    def test_to_dict(self):
        """Test exporting configuration to dictionary."""
        self.config.user_packages = ['myapp']
        self.config.project_root = '/test'
        self.config.root_module = 'RootModule'
        self.config.verbose = True
        self.config.server_engine = 'asgi'
        self.config.server_host = '127.0.0.1'
        self.config.server_port = 9000
        
        config_dict = self.config.to_dict()
        
        self.assertEqual(config_dict['user_packages'], ['myapp'])
        self.assertEqual(config_dict['project_root'], '/test')
        self.assertEqual(config_dict['root_module'], 'RootModule')
        self.assertTrue(config_dict['verbose'])
        self.assertEqual(config_dict['server_engine'], 'asgi')
        self.assertEqual(config_dict['server_host'], '127.0.0.1')
        self.assertEqual(config_dict['server_port'], 9000)


class TestConfigureFunction(unittest.TestCase):
    """Test the configure function."""

    def setUp(self):
        self._original_config = get_config().to_dict()

    def tearDown(self):
        get_config().from_dict(self._original_config)
    
    def test_configure_with_user_packages(self):
        """Test configure with user packages."""
        result = configure(user_packages=['test_app'], verbose=False)
        
        self.assertIsInstance(result, CullinanConfig)
        self.assertIn('test_app', result.user_packages)
    
    def test_configure_verbose(self):
        """Test configure with verbose flag."""
        result = configure(verbose=True)
        self.assertTrue(result.verbose)
    
    def test_configure_auto_scan(self):
        """Test configure with auto_scan flag."""
        result = configure(auto_scan=False)
        self.assertFalse(result.auto_scan)
    
    def test_configure_exclude_packages(self):
        """Test configure with custom exclude packages."""
        result = configure(exclude_packages=['custom_exclude'])
        self.assertEqual(result.exclude_packages, ['custom_exclude'])

    def test_configure_recommended_public_entrypoint_fields(self):
        """Test configure with top-level public run() settings."""
        result = configure(
            server_engine='asgi',
            asgi_server='hypercorn',
            server_host='127.0.0.1',
            server_port=9000,
        )

        self.assertEqual(result.server_engine, 'asgi')
        self.assertEqual(result.asgi_server, 'hypercorn')
        self.assertEqual(result.server_host, '127.0.0.1')
        self.assertEqual(result.server_port, 9000)

    def test_configure_rejects_legacy_root_module_entry(self):
        """Test configure(root_module=...) now raises a migration error."""

        class RootModule:
            pass

        with self.assertRaises(ValueError) as cm:
            configure(root_module=RootModule)

        self.assertIn('configure(root_module=...)', str(cm.exception))
        self.assertIn('@application', str(cm.exception))

    def test_configure_can_decorate_application_class(self):
        """Test configure(...) as an entry-method decorator."""

        @configure(user_packages=['decorator_app'], server_engine='asgi')
        @application
        def main(): ...

        class_config = get_class_config(main)
        assert class_config is not None
        self.assertEqual(class_config['user_packages'], ['decorator_app'])
        self.assertEqual(class_config['server_engine'], 'asgi')
        self.assertEqual(main.entry_kind, 'method')

    def test_application_and_configure_are_order_independent(self):
        """Test @application and @configure in either order."""

        @application
        @configure(user_packages=['ordered_app'], server_host='127.0.0.1')
        def ordered_main(): ...

        @configure(user_packages=['reordered_app'], server_host='127.0.0.2')
        @application
        def reordered_main(): ...

        ordered_config = get_class_config(ordered_main)
        reordered_config = get_class_config(reordered_main)

        assert ordered_config is not None
        assert reordered_config is not None
        self.assertEqual(ordered_config['user_packages'], ['ordered_app'])
        self.assertEqual(ordered_config['server_host'], '127.0.0.1')
        self.assertEqual(reordered_config['user_packages'], ['reordered_app'])
        self.assertEqual(reordered_config['server_host'], '127.0.0.2')
    
    def test_get_config_returns_same_instance(self):
        """Test that get_config returns the global config instance."""
        config1 = get_config()
        config2 = get_config()
        
        # Should be the same object
        self.assertIs(config1, config2)


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation and edge cases."""
    
    def test_empty_user_packages(self):
        """Test with empty user packages."""
        config = CullinanConfig()
        config.from_dict({'user_packages': []})
        self.assertEqual(config.user_packages, [])
    
    def test_none_project_root(self):
        """Test with None project root."""
        config = CullinanConfig()
        config.from_dict({'project_root': None})
        self.assertIsNone(config.project_root)
    
    def test_partial_config_dict(self):
        """Test from_dict with partial configuration."""
        config = CullinanConfig()
        config.from_dict({'verbose': True})
        
        # Should update only specified fields
        self.assertTrue(config.verbose)
        # Other fields should remain default
        self.assertEqual(config.user_packages, [])


class TestExcludePackages(unittest.TestCase):
    """Test exclude packages functionality."""
    
    def test_default_exclude_packages(self):
        """Test default exclude packages list."""
        config = CullinanConfig()
        
        # Should have common directories to exclude
        self.assertIn('test', config.exclude_packages)
        self.assertIn('tests', config.exclude_packages)
        self.assertIn('__pycache__', config.exclude_packages)
        self.assertIn('.git', config.exclude_packages)
    
    def test_custom_exclude_packages(self):
        """Test setting custom exclude packages."""
        config = CullinanConfig()
        config.exclude_packages = ['custom1', 'custom2']
        
        self.assertEqual(config.exclude_packages, ['custom1', 'custom2'])


class TestProjectRootDetection(unittest.TestCase):
    """Test project root detection."""
    
    def test_project_root_absolute_path(self):
        """Test that project root is converted to absolute path."""
        config = CullinanConfig()
        config.set_project_root('.')
        
        # Should be converted to absolute path
        self.assertTrue(os.path.isabs(config.project_root))
    
    def test_project_root_with_relative_path(self):
        """Test project root with relative path."""
        config = CullinanConfig()
        
        # Use current directory
        cwd = os.getcwd()
        config.set_project_root(cwd)
        
        self.assertEqual(config.project_root, cwd)


def test_verbose_can_be_turned_off_again():
    """A switch that only works in one direction is a switch nobody trusts twice.

    ``configure(verbose=True)`` lowers the framework logger to DEBUG. Without a
    way back, every later configuration in the same process inherits the noise,
    which is how a test suite starts printing logs nobody asked for.
    """
    import logging

    from cullinan import configure

    logger = logging.getLogger("cullinan")
    original = logger.level
    try:
        configure(verbose=True)
        assert logger.level == logging.DEBUG
        configure(verbose=False)
        assert logger.level == original, "verbose=False did not restore the previous level"
    finally:
        logger.setLevel(original)
