# -*- coding: utf-8 -*-
"""What a request that does not fit the route table is told.

Three answers were wrong before this file existed, and each one misleads a
different reader:

* every method mismatch came back ``404``, so a client that guessed the verb was
  told the resource does not exist -- and had no ``Allow`` header to correct it;
* ``OPTIONS`` on a path nobody registered answered ``204``, which reads as "yes,
  this is here", including to a CORS pre-flight;
* errors skipped the header policy, so the responses whose bodies echo user
  input were the ones without ``nosniff``.
"""

from __future__ import annotations

import asyncio

from cullinan.web.gateway.dispatcher import Dispatcher
from cullinan.web.gateway.router import Router
from cullinan.web.gateway.web_core import HeaderPolicy, WebRequest, WebResponse


def _dispatching(router: Router) -> Dispatcher:
    return Dispatcher(router=router, header_policy=HeaderPolicy())


def _send(dispatcher: Dispatcher, method: str, path: str) -> WebResponse:
    return asyncio.run(dispatcher.dispatch(WebRequest(method=method, path=path)))


def _router_with_get():
    router = Router()
    router.add_route("GET", "/probe/live", handler=lambda request: WebResponse.json({"ok": True}))
    router.add_route("POST", "/probe/live", handler=lambda request: WebResponse.json({"ok": True}))
    router.add_route("GET", "/probe/only-get", handler=lambda request: WebResponse.json({"ok": True}))
    return router


def test_a_known_path_with_the_wrong_method_answers_405_and_says_which_are_allowed():
    response = _send(_dispatching(_router_with_get()), "DELETE", "/probe/only-get")
    assert response.status_code == 405, "a resource that exists for another verb is not a 404"
    assert response.get_header("Allow") == "GET"


def test_allow_lists_every_registered_method_for_the_path():
    response = _send(_dispatching(_router_with_get()), "DELETE", "/probe/live")
    assert response.status_code == 405
    assert response.get_header("Allow") == "GET, POST"


def test_options_for_a_known_path_answers_204_with_allow():
    response = _send(_dispatching(_router_with_get()), "OPTIONS", "/probe/only-get")
    assert response.status_code == 204
    assert response.get_header("Allow") == "GET"


def test_options_for_an_unknown_path_is_404_not_204():
    response = _send(_dispatching(_router_with_get()), "OPTIONS", "/no/such/path")
    assert response.status_code == 404, (
        "204 on an unregistered path tells a client the route exists; a pre-flight "
        "for a route that does not exist has to fail like any other request"
    )


def test_error_responses_still_carry_the_security_headers():
    dispatcher = _dispatching(_router_with_get())
    for method, path in (("GET", "/no/such/path"), ("DELETE", "/probe/only-get")):
        response = _send(dispatcher, method, path)
        assert response.get_header("X-Content-Type-Options") == "nosniff", (
            f"{method} {path} returned a body without nosniff; errors echo the "
            "requested path, so this is the response that needs it most"
        )


def test_a_successful_response_is_untouched_by_the_change():
    response = _send(_dispatching(_router_with_get()), "GET", "/probe/live")
    assert response.status_code == 200
    assert response.get_header("Allow") is None
