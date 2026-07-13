# -*- coding: utf-8 -*-
"""RawBody and DynamicBody assignment syntax regression."""

from cullinan.web.params import DynamicBody, Header, ParamResolver, RawBody


def handle_webhook(
    self,
    sign: str = Header(alias="X-Hub-Signature-256", required=True),
    event: str = Header(alias="X-GitHub-Event", required=True),
    request_body: bytes = RawBody(),
):
    pass


def handle_body(
    self,
    name: str = Header(alias="X-Name"),
    body: dict = DynamicBody(),
):
    pass


class MockRequest:
    body = b'{"action": "push"}'


def test_rawbody_assignment_syntax_analyzes_as_bytes():
    config = ParamResolver.analyze_params(handle_webhook)

    assert config["request_body"]["source"] == "raw_body"
    assert config["request_body"]["type"] is bytes
    assert config["sign"]["source"] == "header"
    assert config["event"]["source"] == "header"


def test_dynamicbody_assignment_syntax_keeps_body_source():
    config = ParamResolver.analyze_params(handle_body)

    assert config["body"]["source"] == "body"
    assert config["body"]["type"] is DynamicBody
    assert config["name"]["source"] == "header"


def test_rawbody_assignment_syntax_resolves_request_body_bytes():
    resolved = ParamResolver.resolve(
        func=handle_webhook,
        request=MockRequest(),
        url_params={},
        query_params={},
        body_data={},
        headers={"X-Hub-Signature-256": "sha256=abc", "X-Github-Event": "push"},
        files={},
    )

    assert resolved["sign"] == "sha256=abc"
    assert resolved["event"] == "push"
    assert resolved["request_body"] == b'{"action": "push"}'
    assert isinstance(resolved["request_body"], bytes)
