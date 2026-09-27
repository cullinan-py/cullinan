# -*- coding: utf-8 -*-
"""Example: Unified Extension Registration Pattern

Demonstrates the new decorator-based middleware registration and 
extension point discovery API introduced in Task-7.2.

This example shows:
1. Using the @middleware decorator for automatic registration
2. Priority-based middleware ordering
3. Discovering available extension points
4. Mixing decorator and manual registration

Author: plumeink
"""

import logging
from cullinan.web import middleware, Middleware
from cullinan.support.extensions import list_extension_points, ExtensionCategory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Example 1: Decorator-based Middleware Registration
# ============================================================================

@middleware(priority=10)
class CorsMiddleware(Middleware):
    """CORS middleware - runs first (low priority number)."""
    
    def process_request(self, handler):
        logger.info("CORS: Adding CORS headers")
        # Add CORS headers
        return handler  # Continue to next middleware
    
    def process_response(self, handler, response):
        logger.info("CORS: Response processed")
        return response


@middleware(priority=50)
class AuthenticationMiddleware(Middleware):
    """Authentication middleware - runs after CORS."""
    
    def process_request(self, handler):
        logger.info("Auth: Checking authentication")
        # Check authentication token
        token = getattr(handler, 'request', None)
        if token:
            logger.info("Auth: User authenticated")
        return handler  # Continue
    
    def process_response(self, handler, response):
        logger.info("Auth: Response processed")
        return response


@middleware(priority=100)
class LoggingMiddleware(Middleware):
    """Logging middleware - runs after auth."""
    
    def on_init(self):
        logger.info("Logging middleware initialized")
    
    def process_request(self, handler):
        logger.info("Logging: Request received")
        return handler
    
    def process_response(self, handler, response):
        logger.info("Logging: Request completed")
        return response


@middleware(priority=150)
class MetricsMiddleware(Middleware):
    """Metrics middleware - runs last."""
    
    def __init__(self):
        super().__init__()
        self.request_count = 0
    
    def process_request(self, handler):
        self.request_count += 1
        logger.info(f"Metrics: Request #{self.request_count}")
        return handler
    
    def process_response(self, handler, response):
        logger.info(f"Metrics: Total requests: {self.request_count}")
        return response


# ============================================================================
# Example 2: Extension Point Discovery
# ============================================================================

def discover_extension_points():
    """Discover and display available extension points."""
    print("\n" + "=" * 70)
    print("Available Extension Points")
    print("=" * 70)
    
    # List all extension points
    all_points = list_extension_points()
    print(f"\nTotal extension points: {len(all_points)}")
    
    # Group by category
    categories = {}
    for point in all_points:
        cat = point['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(point)
    
    # Display by category
    for category, points in sorted(categories.items()):
        print(f"\n{category.upper()} ({len(points)} points):")
        for point in points:
            print(f"  - {point['name']}")
            print(f"    {point['description']}")
            if point['example_url']:
                print(f"    Docs: {point['example_url']}")


# ============================================================================
# Example 3: Middleware Execution Demo
# ============================================================================

def demo_middleware_execution():
    """Demonstrate middleware execution order."""
    from cullinan.web.middleware import get_middleware_registry
    
    print("\n" + "=" * 70)
    print("Middleware Execution Demo")
    print("=" * 70)
    
    registry = get_middleware_registry()
    
    # Show registered middleware
    registered = registry.get_registered_middleware()
    print("\nRegistered middleware (in priority order):")
    for mw in sorted(registered, key=lambda x: x['priority']):
        print(f"  {mw['priority']:3d}: {mw['name']}")
    
    # Create middleware chain
    chain = registry.get_middleware_chain()
    
    # Simulate request processing
    print("\n--- Simulating Request Processing ---")
    
    class MockHandler:
        def __init__(self):
            self.request = "mock_request"
    
    handler = MockHandler()
    
    # Process request through chain
    print("\n-> Request Phase (in priority order):")
    result = chain.process_request(handler)
    
    # Process response through chain
    print("\n<- Response Phase (in reverse order):")
    response = {"status": 200, "body": "OK"}
    chain.process_response(handler, response)
    
    print("\n[OK] Request/response cycle complete")


# ============================================================================
# Example 4: Manual Registration (Backward Compatibility)
# ============================================================================

class CustomMiddleware(Middleware):
    """Custom middleware registered manually."""
    
    def process_request(self, handler):
        logger.info("Custom: Manual registration still works!")
        return handler


def demo_manual_registration():
    """Demonstrate manual registration for backward compatibility."""
    from cullinan.web.middleware import get_middleware_registry
    
    print("\n" + "=" * 70)
    print("Manual Registration (Backward Compatibility)")
    print("=" * 70)
    
    registry = get_middleware_registry()
    
    # Manual registration
    registry.register(CustomMiddleware, priority=75)
    
    registered = registry.get_registered_middleware()
    print(f"\nTotal registered middleware: {len(registered)}")
    
    # Find our manually registered middleware
    custom = [mw for mw in registered if mw['name'] == 'CustomMiddleware']
    if custom:
        print(f"[OK] Manual registration successful: {custom[0]['name']} (priority: {custom[0]['priority']})")


# ============================================================================
# Example 5: Querying Specific Extension Categories
# ============================================================================

def query_middleware_extensions():
    """Query middleware-specific extension points."""
    print("\n" + "=" * 70)
    print("Middleware Extension Points")
    print("=" * 70)
    
    from cullinan.support.extensions import get_extension_registry
    
    registry = get_extension_registry()
    middleware_points = registry.get_extension_points(
        category=ExtensionCategory.MIDDLEWARE
    )
    
    print(f"\nFound {len(middleware_points)} middleware extension points:\n")
    
    for point in middleware_points:
        print(f"  [ExtensionPoint] {point.name}")
        print(f"   Description: {point.description}")
        print(f"   Interface: {point.interface.__name__ if point.interface else 'N/A'}")
        print(f"   Documentation: {point.example_url or 'N/A'}")
        print()


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Run all examples."""
    print("\n")
    print("+" + "=" * 68 + "+")
    print("|" + " " * 68 + "|")
    print("|" + "  Cullinan Framework - Unified Extension Pattern Demo".center(68) + "|")
    print("|" + "  Task-7.2: Extension Registration & Discovery".center(68) + "|")
    print("|" + " " * 68 + "|")
    print("+" + "=" * 68 + "+")
    
    # Run examples
    discover_extension_points()
    query_middleware_extensions()
    demo_middleware_execution()
    demo_manual_registration()
    
    print("\n" + "=" * 70)
    print("Demo Complete!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1. Use @middleware(priority=N) for automatic registration")
    print("  2. Lower priority numbers execute first")
    print("  3. Manual registration still works for backward compatibility")
    print("  4. Extension points are discoverable via API")
    print("  5. Consistent pattern with @service and @controller")
    print()


if __name__ == '__main__':
    main()
