# -*- coding: utf-8 -*-
"""Legacy compatibility demo for the 0.90 decorator system.

Author: plumeink
"""

import warnings
warnings.filterwarnings("ignore")

from cullinan.core import (
    service,
    controller,
    component,
    ApplicationContext,
    PendingRegistry,
)
from cullinan.core.decorators import Inject, InjectByName, Lazy
from cullinan.core.conditions import ConditionalOnClass, Conditional

print("=" * 60)
print("Cullinan 0.90 Legacy Decorator System Demo")
print("=" * 60)

# Reset registry for demo
PendingRegistry.reset()

# Define services
@service
class EmailService:
    def send(self, to: str, content: str) -> str:
        return f"Email sent to {to}: {content}"

@service
class UserService:
    email_service: EmailService = Inject()
    
    def get_user(self, id: int) -> dict:
        return {"id": id, "name": f"User{id}"}
    
    def notify_user(self, id: int) -> str:
        user = self.get_user(id)
        return self.email_service.send(f"{user['name']}@example.com", "Hello!")

# Define controller
@controller(url="/api/users")
class UserController:
    user_service: UserService = Inject()
    
    def get_user(self, id: int) -> dict:
        return self.user_service.get_user(id)
    
    def notify(self, id: int) -> str:
        return self.user_service.notify_user(id)

# Conditional component
@service
@ConditionalOnClass("json")
class JsonProcessor:
    def process(self, data: dict) -> str:
        import json
        return json.dumps(data)

# Create and refresh context
ctx = ApplicationContext()
ctx.refresh()

print(f"\nRegistered components: {ctx.definition_count}")
print(f"Components: {ctx.list_definitions()}")

# Test services
print("\n--- Testing Services ---")
user_service = ctx.get("UserService")
print(f"UserService.get_user(1): {user_service.get_user(1)}")
print(f"UserService.notify_user(1): {user_service.notify_user(1)}")

# Test controller
print("\n--- Testing Controller ---")
controller = ctx.get("UserController")
print(f"UserController.get_user(42): {controller.get_user(42)}")
print(f"UserController.notify(42): {controller.notify(42)}")

# Test conditional
print("\n--- Testing Conditional ---")
json_processor = ctx.get("JsonProcessor")
print(f"JsonProcessor.process: {json_processor.process({'status': 'ok'})}")

print("\n" + "=" * 60)
print("Demo completed successfully!")
print("=" * 60)
