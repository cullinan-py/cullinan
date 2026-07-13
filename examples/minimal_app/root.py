from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class GreetingService:
    def build_message(self) -> str:
        return "Hello from the Cullinan public API."


@controller(url="/hello")
class HelloController:
    greeting_service: GreetingService  # ← constructor injection

    @get_api(url="")
    def hello(self):
        return {
            "message": self.greeting_service.build_message(),
            "entrypoint": "@application + @configure(...) + main()",
        }


@configure(user_packages=["examples.minimal_app"], server_port=4081)
@application
def main(): ...


__all__ = ["main"]
