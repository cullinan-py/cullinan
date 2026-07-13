# -*- coding: utf-8 -*-
"""Integration regression for the parameter system in controller methods."""

import inspect

from cullinan.web.controller.core import DynamicBody, ParamResolver, request_handler
from cullinan.web.params import Body, Header, Path, Query


class MockController:
    def hello_dynamic(self, body: DynamicBody):
        name = body.get("name", "World")
        return {"message": f"Hello, {name}!"}

    def hello_typed(self, name: Body(str, default="World")):
        return {"message": f"Hello, {name}!"}

    def get_user(self, id: Path(int), verbose: Query(bool, default=False)):
        return {"id": id, "verbose": verbose}

    def legacy_style(self, body_params):
        name = body_params.get("name", "World") if body_params else "World"
        return {"message": f"Hello, {name}!"}


def test_controller_core_keeps_request_handler_available():
    signature = inspect.signature(request_handler)

    assert callable(request_handler)
    assert "self" in signature.parameters
    assert "func" in signature.parameters
    assert "params" in signature.parameters
    assert "headers" in signature.parameters


def test_param_resolver_distinguishes_new_param_system_from_legacy_signature():
    methods = {
        "hello_dynamic": True,
        "hello_typed": True,
        "get_user": True,
        "legacy_style": False,
    }

    for method_name, expected_new_system in methods.items():
        config = ParamResolver.analyze_params(getattr(MockController, method_name))
        uses_new_system = any(
            cfg.get("param_spec") is not None or cfg.get("type") is DynamicBody
            for cfg in config.values()
        )
        assert uses_new_system is expected_new_system


def test_param_resolver_resolves_dynamic_typed_and_path_query_inputs():
    dynamic = ParamResolver.resolve(
        func=MockController.hello_dynamic,
        request=None,
        body_data={"name": "Cullinan"},
    )
    typed = ParamResolver.resolve(
        func=MockController.hello_typed,
        request=None,
        body_data={"name": "TypedUser"},
    )
    path_query = ParamResolver.resolve(
        func=MockController.get_user,
        request=None,
        url_params={"id": "42"},
        query_params={"verbose": "true"},
    )

    assert dynamic["body"].name == "Cullinan"
    assert MockController().hello_dynamic(dynamic["body"]) == {"message": "Hello, Cullinan!"}

    assert typed["name"] == "TypedUser"
    assert MockController().hello_typed(typed["name"]) == {"message": "Hello, TypedUser!"}

    assert path_query == {"id": 42, "verbose": True}


def test_param_resolver_keeps_header_assignment_style_compatible():
    def handler(self, auth: str = Header(alias="Authorization", required=True)):
        return auth

    config = ParamResolver.analyze_params(handler)
    resolved = ParamResolver.resolve(
        func=handler,
        request=None,
        headers={"Authorization": "Bearer token"},
    )

    assert config["auth"]["source"] == "header"
    assert resolved["auth"] == "Bearer token"
