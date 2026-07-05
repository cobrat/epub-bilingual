from __future__ import annotations

from dataclasses import dataclass, field
import threading


@dataclass
class ProfileMetrics:
    cache_hits: int = 0
    cache_misses: int = 0
    fully_cached_batches: int = 0
    partially_cached_batches: int = 0
    uncached_batches: int = 0
    llm_batches: int = 0
    llm_requested_segments: int = 0
    raw_llm_requests: int = 0
    fallback_count: int = 0
    retry_count: int = 0
    llm_batch_sizes: list[int] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def record_cache_result(self, hits: int, misses: int) -> None:
        with self._lock:
            self.cache_hits += hits
            self.cache_misses += misses

    def record_batch_plan(self, hits: int, misses: int) -> None:
        with self._lock:
            if hits and misses:
                self.partially_cached_batches += 1
            elif hits:
                self.fully_cached_batches += 1
            else:
                self.uncached_batches += 1

    def record_llm_batch(self, size: int) -> None:
        with self._lock:
            self.llm_batches += 1
            self.llm_requested_segments += size
            self.llm_batch_sizes.append(size)

    def record_raw_llm_request(self) -> None:
        with self._lock:
            self.raw_llm_requests += 1

    def record_fallback(self) -> None:
        with self._lock:
            self.fallback_count += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retry_count += 1

    def to_dict(self) -> dict[str, object]:
        with self._lock:
            batch_sizes = list(self.llm_batch_sizes)
            if batch_sizes:
                batch_size_min: int | None = min(batch_sizes)
                batch_size_max: int | None = max(batch_sizes)
                batch_size_avg: float | None = sum(batch_sizes) / len(batch_sizes)
            else:
                batch_size_min = None
                batch_size_max = None
                batch_size_avg = None
            return {
                "cache": {
                    "hits": self.cache_hits,
                    "misses": self.cache_misses,
                    "fully_cached_batches": self.fully_cached_batches,
                    "partially_cached_batches": self.partially_cached_batches,
                    "uncached_batches": self.uncached_batches,
                },
                "llm": {
                    "batches": self.llm_batches,
                    "requested_segments": self.llm_requested_segments,
                    "raw_requests": self.raw_llm_requests,
                    "fallbacks": self.fallback_count,
                    "retries": self.retry_count,
                    "batch_size_min": batch_size_min,
                    "batch_size_max": batch_size_max,
                    "batch_size_avg": batch_size_avg,
                },
            }
