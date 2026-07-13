"""Dedicated regression: ensure Controller instances complete dependency injection via ApplicationContext."""

import json
import pytest

pytestmark = pytest.mark.filterwarnings(
    "ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"
)


def reset_all_registries():
    from cullinan.web.controller.registry import reset_controller_registry
    from cullinan.core import set_application_context
    from cullinan.core.pending import PendingRegistry

    reset_controller_registry()
    PendingRegistry.reset()
    set_application_context(None)


def test_bot_controller_regression():
    from cullinan.web.controller.registry import get_controller_registry
    from cullinan.core import ApplicationContext, Inject, controller, service, set_application_context

    reset_all_registries()

    class ChannelBinding:
        def __init__(self, channel_id: str, webhook_secret: str):
            self.channel_id = channel_id
            self.webhook_secret = webhook_secret

    @service
    class MultiChannelService:
        def __init__(self):
            self._bindings = {
                "owner/repo": ChannelBinding("123456789", "secret123"),
                "test/project": ChannelBinding("987654321", "secret456"),
            }

        def get_binding(self, repo_full_name: str, bot_id: str = None):
            return self._bindings.get(repo_full_name)

    @service
    class MultiBotManager:
        def __init__(self):
            self._ready = {"secondary": True, "primary": True}

        def is_ready(self, bot_id: str = None) -> bool:
            if bot_id is None:
                bot_id = "primary"
            return self._ready.get(bot_id, False)

        def send_message(self, channel_id: str, content: str = None, embed: dict = None, bot_id: str = None) -> dict:
            return {"ok": True, "msg": "sent"}

    @controller(url="/api")
    class BotController:
        multi_channel_service: MultiChannelService = Inject()
        multi_bot_manager: MultiBotManager = Inject()

        def handle_secondary_bot_notification(self, request_body: bytes):
            bot_id = "secondary"

            try:
                body_str = request_body.decode("utf-8") if isinstance(request_body, bytes) else str(request_body)
                payload = json.loads(body_str)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                return {"error": f"Invalid JSON: {exc}"}

            title = payload.get("title")
            content = payload.get("content")
            time_str = payload.get("time")
            repo_full_name = payload.get("repo")

            missing_fields = []
            if not title:
                missing_fields.append("title")
            if not content:
                missing_fields.append("content")
            if not time_str:
                missing_fields.append("time")
            if not repo_full_name:
                missing_fields.append("repo")
            if missing_fields:
                return {"error": f"Missing fields: {', '.join(missing_fields)}"}

            if not self.multi_channel_service or not hasattr(self.multi_channel_service, "get_binding"):
                return {"error": "MultiChannelService not available or not properly injected"}

            binding = self.multi_channel_service.get_binding(repo_full_name, bot_id=bot_id)
            if not binding:
                return {"error": f"Repository '{repo_full_name}' is not configured"}

            if not self.multi_bot_manager or not hasattr(self.multi_bot_manager, "is_ready"):
                return {"error": "MultiBotManager not available or not properly injected"}
            if not self.multi_bot_manager.is_ready(bot_id):
                return {"error": f"Bot '{bot_id}' is not ready"}

            response = self.multi_bot_manager.send_message(
                channel_id=binding.channel_id,
                content=f"**{title}**\n{content}\n_Time: {time_str}_",
                bot_id=bot_id,
            )
            if response.get("ok", False):
                return {"ok": True, "message": "Notification sent successfully"}
            return {"error": f"Failed to send: {response.get('msg', 'unknown')}"}

    ctx = ApplicationContext()
    set_application_context(ctx)

    try:
        ctx.refresh()

        registry = get_controller_registry()
        registry.register("BotController", BotController, url_prefix="/api")
        bot_controller = registry.get_instance("BotController")

        assert isinstance(bot_controller.multi_channel_service, Inject) is False
        assert isinstance(bot_controller.multi_bot_manager, Inject) is False
        assert hasattr(bot_controller.multi_channel_service, "get_binding") is True
        assert hasattr(bot_controller.multi_bot_manager, "is_ready") is True

        success_result = bot_controller.handle_secondary_bot_notification(
            json.dumps(
                {
                    "title": "测试通知",
                    "content": "这是一条测试消息",
                    "time": "2026-01-07 12:00:00",
                    "repo": "owner/repo",
                }
            ).encode("utf-8")
        )
        assert success_result == {"ok": True, "message": "Notification sent successfully"}

        unconfigured_result = bot_controller.handle_secondary_bot_notification(
            json.dumps(
                {
                    "title": "测试",
                    "content": "内容",
                    "time": "2026-01-07 12:00:00",
                    "repo": "unknown/repo",
                }
            ).encode("utf-8")
        )
        assert "not configured" in unconfigured_result["error"]

        missing_fields_result = bot_controller.handle_secondary_bot_notification(
            json.dumps({"title": "测试"}).encode("utf-8")
        )
        assert "Missing fields" in missing_fields_result["error"]
    finally:
        ctx.shutdown()
        reset_all_registries()
