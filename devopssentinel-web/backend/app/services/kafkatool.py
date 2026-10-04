"""Opt-in Kafka topic listing over the wire protocol.

Kafka has no "list topics" REST API, and the engine's ``kafka_topics_report``
needs the ``kafka-topics.sh`` CLI plus an authenticated broker session. When the
operator enables ``DSWEB_ENABLE_KAFKA_TOPICS=1`` the adapter performs a single,
read-only Kafka **Metadata** request (API key 3, version 1 -- Kafka 3.9 removed
version 0) against a bootstrap address the operator supplies, and reports the
topic names, partition counts and the brokers the cluster advertises.

Guarantees:
  * disabled unless ``DSWEB_ENABLE_KAFKA_TOPICS=1``
  * one request, one response -- no consumer groups, no offsets, no writes
  * no credentials, no SASL and no TLS material is accepted or transmitted
  * bounded by a socket timeout and a topic cap
"""

from __future__ import annotations

import asyncio
import socket
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .runner import AuditRecord, audit

_METADATA_API_KEY = 3
# Kafka 3.9 dropped Metadata v0 (KIP-896); v1 is the oldest accepted version.
_METADATA_API_VERSION = 1
_MAX_TOPICS = 500


class KafkaError(RuntimeError):
    """Raised with a safe, user-facing message."""


@dataclass
class TopicInfo:
    name: str
    partitions: int = 0
    internal: bool = False


@dataclass
class TopicListing:
    bootstrap: str = ""
    brokers: list[str] = field(default_factory=list)
    topics: list[TopicInfo] = field(default_factory=list)
    truncated: bool = False
    duration_ms: int = 0


def validate_target(host: str, port: int) -> None:
    if not host or len(host) > 253 or host.startswith("-") or " " in host:
        raise KafkaError("invalid bootstrap host")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise KafkaError("invalid bootstrap port")


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def _take(self, count: int) -> bytes:
        end = self._pos + count
        if end > len(self._data):
            raise KafkaError("truncated broker response")
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def int16(self) -> int:
        return struct.unpack(">h", self._take(2))[0]

    def int32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def int8(self) -> int:
        return self._take(1)[0]

    def string(self) -> str:
        length = self.int16()
        if length < 0:
            return ""
        return self._take(length).decode("utf-8", "replace")


def _request(correlation_id: int) -> bytes:
    client_id = b"devopssentinel-web"
    body = struct.pack(">hhi", _METADATA_API_KEY, _METADATA_API_VERSION, correlation_id)
    body += struct.pack(">h", len(client_id)) + client_id
    body += struct.pack(">i", -1)  # -1 = every topic
    return struct.pack(">i", len(body)) + body


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise KafkaError("broker closed the connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _parse(payload: bytes) -> TopicListing:
    """Parse a Metadata v1 response.

    v1 adds a nullable ``rack`` per broker, a ``controller_id`` before the topic
    array and an ``is_internal`` flag per topic (compared with v0).
    """
    reader = _Reader(payload)
    reader.int32()  # correlation id
    listing = TopicListing()
    for _ in range(max(reader.int32(), 0)):
        node_id = reader.int32()
        host = reader.string()
        port = reader.int32()
        reader.string()  # rack (nullable)
        listing.brokers.append(f"{node_id}:{host}:{port}")
    reader.int32()  # controller id
    for _ in range(max(reader.int32(), 0)):
        error = reader.int16()
        name = reader.string()
        internal = reader.int8() != 0
        partitions = max(reader.int32(), 0)
        for _ in range(partitions):
            reader.int16()  # partition error code
            reader.int32()  # partition index
            reader.int32()  # leader id
            for _ in range(max(reader.int32(), 0)):  # replicas
                reader.int32()
            for _ in range(max(reader.int32(), 0)):  # in-sync replicas
                reader.int32()
        if error != 0:
            continue
        if len(listing.topics) >= _MAX_TOPICS:
            listing.truncated = True
            break
        listing.topics.append(
            TopicInfo(name=name, partitions=partitions, internal=internal or name.startswith("__"))
        )
    listing.topics.sort(key=lambda topic: topic.name)
    return listing


def _run_blocking(host: str, port: int, timeout: float) -> TopicListing:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_request(1))
            size = struct.unpack(">i", _recv_exact(sock, 4))[0]
            if size <= 0 or size > 32 * 1024 * 1024:
                raise KafkaError("unexpected response size from the broker")
            listing = _parse(_recv_exact(sock, size))
    except KafkaError:
        raise
    except (socket.timeout, TimeoutError) as exc:
        raise KafkaError(f"broker did not answer within {timeout:.0f}s") from exc
    except OSError as exc:
        raise KafkaError(f"cannot reach the broker: {exc}") from exc
    listing.bootstrap = f"{host}:{port}"
    listing.duration_ms = int((time.monotonic() - started) * 1000)
    return listing


def _audit(host: str, port: int, duration_ms: int, status: int, topics: int) -> None:
    audit.add(
        AuditRecord(
            timestamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            operation="kafka.topics",
            context=f"{host}:{port}",
            namespace="",
            duration_ms=duration_ms,
            exit_status=status,
            record_count=topics,
            source="KAFKA",
        )
    )


async def list_topics(host: str, port: int, timeout: float) -> TopicListing:
    validate_target(host, port)
    try:
        listing = await asyncio.wait_for(
            asyncio.to_thread(_run_blocking, host, port, timeout), timeout=timeout + 3
        )
    except asyncio.TimeoutError as exc:
        _audit(host, port, int(timeout * 1000), 124, 0)
        raise KafkaError(f"broker did not answer within {timeout:.0f}s") from exc
    _audit(host, port, listing.duration_ms, 0, len(listing.topics))
    return listing

