# -*- coding: utf-8 -*-
"""Module scanning statistics and monitoring utilities.

Provides detailed statistics and monitoring capabilities for the module
scanning process, helping developers understand scanning performance
and identify optimization opportunities.

Author: plumeink
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ScanPhase(Enum):
    """Module scanning phases."""
    INITIALIZATION = "initialization"
    DISCOVERY = "discovery"
    FILTERING = "filtering"
    VALIDATION = "validation"
    CACHING = "caching"


@dataclass
class ScanStatistics:
    """Statistics for a module scanning operation.

    Attributes:
        total_duration_ms: Total scanning duration in milliseconds
        modules_found: Total number of modules discovered
        modules_filtered: Number of modules filtered out
        modules_cached: Number of modules retrieved from cache
        phase_durations: Duration of each scanning phase
        scan_mode: Scanning mode (auto, explicit, cached)
        packaging_mode: Packaging environment (development, nuitka, pyinstaller)
        errors: List of errors encountered during scanning
    """

    total_duration_ms: float = 0.0
    modules_found: int = 0
    modules_filtered: int = 0
    modules_cached: int = 0
    phase_durations: Dict[str, float] = field(default_factory=dict)
    scan_mode: str = "auto"
    packaging_mode: str = "unknown"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary for logging/monitoring."""
        return {
            'total_duration_ms': round(self.total_duration_ms, 2),
            'modules_found': self.modules_found,
            'modules_filtered': self.modules_filtered,
            'modules_cached': self.modules_cached,
            'phase_durations_ms': {
                phase: round(duration, 2)
                for phase, duration in self.phase_durations.items()
            },
            'scan_mode': self.scan_mode,
            'packaging_mode': self.packaging_mode,
            'error_count': len(self.errors),
        }

    def add_phase_duration(self, phase: ScanPhase, duration_ms: float):
        """Add duration for a specific phase."""
        self.phase_durations[phase.value] = duration_ms

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)

    def is_slow(self, threshold_ms: float = 1000.0) -> bool:
        """Check if scanning was slow."""
        return self.total_duration_ms > threshold_ms

    def get_summary(self) -> str:
        """Get a human-readable summary."""
        return (
            f"Scanned {self.modules_found} modules in {self.total_duration_ms:.2f}ms "
            f"(mode: {self.scan_mode}, env: {self.packaging_mode})"
        )


