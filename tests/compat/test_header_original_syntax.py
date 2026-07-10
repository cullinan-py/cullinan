# -*- coding: utf-8 -*-
"""Regression test for Header and RawBody historical syntax compatibility."""

from cullinan.web.params import Header, ParamResolver, RawBody


def handle_webhook_v1(
    self,
    sign: Header(str, alias="X-Hub-Signature-256"),
    event: Header(str, alias="X-GitHub-Event"),
    raw_body: RawBody,
):
    pass


def handle_webhook_v2(
    self,
    sign: Header(str, alias="X-Hub-Signature-256"),
    event: Header(str, alias="X-GitHub-Event"),
    raw_body: RawBody(),
):
    pass


class MockRequest:
    body = b'{"action": "push", "ref": "refs/heads/main"}'


def test_rawbody_annotation_form_remains_compatible():
    config = ParamResolver.analyze_params(handle_webhook_v1)

    assert config["raw_body"]["source"] == "raw_body"
    assert config["raw_body"]["type"] is bytes


def test_rawbody_instance_form_remains_compatible():
    config = ParamResolver.analyze_params(handle_webhook_v2)

    assert config["raw_body"]["source"] == "raw_body"
    assert config["raw_body"]["type"] is bytes


def test_header_and_rawbody_compatibility_syntax_still_resolves_values():
    resolved = ParamResolver.resolve(
        func=handle_webhook_v1,
        request=MockRequest(),
        url_params={},
        query_params={},
        body_data={"action": "push"},
        headers={
            "X-Hub-Signature-256": "sha256=abc123",
            "X-Github-Event": "push",
        },
        files={},
    )

    assert resolved["sign"] == "sha256=abc123"
    assert resolved["event"] == "push"
    assert resolved["raw_body"] == b'{"action": "push", "ref": "refs/heads/main"}'
    assert isinstance(resolved["raw_body"], bytes)
