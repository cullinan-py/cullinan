# -*- coding: utf-8 -*-
"""Cullinan ParamValidator Tests

Tests parameter validators.

Author: Cullinan
"""

import unittest

from cullinan.web.params import (
    ParamValidator,
    ValidationError,
    Param,
    Query,
)


class TestValidationError(unittest.TestCase):
    """Test ValidationError"""

    def test_basic_error(self):
        """Basic error"""
        err = ValidationError("test error", param_name="age", value=5)
        self.assertEqual(err.message, "test error")
        self.assertEqual(err.param_name, "age")
        self.assertEqual(err.value, 5)

    def test_to_dict(self):
        """Convert to dict"""
        err = ValidationError("test", param_name="x", value=1, constraint="ge:0")
        d = err.to_dict()
        self.assertEqual(d['message'], "test")
        self.assertEqual(d['param'], "x")
        self.assertEqual(d['constraint'], "ge:0")


class TestParamValidatorRequired(unittest.TestCase):
    """Test required validation"""

    def test_required_with_value(self):
        """Required with value"""
        ParamValidator.validate_required("test", True, "name")  # no exception

    def test_required_without_value(self):
        """Required without value"""
        with self.assertRaises(ValidationError) as ctx:
            ParamValidator.validate_required(None, True, "name")
        self.assertIn("required", ctx.exception.message)

    def test_optional_without_value(self):
        """Optional without value"""
        ParamValidator.validate_required(None, False, "name")  # no exception


class TestParamValidatorNumeric(unittest.TestCase):
    """Test numeric validation"""

    def test_ge_pass(self):
        """ge pass"""
        ParamValidator.validate_ge(10, 5, "age")
        ParamValidator.validate_ge(5, 5, "age")

    def test_ge_fail(self):
        """ge fail"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_ge(3, 5, "age")

    def test_ge_none(self):
        """ge None skip"""
        ParamValidator.validate_ge(None, 5, "age")

    def test_le_pass(self):
        """le pass"""
        ParamValidator.validate_le(5, 10, "age")
        ParamValidator.validate_le(10, 10, "age")

    def test_le_fail(self):
        """le fail"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_le(15, 10, "age")

    def test_gt_pass(self):
        """gt pass"""
        ParamValidator.validate_gt(10, 5, "age")

    def test_gt_fail(self):
        """gt fail (equal is also not allowed)"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_gt(5, 5, "age")

    def test_lt_pass(self):
        """lt pass"""
        ParamValidator.validate_lt(5, 10, "age")

    def test_lt_fail(self):
        """lt fail (equal is also not allowed)"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_lt(10, 10, "age")


class TestParamValidatorLength(unittest.TestCase):
    """Test length validation"""

    def test_min_length_pass(self):
        """min_length pass"""
        ParamValidator.validate_min_length("hello", 3, "name")
        ParamValidator.validate_min_length([1, 2, 3], 2, "items")

    def test_min_length_fail(self):
        """min_length fail"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_min_length("hi", 3, "name")

    def test_max_length_pass(self):
        """max_length pass"""
        ParamValidator.validate_max_length("hi", 10, "name")

    def test_max_length_fail(self):
        """max_length fail"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_max_length("hello world", 5, "name")


class TestParamValidatorRegex(unittest.TestCase):
    """Test regex validation"""

    def test_regex_pass(self):
        """regex pass"""
        ParamValidator.validate_regex("test@example.com", r".+@.+\..+", "email")

    def test_regex_fail(self):
        """regex fail"""
        with self.assertRaises(ValidationError):
            ParamValidator.validate_regex("invalid-email", r".+@.+\..+", "email")

    def test_regex_none(self):
        """regex None skip"""
        ParamValidator.validate_regex(None, r".+", "field")


class TestParamValidatorBatch(unittest.TestCase):
    """Test batch validation"""

    def test_validate_multiple(self):
        """Multiple rules"""
        validators = [('ge', 0), ('le', 100)]
        ParamValidator.validate(50, validators, "score")

    def test_validate_fail_first(self):
        """First rule fails"""
        validators = [('ge', 10), ('le', 100)]
        with self.assertRaises(ValidationError):
            ParamValidator.validate(5, validators, "score")

    def test_validate_unknown_rule(self):
        """Unknown rule"""
        with self.assertRaises(ValueError):
            ParamValidator.validate(10, [('unknown', 5)], "x")


class TestParamValidatorWithParam(unittest.TestCase):
    """Test integration with Param class"""

    def test_validate_param_required(self):
        """Validate Param required"""
        param = Query(int, name="age")
        with self.assertRaises(ValidationError):
            ParamValidator.validate_param(param, None)

    def test_validate_param_with_constraints(self):
        """Validate Param constraints"""
        param = Query(int, name="age", ge=0, le=150)
        ParamValidator.validate_param(param, 25)

        with self.assertRaises(ValidationError):
            ParamValidator.validate_param(param, -5)

    def test_validate_param_optional(self):
        """Validate optional Param"""
        param = Query(int, name="page", default=1)
        ParamValidator.validate_param(param, None)  # no exception, because has default = not required

