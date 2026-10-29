"""验证通知顺序、监听器隔离和订阅生命周期。"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from aurora_core.events import EventBus
from aurora_core.ids import Id

CHANGED = Id("dev.example:events/changed")
OTHER = Id("dev.example:events/other")


def test_filters_and_independent_payloads():
    bus = EventBus()
    received = []
    bus.subscribe(lambda event: event.payload.append("修改"), event_type=CHANGED)
    bus.subscribe(received.append, event_type=CHANGED)
    source = ["原始"]
    bus.publish(OTHER, source)
    bus.publish(CHANGED, source)
    assert source == ["原始"]
    assert received[0].payload == source
    assert received[0].sequence == 2


def test_reentrant_publication_keeps_fifo_order():
    bus = EventBus()
    received = []

    def first(event):
        if event.payload == 1:
            bus.publish(CHANGED, 2)

    bus.subscribe(first)
    bus.subscribe(lambda event: received.append(event.payload))
    bus.publish(CHANGED, 1)
    assert received == [1, 2]


def test_unsubscribe_skips_pending_callbacks_and_does_not_cross_buses():
    bus = EventBus()
    received = []
    bus.subscribe(lambda event: bus.unsubscribe(handle))
    handle = bus.subscribe(received.append)
    assert EventBus().unsubscribe(handle) is False
    bus.publish(CHANGED, None)
    assert received == []
    assert bus.unsubscribe(handle) is False


def test_listener_failure_does_not_stop_delivery(caplog):
    bus = EventBus()
    received = []

    def fail(event):
        raise ValueError("监听失败")

    bus.subscribe(fail)
    bus.subscribe(received.append)
    bus.publish(CHANGED, None)
    assert len(received) == 1
    assert "监听失败" in caplog.text


def test_subscribe_during_dispatch_only_receives_future_events():
    bus = EventBus()
    received = []
    bus.subscribe(lambda event: bus.subscribe(received.append))
    bus.publish(CHANGED, 1)
    assert received == []
    bus.publish(CHANGED, 2)
    assert [event.payload for event in received] == [2]


def test_close_releases_pending_callbacks():
    bus = EventBus()
    received = []
    bus.subscribe(lambda event: bus.close())
    handle = bus.subscribe(received.append)
    bus.publish(CHANGED, None)
    assert received == []
    assert bus.unsubscribe(handle) is False
    bus.close()
    with pytest.raises(RuntimeError, match="关闭"):
        bus.publish(CHANGED, None)
    with pytest.raises(RuntimeError, match="关闭"):
        bus.subscribe(received.append)


def test_async_callbacks_are_rejected():
    bus = EventBus()

    async def callback(event):
        pass

    with pytest.raises(TypeError, match="同步"):
        bus.subscribe(callback)


def test_cross_thread_access_is_explicitly_rejected():
    bus = EventBus()
    with ThreadPoolExecutor(max_workers=1) as pool, pytest.raises(RuntimeError, match="宿主线程"):
        pool.submit(bus.publish, CHANGED, None).result()
