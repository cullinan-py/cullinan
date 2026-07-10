from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class QuoteService:
    def sample(self) -> str:
        return "Public API testing keeps examples stable."


@controller(url="/notes")
class NotesController:
    quote_service: QuoteService  # ← constructor injection

    @get_api(url="/sample")
    def sample(self):
        return {"message": self.quote_service.sample(), "tested_via": "get_asgi_app()"}


@configure(user_packages=["examples.testing_flow"])
@application
def main(): ...


__all__ = ["main"]