class ScanStatsCollector:
    """Collects and manages module scanning statistics.

    Provides context managers for phase timing and aggregates
    statistics across multiple scanning operations.
    """

    def __init__(self):
        """Initialize the statistics collector."""
        self._current_stats: Optional[ScanStatistics] = None
        self._phase_start_times: Dict[str, float] = {}
        self._all_scans: List[ScanStatistics] = []

    def start_scan(self, scan_mode: str = "auto", packaging_mode: str = "unknown"):
        """Start collecting statistics for a new scan operation.

        Args:
            scan_mode: The scanning mode (auto, explicit, cached)
            packaging_mode: The packaging environment
        """
        self._current_stats = ScanStatistics(
            scan_mode=scan_mode,
            packaging_mode=packaging_mode
        )
        logger.debug(f"Started scan statistics collection (mode: {scan_mode})")

    def start_phase(self, phase: ScanPhase):
        """Start timing a specific scanning phase.

        Args:
            phase: The scanning phase to time
        """
        self._phase_start_times[phase.value] = time.perf_counter()
        logger.debug(f"Started phase: {phase.value}")

    def end_phase(self, phase: ScanPhase):
        """End timing a specific scanning phase.

        Args:
            phase: The scanning phase to end
        """
        if phase.value in self._phase_start_times:
            start_time = self._phase_start_times[phase.value]
            duration_ms = (time.perf_counter() - start_time) * 1000

            if self._current_stats:
                self._current_stats.add_phase_duration(phase, duration_ms)

            logger.debug(f"Completed phase: {phase.value} ({duration_ms:.2f}ms)")
            del self._phase_start_times[phase.value]

    def record_modules_found(self, count: int):
        """Record the number of modules found.

        Args:
            count: Number of modules discovered
        """
        if self._current_stats:
            self._current_stats.modules_found = count

    def record_modules_filtered(self, count: int):
        """Record the number of modules filtered out.

        Args:
            count: Number of modules filtered
        """
        if self._current_stats:
            self._current_stats.modules_filtered = count

    def record_modules_cached(self, count: int):
        """Record the number of modules from cache.

        Args:
            count: Number of cached modules
        """
        if self._current_stats:
            self._current_stats.modules_cached = count

    def record_error(self, error: str):
        """Record an error encountered during scanning.

        Args:
            error: Error message
        """
        if self._current_stats:
            self._current_stats.add_error(error)
        logger.debug(f"Recorded scan error: {error}")

    def end_scan(self, total_duration_ms: float) -> ScanStatistics:
        """End the current scan and return statistics.

        Args:
            total_duration_ms: Total scanning duration

        Returns:
            The collected statistics
        """
        if not self._current_stats:
            logger.warning("end_scan called without start_scan")
            return ScanStatistics()

        self._current_stats.total_duration_ms = total_duration_ms
        self._all_scans.append(self._current_stats)

        stats = self._current_stats
        self._current_stats = None

        logger.debug(f"Completed scan: {stats.get_summary()}")
        return stats

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all scans.

        Returns:
            Aggregate statistics dictionary
        """
        if not self._all_scans:
            return {
                'total_scans': 0,
                'avg_duration_ms': 0.0,
                'total_modules': 0,
                'total_errors': 0,
            }

        total_duration = sum(s.total_duration_ms for s in self._all_scans)
        total_modules = sum(s.modules_found for s in self._all_scans)
        total_errors = sum(len(s.errors) for s in self._all_scans)

        return {
            'total_scans': len(self._all_scans),
            'avg_duration_ms': round(total_duration / len(self._all_scans), 2),
            'total_modules': total_modules,
            'total_errors': total_errors,
            'fastest_scan_ms': round(min(s.total_duration_ms for s in self._all_scans), 2),
            'slowest_scan_ms': round(max(s.total_duration_ms for s in self._all_scans), 2),
        }

    def reset(self):
        """Reset all collected statistics."""
        self._current_stats = None
        self._phase_start_times.clear()
        self._all_scans.clear()
        logger.debug("Reset scan statistics")


# Global statistics collector
_stats_collector: Optional[ScanStatsCollector] = None


def get_scan_stats_collector() -> ScanStatsCollector:
    """Get the global scan statistics collector.

    Returns:
        The global ScanStatsCollector instance
    """
    global _stats_collector
    if _stats_collector is None:
        _stats_collector = ScanStatsCollector()
    return _stats_collector


def reset_scan_stats_collector():
    """Reset the global scan statistics collector."""
    global _stats_collector
    if _stats_collector:
        _stats_collector.reset()
    _stats_collector = None


def log_scan_statistics(stats: ScanStatistics, level: str = "info"):
    """Log scanning statistics in a structured format.

    Args:
        stats: The statistics to log
        level: Log level (debug, info, warning, error)
    """
    log_func = getattr(logger, level, logger.info)

    # Basic summary
    log_func(stats.get_summary())

    # Detailed stats (debug level)
    if level == "debug" or stats.is_slow():
        log_func("Scan details:", extra=stats.to_dict())

        # Phase breakdown
        if stats.phase_durations:
            phase_summary = ", ".join(
                f"{phase}: {duration:.2f}ms"
                for phase, duration in stats.phase_durations.items()
            )
            log_func(f"Phase breakdown: {phase_summary}")

        # Errors
        if stats.errors:
            log_func(f"Encountered {len(stats.errors)} errors during scanning")
            for error in stats.errors[:5]:  # Show first 5 errors
                logger.warning(f"Scan error: {error}")

    # Performance warning
    if stats.is_slow(threshold_ms=1000.0):
        logger.warning(
            f"Slow module scanning detected ({stats.total_duration_ms:.2f}ms). "
            "Consider using explicit registration or configuring user_packages."
        )


def export_scan_statistics(output_file: str = "scan_stats.json"):
    """Export all collected statistics to a JSON file.

    Args:
        output_file: Output file path
    """
    import json

    collector = get_scan_stats_collector()
    data = {
        'aggregate': collector.get_aggregate_stats(),
        'scans': [stats.to_dict() for stats in collector._all_scans]
    }

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Exported scan statistics to {output_file}")
    except Exception as e:
        logger.error(f"Failed to export statistics: {e}")

