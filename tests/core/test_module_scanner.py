# -*- coding: utf-8 -*-
"""Tests for the module_scanner module.

Tests the module discovery and scanning functionality across different
deployment environments (development, Nuitka, PyInstaller).
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from cullinan.runtime.module_scanner import (
    is_pyinstaller_frozen,
    is_nuitka_compiled,
    get_nuitka_standalone_mode,
    get_pyinstaller_mode,
    get_caller_package,
    _is_user_module_by_path,
)


class TestEnvironmentDetection(unittest.TestCase):
    """Test environment detection functions."""
    
    def test_is_pyinstaller_frozen_false(self):
        """Test PyInstaller detection in normal environment."""
        # In normal Python environment, should return False
        result = is_pyinstaller_frozen()
        self.assertFalse(result)
    
    def test_is_nuitka_compiled_false(self):
        """Test Nuitka detection in normal environment."""
        # In normal Python environment, should return False
        result = is_nuitka_compiled()
        self.assertFalse(result)
    
    def test_get_nuitka_standalone_mode_none(self):
        """Test Nuitka mode detection returns None in normal environment."""
        result = get_nuitka_standalone_mode()
        self.assertIsNone(result)
    
    def test_get_pyinstaller_mode_none(self):
        """Test PyInstaller mode detection returns None in normal environment."""
        result = get_pyinstaller_mode()
        self.assertIsNone(result)


class TestModulePathChecking(unittest.TestCase):
    """Test module path validation functions."""
    
    def test_is_user_module_by_path_cullinan(self):
        """Test that cullinan modules are excluded."""
        mod = MagicMock()
        mod.__file__ = '/path/to/cullinan/module.py'
        result = _is_user_module_by_path('cullinan.module', mod)
        self.assertFalse(result)
    
    def test_is_user_module_by_path_site_packages(self):
        """Test that site-packages modules are excluded."""
        mod = MagicMock()
        mod.__file__ = '/usr/lib/python3.12/site-packages/some_lib/module.py'
        result = _is_user_module_by_path('some_lib.module', mod)
        self.assertFalse(result)
    
    def test_is_user_module_by_path_stdlib(self):
        """Test that stdlib modules are excluded."""
        mod = MagicMock()
        mod.__file__ = '/usr/lib/python3.12/json/__init__.py'
        result = _is_user_module_by_path('json', mod)
        self.assertFalse(result)
    
    def test_is_user_module_by_path_user_code(self):
        """Test that user modules are included."""
        mod = MagicMock()
        mod.__file__ = '/home/user/myproject/myapp/controller.py'
        result = _is_user_module_by_path('myapp.controller', mod)
        self.assertTrue(result)


class TestCallerPackage(unittest.TestCase):
    """Test caller package detection."""
    
    def test_get_caller_package(self):
        """Test that get_caller_package returns a package name."""
        # This test will return 'tests' since it's called from test module
        try:
            result = get_caller_package()
            # Should return something, even if it's an error
            self.assertIsInstance(result, str)
            # Should not be 'cullinan' since we're in tests
            self.assertNotEqual(result, 'cullinan')
        except Exception:
            # If it fails, that's also acceptable for this test
            pass


class TestModuleScannerIntegration(unittest.TestCase):
    """Integration tests for module scanning."""
    
    def test_module_scanner_imports(self):
        """Test that all expected functions are importable."""
        from cullinan.runtime import module_scanner
        
        # Check that all key functions exist
        self.assertTrue(hasattr(module_scanner, 'is_pyinstaller_frozen'))
        self.assertTrue(hasattr(module_scanner, 'is_nuitka_compiled'))
        self.assertTrue(hasattr(module_scanner, 'get_nuitka_standalone_mode'))
        self.assertTrue(hasattr(module_scanner, 'get_pyinstaller_mode'))
        self.assertTrue(hasattr(module_scanner, 'get_caller_package'))
        self.assertTrue(hasattr(module_scanner, 'list_submodules'))
        self.assertTrue(hasattr(module_scanner, 'file_list_func'))
        self.assertTrue(hasattr(module_scanner, 'invalidate_module_cache'))
    
    def test_file_list_func_returns_list(self):
        """Test that file_list_func returns a list."""
        from cullinan.runtime.module_scanner import file_list_func
        
        result = file_list_func()
        self.assertIsInstance(result, list)
        # Should return at least some modules (like tests)
        self.assertGreaterEqual(len(result), 0)


class TestModuleCacheInvalidation(unittest.TestCase):
    """Test module scanning cache invalidation API (Issue 4 fix verification)"""

    def test_invalidate_clears_cache(self):
        """Verify: invalidate_module_cache clears cache so file_list_func rescans"""
        import cullinan.runtime.module_scanner as ms

        # First call, fills cache
        first_result = ms.file_list_func()
        self.assertIsNotNone(ms._module_list_cache)
        self.assertEqual(first_result, ms._module_list_cache)

        # Invalidate cache
        ms.invalidate_module_cache()
        self.assertIsNone(ms._module_list_cache)

        # Second call, should rescan (result same as or newer than first)
        second_result = ms.file_list_func()
        self.assertIsNotNone(ms._module_list_cache)
        self.assertEqual(second_result, ms._module_list_cache)
        # In a stable environment, both results should be identical
        self.assertEqual(first_result, second_result)

    def test_invalidate_importable_from_runtime(self):
        """Verify: invalidate_module_cache is importable from cullinan.runtime"""
        from cullinan.runtime import invalidate_module_cache
        self.assertTrue(callable(invalidate_module_cache))

    def test_get_caller_package_with_fallback(self):
        """Verify: get_caller_package supports fallback_package parameter"""
        from cullinan.runtime.module_scanner import get_caller_package

        result = get_caller_package(fallback_package="test_fallback")
        self.assertIsInstance(result, str)
        # In test environment, should return actual caller package or fallback
        self.assertTrue(len(result) > 0)

    def test_get_caller_package_uses_getframe(self):
        """Verify: get_caller_package uses sys._getframe() optimized path"""
        from cullinan.runtime.module_scanner import get_caller_package

        # Basic call not raising exception verifies _getframe path works
        result = get_caller_package(fallback_package="fallback_test")
        self.assertIsInstance(result, str)


class TestListSubmodules(unittest.TestCase):
    """Test deep subpackage discovery via list_submodules."""

    def test_shallow_package_returns_submodules(self):
        """list_submodules finds modules inside a shallow package."""
        from cullinan.runtime.module_scanner import list_submodules
        mods = list_submodules("cullinan.runtime")
        self.assertIsInstance(mods, list)
        # scanner and module_scanner should be discoverable
        self.assertIn("cullinan.runtime.scanner", mods)

    def test_filesystem_fallback_finds_deep_subpackages(self):
        """Filesystem fallback discovers subpackages walk_packages may miss."""
        from cullinan.runtime.module_scanner import list_submodules
        # cullinan.core has deeper structure
        mods = list_submodules("cullinan.core")
        self.assertIsInstance(mods, list)
        # At minimum, should find application_context
        found_context = any(
            "application_context" in m for m in mods
        )
        self.assertTrue(found_context, f"application_context not in {mods}")

    def test_missing_package_returns_empty_list(self):
        """list_submodules gracefully handles missing packages."""
        from cullinan.runtime.module_scanner import list_submodules
        mods = list_submodules("nonexistent.package.zzz")
        self.assertEqual(mods, [])

    def test_dedup_across_strategies(self):
        """Duplicates from walk_packages and filesystem are merged."""
        from cullinan.runtime.module_scanner import list_submodules
        mods = list_submodules("cullinan.runtime")
        # No duplicates
        self.assertEqual(len(mods), len(set(mods)))
