# -*- coding: utf-8 -*-
"""Conditional decorators for Cullinan framework.

This module provides condition-based component registration:
- @ConditionalOnProperty: Register based on configuration property
- @ConditionalOnClass: Register based on class availability
- @ConditionalOnMissingBean: Register when specific bean is missing

The conditions are stored on the class itself using a special attribute,
and will be collected when @Service/@Controller/@Component decorator runs.

Author: plumeink
"""

from typing import Callable, Type, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .application_context import ApplicationContext


# Special attribute name to store conditions on classes
_CONDITIONS_ATTR = '_cullinan_conditions_'


def _add_condition_to_class(cls: Type, condition: Callable) -> Type:
    """Add a condition to a class's condition list.

    This stores conditions on the class itself, to be collected later
    by @Service/@Controller/@Component decorators.
    """
    if not hasattr(cls, _CONDITIONS_ATTR):
        setattr(cls, _CONDITIONS_ATTR, [])
    getattr(cls, _CONDITIONS_ATTR).append(condition)
    return cls


def get_class_conditions(cls: Type) -> List[Callable]:
    """Get all conditions stored on a class."""
    return getattr(cls, _CONDITIONS_ATTR, [])


def clear_class_conditions(cls: Type) -> None:
    """Clear conditions from a class (after they've been collected)."""
    if hasattr(cls, _CONDITIONS_ATTR):
        delattr(cls, _CONDITIONS_ATTR)


def ConditionalOnProperty(
    property_name: str,
    having_value: str = "true",
    match_if_missing: bool = False
):
    """Conditional decorator: register based on configuration property.
    
    The component will only be registered if the specified property
    has the expected value.
    
    Usage:
        @Service()
        @ConditionalOnProperty("feature.email", having_value="true")
        class EmailService:
            pass
    
    Args:
        property_name: The property name to check
        having_value: The expected value (default "true")
        match_if_missing: Whether to match if property is missing (default False)
    
    Returns:
        Decorator function
    """
    def condition(ctx: 'ApplicationContext') -> bool:
        # Try to get property from context
        value = None
        if hasattr(ctx, 'get_property'):
            value = ctx.get_property(property_name)
        elif hasattr(ctx, 'config') and ctx.config:
            value = ctx.config.get(property_name)
        
        if value is None:
            return match_if_missing
        
        return str(value).lower() == having_value.lower()
    
    def decorator(cls: Type) -> Type:
        return _add_condition_to_class(cls, condition)

    return decorator


def ConditionalOnClass(class_name: str):
    """Conditional decorator: register based on class availability.
    
    The component will only be registered if the specified class
    can be imported.
    
    Usage:
        @Service()
        @ConditionalOnClass("redis.Redis")
        class RedisCacheService:
            pass
    
    Args:
        class_name: Fully qualified class name (e.g., "redis.Redis")
    
    Returns:
        Decorator function
    """
    def condition(ctx: 'ApplicationContext') -> bool:
        try:
            parts = class_name.rsplit('.', 1)
            if len(parts) == 2:
                module_name, cls_name = parts
                module = __import__(module_name, fromlist=[cls_name])
                getattr(module, cls_name)
            else:
                __import__(class_name)
            return True
        except (ImportError, AttributeError):
            return False
    
    def decorator(cls: Type) -> Type:
        return _add_condition_to_class(cls, condition)

    return decorator


def ConditionalOnMissingBean(bean_name: str):
    """Conditional decorator: register when specific bean is missing.
    
    The component will only be registered if no bean with the
    specified name is already registered.
    
    Usage:
        @Service()
        @ConditionalOnMissingBean("CustomEmailService")
        class DefaultEmailService:
            pass
    
    Args:
        bean_name: The bean name to check for
    
    Returns:
        Decorator function
    """
    def condition(ctx: 'ApplicationContext') -> bool:
        return not ctx.has(bean_name)
    
    def decorator(cls: Type) -> Type:
        return _add_condition_to_class(cls, condition)

    return decorator


def ConditionalOnBean(bean_name: str):
    """Conditional decorator: register when specific bean exists.
    
    The component will only be registered if a bean with the
    specified name is already registered.
    
    Usage:
        @Service()
        @ConditionalOnBean("DatabaseConnection")
        class DatabaseService:
            pass
    
    Args:
        bean_name: The bean name to check for
    
    Returns:
        Decorator function
    """
    def condition(ctx: 'ApplicationContext') -> bool:
        return ctx.has(bean_name)
    
    def decorator(cls: Type) -> Type:
        return _add_condition_to_class(cls, condition)

    return decorator


def Conditional(condition_func: Callable[['ApplicationContext'], bool]):
    """Generic conditional decorator with custom condition function.
    
    Usage:
        def is_production(ctx):
            return ctx.get_property("env") == "production"
        
        @Service()
        @Conditional(is_production)
        class ProductionOnlyService:
            pass
    
    Args:
        condition_func: Function that takes ApplicationContext and returns bool
    
    Returns:
        Decorator function
    """
    def decorator(cls: Type) -> Type:
        return _add_condition_to_class(cls, condition_func)

    return decorator


__all__ = [
    'ConditionalOnProperty',
    'ConditionalOnClass',
    'ConditionalOnMissingBean',
    'ConditionalOnBean',
    'Conditional',
]

