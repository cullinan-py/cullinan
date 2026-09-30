from cullinan import Middleware, middleware


@middleware(priority=50)
class ExampleModuleBoundaryMiddleware(Middleware):
    def process_request(self, request):
        request.attributes["module_boundary"] = "examples.middleware_and_module"
        return request

    def process_response(self, request, response):
        response.set_header("X-Cullinan-Example", "middleware-and-module")
        response.set_header(
            "X-Module-Boundary",
            request.attributes.get("module_boundary", "unknown"),
        )
        return response
