"""Verify that Service lifecycle hooks are triggered during container lifecycle."""

import pytest

from cullinan.core import ApplicationContext, InjectByName, set_application_context
from cullinan.core.pending import PendingRegistry
from cullinan.core.services import Service, service

pytestmark = [
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"),
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.InjectionSemanticWarning"),
]


def test_lifecycle_hooks_run_with_application_context():
    PendingRegistry.reset()
    lifecycle_events = {
        "email_post_construct": False,
        "email_pre_destroy": False,
        "user_post_construct": False,
        "user_pre_destroy": False,
    }

    @service
    class EmailService(Service):
        def on_post_construct(self):
            lifecycle_events["email_post_construct"] = True
            self.initialized = True

        def on_pre_destroy(self):
            lifecycle_events["email_pre_destroy"] = True

        def send_email(self, to):
            return f"Email sent to {to}"

    @service
    class UserService(Service):
        email_service = InjectByName("EmailService")

        def on_post_construct(self):
            lifecycle_events["user_post_construct"] = True
            self.initialized = True

        def on_pre_destroy(self):
            lifecycle_events["user_pre_destroy"] = True

        def create_user(self, email):
            return self.email_service.send_email(email)

    ctx = ApplicationContext()
    set_application_context(ctx)

    try:
        ctx.refresh()

        email_service = ctx.get("EmailService")
        user_service = ctx.get("UserService")

        assert "EmailService" in ctx.list_definitions()
        assert "UserService" in ctx.list_definitions()
        assert getattr(email_service, "initialized", False) is True
        assert getattr(user_service, "initialized", False) is True
        assert user_service.email_service is email_service
        assert user_service.create_user("test@example.com") == "Email sent to test@example.com"
    finally:
        ctx.shutdown()
        set_application_context(None)
        PendingRegistry.reset()

    assert lifecycle_events == {
        "email_post_construct": True,
        "email_pre_destroy": True,
        "user_post_construct": True,
        "user_pre_destroy": True,
    }
