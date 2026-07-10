# -*- coding: utf-8 -*-
"""Cullinan Codec Module Tests

Tests the encoding/decoding functionality of the Codec module.

Author: Cullinan
"""

import unittest
import json

from cullinan.codec import (
    BodyCodec,
    ResponseCodec,
    JsonBodyCodec,
    JsonResponseCodec,
    FormBodyCodec,
    DecodeError,
    EncodeError,
    CodecRegistry,
    get_codec_registry,
    reset_codec_registry,
)


class TestJsonBodyCodec(unittest.TestCase):
    """Test JSON request body decoding"""

    def setUp(self):
        self.codec = JsonBodyCodec()

    def test_decode_empty_body(self):
        """Empty body should return empty dict"""
        result = self.codec.decode(b'')
        self.assertEqual(result, {})

    def test_decode_valid_json(self):
        """Normal JSON decoding"""
        body = b'{"name": "test", "age": 18}'
        result = self.codec.decode(body)
        self.assertEqual(result, {"name": "test", "age": 18})

    def test_decode_json_array(self):
        """JSON array should be wrapped"""
        body = b'[1, 2, 3]'
        result = self.codec.decode(body)
        self.assertEqual(result, {"_value": [1, 2, 3]})

    def test_decode_invalid_json(self):
        """Invalid JSON should raise DecodeError"""
        body = b'invalid json'
        with self.assertRaises(DecodeError):
            self.codec.decode(body)

    def test_decode_with_charset(self):
        """Decoding with charset"""
        body = '{"name": "中文"}'.encode('utf-8')
        result = self.codec.decode(body, charset='utf-8')
        self.assertEqual(result, {"name": "中文"})

    def test_supports_content_type(self):
        """Content-Type support detection"""
        self.assertTrue(JsonBodyCodec.supports('application/json'))
        self.assertTrue(JsonBodyCodec.supports('application/json; charset=utf-8'))
        self.assertTrue(JsonBodyCodec.supports('text/json'))
        self.assertFalse(JsonBodyCodec.supports('text/plain'))


class TestJsonResponseCodec(unittest.TestCase):
    """Test JSON response encoding"""

    def setUp(self):
        self.codec = JsonResponseCodec()

    def test_encode_dict(self):
        """Encode dict"""
        data = {"name": "test", "age": 18}
        result = self.codec.encode(data)
        self.assertEqual(json.loads(result.decode('utf-8')), data)

    def test_encode_with_chinese(self):
        """Encode Chinese text"""
        data = {"name": "中文"}
        result = self.codec.encode(data)
        self.assertIn("中文", result.decode('utf-8'))

    def test_get_content_type(self):
        """Get Content-Type"""
        ct = self.codec.get_content_type()
        self.assertIn('application/json', ct)
        self.assertIn('utf-8', ct)


class TestFormBodyCodec(unittest.TestCase):
    """Test Form request body decoding"""

    def setUp(self):
        self.codec = FormBodyCodec()

    def test_decode_empty_body(self):
        """Empty body should return empty dict"""
        result = self.codec.decode(b'')
        self.assertEqual(result, {})

    def test_decode_simple_form(self):
        """Simple form decoding"""
        body = b'name=test&age=18'
        result = self.codec.decode(body)
        self.assertEqual(result, {"name": "test", "age": "18"})

    def test_decode_multi_value(self):
        """Multi-value field"""
        body = b'tags=a&tags=b&tags=c'
        result = self.codec.decode(body)
        self.assertEqual(result, {"tags": ["a", "b", "c"]})

    def test_supports_content_type(self):
        """Content-Type support detection"""
        self.assertTrue(FormBodyCodec.supports('application/x-www-form-urlencoded'))
        self.assertFalse(FormBodyCodec.supports('application/json'))


class TestCodecRegistry(unittest.TestCase):
    """Test Codec registry"""

    def setUp(self):
        reset_codec_registry()
        self.registry = get_codec_registry()

    def tearDown(self):
        reset_codec_registry()

    def test_default_codecs_registered(self):
        """Default codecs should be registered"""
        body_codecs = self.registry.list_body_codecs()
        self.assertTrue(any(c == JsonBodyCodec for c in body_codecs))
        self.assertTrue(any(c == FormBodyCodec for c in body_codecs))

    def test_get_body_codec_json(self):
        """Get JSON Codec"""
        codec = self.registry.get_body_codec('application/json')
        self.assertIsInstance(codec, JsonBodyCodec)

    def test_get_body_codec_form(self):
        """Get Form Codec"""
        codec = self.registry.get_body_codec('application/x-www-form-urlencoded')
        self.assertIsInstance(codec, FormBodyCodec)

    def test_decode_body_json(self):
        """Decode JSON via registry"""
        body = b'{"test": true}'
        result = self.registry.decode_body(body, 'application/json')
        self.assertEqual(result, {"test": True})

    def test_decode_body_form(self):
        """Decode Form via registry"""
        body = b'key=value'
        result = self.registry.decode_body(body, 'application/x-www-form-urlencoded')
        self.assertEqual(result, {"key": "value"})

    def test_encode_response(self):
        """Encode response via registry"""
        data = {"status": "ok"}
        encoded, content_type = self.registry.encode_response(data)
        self.assertIn('application/json', content_type)
        self.assertEqual(json.loads(encoded.decode('utf-8')), data)

