from cullinan.application import Application, configure, get_asgi_app, module, run
from cullinan.application import bind_runtime_request_context, release_runtime_request_context
from cullinan.core import get_injection_registry, injectable
from cullinan.runtime import get_scan_stats_collector, list_submodules
from cullinan.support import get_config, get_packaging_mode
from cullinan.transport import ASGIAdapter, WebAdapter
from cullinan.web import Body, Path, WebRequest, WebResponse, controller, get_api, middleware


def test_semantic_application_facade_exports():
    assert Application is not None
    assert configure is not None
    assert run is not None
    assert get_asgi_app is not None
    assert module is not None


def test_semantic_web_facade_exports():
    assert controller is not None
    assert get_api is not None
    assert middleware is not None
    assert Path is not None
    assert Body is not None
    assert WebRequest is not None
    assert WebResponse is not None


def test_runtime_transport_support_and_core_facades():
    assert list_submodules is not None
    assert get_scan_stats_collector() is not None
    assert WebAdapter is not None
    assert ASGIAdapter is not None
    assert get_packaging_mode is not None
    assert get_config is not None
    assert injectable is not None
    assert get_injection_registry is not None
def test_application_facade_exports_runtime_context_helpers():
    assert bind_runtime_request_context is not None
    assert release_runtime_request_context is not None


def test_warn_semantic_once_concurrent_dedup():
    """Test: 20 threads calling warn_semantic_once with same key triggers only 1 warning (Issue 13 fix verification)"""
    import threading
    import warnings
    from cullinan.core.semantic_rules import warn_semantic_once, reset_semantic_warnings, CullinanSemanticWarning

    reset_semantic_warnings()
    warning_count = [0]
    count_lock = threading.Lock()

    # Capture warning count
    def warning_handler(message, category, filename, lineno, file=None, line=None):
        with count_lock:
            warning_count[0] += 1

    errors = []
    barrier = threading.Barrier(20)

    def trigger_warning():
        try:
            barrier.wait()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                warn_semantic_once(
                    key="concurrent_test_key",
                    rule_key="component-top-level",
                    problem="test problem",
                    guidance="test guidance",
                    category=CullinanSemanticWarning,
                )
                with count_lock:
                    warning_count[0] += len(w)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=trigger_warning) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors: {errors}"
    # At most 1 thread across all threads should actually trigger warning
    assert warning_count[0] <= 1, (
        f"Expected at most 1 warning, got {warning_count[0]}"
    )

    reset_semantic_warnings()
