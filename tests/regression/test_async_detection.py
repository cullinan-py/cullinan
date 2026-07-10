"""Regression test: confirm async wrappers do not mislead coroutine detection logic."""

import inspect


async def original_async_func():
    return {"status": "ok"}


def test_async_detection_distinguishes_original_and_wrapped_functions():
    assert inspect.iscoroutinefunction(original_async_func) is True

    original_result = original_async_func()
    assert inspect.iscoroutine(original_result) is True
    assert inspect.isawaitable(original_result) is True
    original_result.close()

    def bad_wrapper(func):
        def wrapper():
            return func()

        return wrapper

    wrapped_bad = bad_wrapper(original_async_func)
    assert inspect.iscoroutinefunction(wrapped_bad) is False

    wrapped_bad_result = wrapped_bad()
    assert inspect.iscoroutine(wrapped_bad_result) is True
    assert inspect.isawaitable(wrapped_bad_result) is True
    wrapped_bad_result.close()

    def good_wrapper(func):
        async def wrapper():
            return await func()

        return wrapper

    wrapped_good = good_wrapper(original_async_func)
    assert inspect.iscoroutinefunction(wrapped_good) is True

    wrapped_good_result = wrapped_good()
    assert inspect.iscoroutine(wrapped_good_result) is True
    wrapped_good_result.close()
