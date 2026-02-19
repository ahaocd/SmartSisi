#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Liuye runtime probe for SmartSisi (online service check on localhost:5000 by default).

Usage examples:
  python tests/liuye_runtime_probe.py
  python tests/liuye_runtime_probe.py --base-url http://127.0.0.1:5000 --exercise-mutations
  python tests/liuye_runtime_probe.py --report-json runtime/liuye_probe_report.json
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ProbeResult:
    name: str
    ok: bool
    status: int
    latency_ms: int
    detail: str
    payload: Optional[Dict[str, Any]] = None


def _http_json(
    base_url: str,
    path: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    timeout_sec: float = 6.0,
) -> ProbeResult:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            latency_ms = int((time.perf_counter() - start) * 1000)
            text = raw.decode("utf-8", errors="ignore")
            payload = None
            try:
                payload = json.loads(text)
            except Exception:
                payload = {"raw": text[:500]}
            return ProbeResult(
                name=f"{method.upper()} {path}",
                ok=200 <= int(resp.status) < 300,
                status=int(resp.status),
                latency_ms=latency_ms,
                detail="ok",
                payload=payload,
            )
    except urllib.error.HTTPError as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        detail = ""
        payload = None
        try:
            text = e.read().decode("utf-8", errors="ignore")
            detail = text[:500]
            try:
                payload = json.loads(text)
            except Exception:
                payload = {"raw": detail}
        except Exception:
            detail = str(e)
        return ProbeResult(
            name=f"{method.upper()} {path}",
            ok=False,
            status=int(e.code or 0),
            latency_ms=latency_ms,
            detail=detail or str(e),
            payload=payload,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProbeResult(
            name=f"{method.upper()} {path}",
            ok=False,
            status=0,
            latency_ms=latency_ms,
            detail=str(e),
            payload=None,
        )


def _read_first_sse_event(
    base_url: str,
    path: str,
    timeout_sec: float = 8.0,
) -> ProbeResult:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    req = urllib.request.Request(
        url=url,
        method="GET",
        headers={
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        },
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                latency_ms = int((time.perf_counter() - start) * 1000)
                detail = data_text
                payload = None
                try:
                    payload = json.loads(data_text)
                except Exception:
                    payload = {"raw": data_text}
                return ProbeResult(
                    name=f"GET {path} (SSE first event)",
                    ok=True,
                    status=int(resp.status),
                    latency_ms=latency_ms,
                    detail=detail[:500],
                    payload=payload,
                )
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ProbeResult(
                name=f"GET {path} (SSE first event)",
                ok=False,
                status=int(resp.status),
                latency_ms=latency_ms,
                detail="stream opened but no data line received",
                payload=None,
            )
    except urllib.error.HTTPError as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProbeResult(
            name=f"GET {path} (SSE first event)",
            ok=False,
            status=int(e.code or 0),
            latency_ms=latency_ms,
            detail=str(e),
            payload=None,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProbeResult(
            name=f"GET {path} (SSE first event)",
            ok=False,
            status=0,
            latency_ms=latency_ms,
            detail=str(e),
            payload=None,
        )


def _probe_liuye_turn_flow(base_url: str, timeout_sec: float = 8.0) -> List[ProbeResult]:
    out: List[ProbeResult] = []
    session_id = f"probe_{int(time.time())}"

    # Create session
    create_ret = _http_json(
        base_url,
        "/api/v1/liuye/session",
        method="POST",
        body={"session_id": session_id, "user_id": "probe"},
        timeout_sec=timeout_sec,
    )
    out.append(create_ret)
    if not create_ret.ok:
        return out

    turn_ret = _http_json(
        base_url,
        f"/api/v1/liuye/session/{session_id}/turn",
        method="POST",
        body={"input": "你好，做个连通性探测"},
        timeout_sec=timeout_sec,
    )
    out.append(turn_ret)
    return out


def _probe_guild_mutation_flow(base_url: str, guild_id: str, timeout_sec: float = 8.0) -> List[ProbeResult]:
    out: List[ProbeResult] = []
    description = f"运行时探测任务 {int(time.time())}：验证提交-解散链路"
    create_task = _http_json(
        base_url,
        f"/api/v1/guilds/{guild_id}/quests",
        method="POST",
        body={"description": description},
        timeout_sec=timeout_sec,
    )
    out.append(create_task)

    dissolve = _http_json(
        base_url,
        f"/api/v1/guilds/{guild_id}/dissolve",
        method="POST",
        body={"reason": "runtime probe: verify interrupt/dissolve path"},
        timeout_sec=timeout_sec,
    )
    out.append(dissolve)
    return out


def run_probe(
    base_url: str,
    guild_id: str,
    timeout_sec: float,
    exercise_mutations: bool,
    skip_liuye_turn: bool,
) -> Tuple[List[ProbeResult], Dict[str, Any]]:
    results: List[ProbeResult] = []
    resolved_guild_id = guild_id

    # Base service
    results.append(_http_json(base_url, "/", method="GET", timeout_sec=timeout_sec))
    results.append(_http_json(base_url, "/api/v1/adventurers", method="GET", timeout_sec=timeout_sec))
    results.append(_http_json(base_url, "/api/v1/models", method="GET", timeout_sec=timeout_sec))
    guilds_ret = _http_json(base_url, "/api/v1/guilds", method="GET", timeout_sec=timeout_sec)
    results.append(guilds_ret)

    if str(guild_id).strip().lower() == "auto" and guilds_ret.ok:
        try:
            guilds = ((guilds_ret.payload or {}).get("data") or {}).get("guilds") or []
            if guilds and isinstance(guilds[0], dict):
                gid = str(guilds[0].get("id") or "").strip()
                if gid:
                    resolved_guild_id = gid
        except Exception:
            pass

    results.append(
        _http_json(
            base_url,
            f"/api/v1/guilds/{resolved_guild_id}/quests",
            method="GET",
            timeout_sec=timeout_sec,
        )
    )

    # Event path
    results.append(
        _read_first_sse_event(
            base_url,
            f"/api/v1/guilds/{resolved_guild_id}/events?type=guild",
            timeout_sec=max(timeout_sec, 8.0),
        )
    )

    # Liuye turn path
    if not skip_liuye_turn:
        results.extend(_probe_liuye_turn_flow(base_url, timeout_sec=timeout_sec))

    if exercise_mutations:
        results.extend(
            _probe_guild_mutation_flow(
                base_url,
                guild_id=resolved_guild_id,
                timeout_sec=timeout_sec,
            )
        )

    ok_count = sum(1 for r in results if r.ok)
    avg_latency = int(sum(r.latency_ms for r in results) / max(len(results), 1))
    summary = {
        "base_url": base_url,
        "guild_id": resolved_guild_id,
        "checked_at": int(time.time()),
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "avg_latency_ms": avg_latency,
    }
    return results, summary


def _print_report(results: List[ProbeResult], summary: Dict[str, Any]) -> None:
    print("=== Liuye Runtime Probe Report ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("")
    for item in results:
        mark = "OK" if item.ok else "FAIL"
        print(
            f"[{mark}] {item.name} | status={item.status} | latency={item.latency_ms}ms | detail={item.detail[:120]}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="SmartSisi Liuye runtime probe")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="runtime base URL")
    parser.add_argument("--guild-id", default="auto", help="guild id (default: auto detect)")
    parser.add_argument("--timeout-sec", type=float, default=12.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--exercise-mutations",
        action="store_true",
        help="create quest and dissolve guild to validate interrupt path",
    )
    parser.add_argument(
        "--skip-liuye-turn",
        action="store_true",
        help="skip /api/v1/liuye/session/<id>/turn probe (useful when external model is slow)",
    )
    parser.add_argument("--report-json", default="", help="optional output report json path")
    args = parser.parse_args()

    results, summary = run_probe(
        base_url=args.base_url,
        guild_id=args.guild_id,
        timeout_sec=args.timeout_sec,
        exercise_mutations=args.exercise_mutations,
        skip_liuye_turn=args.skip_liuye_turn,
    )

    _print_report(results, summary)

    if args.report_json:
        report = {
            "summary": summary,
            "results": [asdict(x) for x in results],
        }
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nreport saved: {args.report_json}")

    return 0 if summary.get("failed", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
