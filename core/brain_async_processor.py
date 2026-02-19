#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

BrainProcessFn = Callable[[str, str, str], Awaitable[Dict[str, Any]]]
BrainMemorySinkFn = Callable[["BrainTask", "BrainResult"], None]


@dataclass(frozen=True)
class BrainTask:
    task_id: str
    audio_path: str
    user_input: str
    user_key: str  # namespaced user id: "{persona}::{canonical_user_id}"
    submitted_at: datetime
    priority: int = 1


@dataclass(frozen=True)
class BrainResult:
    task_id: str
    user_key: str
    success: bool
    environment_analysis: Dict[str, Any]
    memory_context: str
    dynamic_prompt: str
    processing_time: float
    created_at: datetime


class BrainAsyncProcessor:
    """
    A single daemon worker that consumes brain tasks and caches results.

    Contract:
    - submit_task_fire_and_forget() never blocks the caller.
    - a single event loop lives in a dedicated daemon thread.
    """

    def __init__(self, *, process_fn: Optional[BrainProcessFn] = None, memory_sink_fn: Optional[BrainMemorySinkFn] = None):
        self.max_cache_size = 50
        self.cache_expire_time = timedelta(minutes=10)
        self.max_concurrent_tasks = 3

        self._process_fn_lock = threading.Lock()
        self._process_fn: Optional[BrainProcessFn] = process_fn
        self._memory_sink_fn: Optional[BrainMemorySinkFn] = memory_sink_fn

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue[BrainTask]] = None
        self._running = threading.Event()
        self._ready = threading.Event()

        self._cache_lock = threading.Lock()
        self._result_by_task: Dict[str, BrainResult] = {}
        self._latest_by_user: Dict[str, BrainResult] = {}

        self._metrics_lock = threading.Lock()
        self._enqueued_total = 0
        self._processed_total = 0

    def ensure_started(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._running.set()
        self._ready.clear()

        def _run() -> None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._queue = asyncio.Queue(maxsize=100)
                self._ready.set()
                logger.info("[brain] worker_started")
                loop.create_task(self._worker_loop())
                loop.run_forever()
            except Exception as e:
                logger.error(f"[brain] worker_crashed error={e}")
                self._ready.set()
            finally:
                try:
                    if self._loop and self._loop.is_running():
                        self._loop.stop()
                except Exception:
                    pass

        self._thread = threading.Thread(target=_run, daemon=True, name="BrainAsyncProcessor")
        self._thread.start()
        self._ready.wait(timeout=1.0)

    def set_process_fn(self, process_fn: Optional[BrainProcessFn]) -> None:
        with self._process_fn_lock:
            self._process_fn = process_fn

    def set_memory_sink_fn(self, memory_sink_fn: Optional[BrainMemorySinkFn]) -> None:
        self._memory_sink_fn = memory_sink_fn

    def stop(self) -> None:
        self._running.clear()
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        logger.info("[brain] worker_stopping")

    def submit_task_fire_and_forget(self, audio_path: str, user_input: str, user_key: str, priority: int = 1) -> str:
        self.ensure_started()

        task_id = f"brain_{int(time.time() * 1000)}"
        task = BrainTask(
            task_id=task_id,
            audio_path=audio_path,
            user_input=user_input,
            user_key=user_key,
            submitted_at=datetime.now(),
            priority=priority,
        )

        loop = self._loop
        queue = self._queue
        if loop is None or queue is None:
            logger.error("[brain] enqueue_failed reason=not_ready")
            return ""

        async def _put() -> None:
            await queue.put(task)

        try:
            asyncio.run_coroutine_threadsafe(_put(), loop)
            with self._metrics_lock:
                self._enqueued_total += 1
            logger.info(f"[brain] task_enqueued task_id={task_id} user_key={user_key}")
            return task_id
        except Exception as e:
            logger.error(f"[brain] enqueue_failed task_id={task_id} error={e}")
            return ""

    def get_latest_result_for_user(self, user_key: str) -> Optional[BrainResult]:
        with self._cache_lock:
            res = self._latest_by_user.get(user_key)
            if not res:
                return None
            if datetime.now() - res.created_at > self.cache_expire_time:
                return None
            return res

    def get_cached_result(self, task_id: str) -> Optional[BrainResult]:
        with self._cache_lock:
            res = self._result_by_task.get(task_id)
            if not res:
                return None
            if datetime.now() - res.created_at > self.cache_expire_time:
                return None
            return res

    def get_status(self) -> Dict[str, Any]:
        qsize = 0
        try:
            if self._queue is not None:
                qsize = int(self._queue.qsize())
        except Exception:
            qsize = 0
        with self._metrics_lock:
            enq = self._enqueued_total
            proc = self._processed_total
        with self._cache_lock:
            cached = len(self._result_by_task)
            users = len(self._latest_by_user)
        return {
            "running": bool(self._running.is_set()),
            "queue_size": qsize,
            "enqueued_total": enq,
            "processed_total": proc,
            "cached_results": cached,
            "cached_users": users,
            "max_concurrent": self.max_concurrent_tasks,
        }

    async def _worker_loop(self) -> None:
        sem = asyncio.Semaphore(self.max_concurrent_tasks)
        assert self._queue is not None

        while self._running.is_set():
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[brain] dequeue_failed error={e}")
                await asyncio.sleep(0.25)
                continue

            async def _run_one(t: BrainTask) -> None:
                async with sem:
                    await self._process_task(t)

            asyncio.create_task(_run_one(task))

    async def _process_task(self, task: BrainTask) -> None:
        start = time.time()
        try:
            with self._process_fn_lock:
                process_fn = self._process_fn
            if process_fn is None:
                from sisi_brain.real_brain_system import process_with_real_brain as _default_process_fn

                process_fn = _default_process_fn

            brain_result = await process_fn(task.user_input, task.audio_path, task.user_key)
            processing_time = time.time() - start
            result = BrainResult(
                task_id=task.task_id,
                user_key=task.user_key,
                success=True,
                environment_analysis=brain_result.get("environment_analysis", {}) if isinstance(brain_result, dict) else {},
                memory_context=(brain_result.get("memory_context", "") if isinstance(brain_result, dict) else "") or "",
                dynamic_prompt=(brain_result.get("dynamic_prompt", "") if isinstance(brain_result, dict) else "") or "",
                processing_time=processing_time,
                created_at=datetime.now(),
            )

            sink = self._memory_sink_fn
            if sink is not None:
                try:
                    sink(task, result)
                except Exception:
                    logger.debug("[brain] memory_sink_failed", exc_info=True)
            self._cache_result(result)
            logger.info(f"[brain] task_done task_id={task.task_id} user_key={task.user_key} t={processing_time:.2f}s ok=1")
        except Exception as e:
            processing_time = time.time() - start
            result = BrainResult(
                task_id=task.task_id,
                user_key=task.user_key,
                success=False,
                environment_analysis={},
                memory_context="",
                dynamic_prompt="",
                processing_time=processing_time,
                created_at=datetime.now(),
            )
            self._cache_result(result)
            logger.error(f"[brain] task_done task_id={task.task_id} user_key={task.user_key} t={processing_time:.2f}s ok=0 error={e}")
        finally:
            with self._metrics_lock:
                self._processed_total += 1

    def _cache_result(self, result: BrainResult) -> None:
        with self._cache_lock:
            self._cleanup_expired_locked()
            self._result_by_task[result.task_id] = result
            self._latest_by_user[result.user_key] = result
            if len(self._result_by_task) > self.max_cache_size:
                # best-effort trim: remove oldest entries
                items = sorted(self._result_by_task.items(), key=lambda kv: kv[1].created_at)
                for k, _ in items[: max(0, len(items) - self.max_cache_size)]:
                    self._result_by_task.pop(k, None)

    def _cleanup_expired_locked(self) -> None:
        now = datetime.now()
        expired = [k for k, v in self._result_by_task.items() if now - v.created_at > self.cache_expire_time]
        for k in expired:
            self._result_by_task.pop(k, None)
        expired_users = [uk for uk, v in self._latest_by_user.items() if now - v.created_at > self.cache_expire_time]
        for uk in expired_users:
            self._latest_by_user.pop(uk, None)


_brain_processor: Optional[BrainAsyncProcessor] = None


def _default_memory_sink(task: BrainTask, result: BrainResult) -> None:
    if not result.memory_context:
        return
    persona = "sisi"
    canonical_user_id = "default_user"
    if isinstance(task.user_key, str) and "::" in task.user_key:
        persona, canonical_user_id = task.user_key.split("::", 1)
    from sisi_memory.sisi_mem0 import get_sisi_memory_system

    mem = get_sisi_memory_system()
    mem.add_sisi_memory(
        text=result.memory_context[:1200],
        speaker_id=f"shared::{canonical_user_id}",
        response="",
        speaker_info={"mode": persona, "role_type": "assistant"},
    )


def get_brain_processor(*, process_fn: Optional[BrainProcessFn] = None, memory_sink_fn: Optional[BrainMemorySinkFn] = None) -> BrainAsyncProcessor:
    global _brain_processor
    if _brain_processor is None:
        _brain_processor = BrainAsyncProcessor(process_fn=process_fn, memory_sink_fn=memory_sink_fn or _default_memory_sink)
    else:
        if process_fn is not None:
            _brain_processor.set_process_fn(process_fn)
        if memory_sink_fn is not None:
            _brain_processor.set_memory_sink_fn(memory_sink_fn)
    return _brain_processor


def ensure_brain_processor_started(*, process_fn: Optional[BrainProcessFn] = None, memory_sink_fn: Optional[BrainMemorySinkFn] = None) -> None:
    get_brain_processor(process_fn=process_fn, memory_sink_fn=memory_sink_fn).ensure_started()


def submit_brain_task_fire_and_forget(audio_path: str, user_input: str, user_key: str) -> str:
    return get_brain_processor().submit_task_fire_and_forget(audio_path=audio_path, user_input=user_input, user_key=user_key)


def get_latest_brain_result(user_key: str) -> Optional[BrainResult]:
    return get_brain_processor().get_latest_result_for_user(user_key=user_key)
