"""Test basic communication primitives: send/receive, lock, counter, wake."""

import asyncio

import pytest

from tracefix.runtime.enforcement.store import MessageStore, LockStore, CounterStore
from tracefix.runtime.enforcement.engine import Runtime, AgentRunner, run_ir


# ---------------------------------------------------------------------------
# MessageStore 单元测试
# ---------------------------------------------------------------------------

class TestMessageStore:
    def test_send_and_peek(self):
        store = MessageStore()
        store.init_channel("ch")
        assert not store.peek("ch", "hello")
        store.send("ch", "hello", "agentA")
        assert store.peek("ch", "hello")

    def test_send_and_consume(self):
        store = MessageStore()
        store.init_channel("ch")
        store.send("ch", "hello", "agentA")
        msg = store.try_consume("ch", "hello")
        assert msg is not None
        assert msg.label == "hello"
        assert msg.sender == "agentA"
        # 消费后就没了
        assert store.try_consume("ch", "hello") is None

    def test_selective_receive(self):
        """多个 label 在同一 channel，只消费匹配的。"""
        store = MessageStore()
        store.init_channel("ch")
        store.send("ch", "apple", "a")
        store.send("ch", "banana", "a")
        store.send("ch", "apple", "a")
        # 只消费第一个 apple
        msg = store.try_consume("ch", "apple")
        assert msg is not None
        assert msg.id == 0
        # banana 还在
        assert store.peek("ch", "banana")
        # 第二个 apple 也还在
        msg2 = store.try_consume("ch", "apple")
        assert msg2 is not None
        assert msg2.id == 2

    def test_consume_wrong_label(self):
        store = MessageStore()
        store.init_channel("ch")
        store.send("ch", "hello", "a")
        assert store.try_consume("ch", "goodbye") is None
        # 原消息还在
        assert store.peek("ch", "hello")

    def test_fifo_order(self):
        store = MessageStore()
        store.init_channel("ch")
        store.send("ch", "msg", "a")
        store.send("ch", "msg", "b")
        store.send("ch", "msg", "c")
        m1 = store.try_consume("ch", "msg")
        m2 = store.try_consume("ch", "msg")
        m3 = store.try_consume("ch", "msg")
        assert m1.sender == "a"
        assert m2.sender == "b"
        assert m3.sender == "c"


# ---------------------------------------------------------------------------
# LockStore 单元测试
# ---------------------------------------------------------------------------

class TestLockStore:
    def test_acquire_and_release(self):
        store = LockStore()
        store.init_lock("L")
        assert store.is_free("L")
        assert store.try_acquire("L", "agentA")
        assert not store.is_free("L")
        # 第二次 acquire 失败
        assert not store.try_acquire("L", "agentB")
        store.release("L")
        assert store.is_free("L")
        # 现在 B 可以 acquire
        assert store.try_acquire("L", "agentB")


# ---------------------------------------------------------------------------
# CounterStore 单元测试
# ---------------------------------------------------------------------------

class TestCounterStore:
    def test_decrement_and_increment(self):
        store = CounterStore()
        store.init_counter("C", 2)
        assert store.value("C") == 2
        assert store.try_decrement("C")
        assert store.value("C") == 1
        assert store.try_decrement("C")
        assert store.value("C") == 0
        # 不能再减了
        assert not store.try_decrement("C")
        store.increment("C")
        assert store.value("C") == 1
        assert store.try_decrement("C")


# ---------------------------------------------------------------------------
# 两个 Agent 通信：A 发消息给 B，B 收到后回复
# ---------------------------------------------------------------------------

class TestTwoAgentCommunication:
    def test_ping_pong(self):
        """A sends ping → B receives → B sends pong → A receives."""
        ir = {
            "agents": [
                {"id": "A", "initial_state": "a_send"},
                {"id": "B", "initial_state": "b_wait"},
            ],
            "resources": [],
            "channels": [
                {"id": "ch_ab", "from": "A", "to": "B"},
                {"id": "ch_ba", "from": "B", "to": "A"},
            ],
            "states": [
                # A: send ping, then wait for pong
                {"id": "a_send", "agent": "A", "actions": [
                    {"target": "a_wait", "send": [{"channel": "ch_ab", "label": "ping"}]}
                ]},
                {"id": "a_wait", "agent": "A", "actions": [
                    {"target": "a_done", "receive": [{"channel": "ch_ba", "label": "pong"}]}
                ]},
                {"id": "a_done", "agent": "A", "actions": []},
                # B: wait for ping, then send pong
                {"id": "b_wait", "agent": "B", "actions": [
                    {"target": "b_reply", "receive": [{"channel": "ch_ab", "label": "ping"}]}
                ]},
                {"id": "b_reply", "agent": "B", "actions": [
                    {"target": "b_done", "send": [{"channel": "ch_ba", "label": "pong"}]}
                ]},
                {"id": "b_done", "agent": "B", "actions": []},
            ],
        }
        result = run_ir(ir, seed=1, timeout=5)
        assert result.success
        assert result.final_states == {"A": "a_done", "B": "b_done"}
        # 验证 trace: A send → B recv → B send → A recv
        agents_actions = [(e.agent, e.from_state, e.to_state) for e in result.trace]
        assert agents_actions == [
            ("A", "a_send", "a_wait"),
            ("B", "b_wait", "b_reply"),
            ("B", "b_reply", "b_done"),
            ("A", "a_wait", "a_done"),
        ]

    def test_multi_round_chat(self):
        """A 和 B 来回聊 3 轮。"""
        ir = {
            "agents": [
                {"id": "A", "initial_state": "a1"},
                {"id": "B", "initial_state": "b1"},
            ],
            "resources": [],
            "channels": [
                {"id": "ab", "from": "A", "to": "B"},
                {"id": "ba", "from": "B", "to": "A"},
            ],
            "states": [
                # Round 1: A→B
                {"id": "a1", "agent": "A", "actions": [
                    {"target": "a2", "send": [{"channel": "ab", "label": "msg1"}]}
                ]},
                {"id": "b1", "agent": "B", "actions": [
                    {"target": "b2", "receive": [{"channel": "ab", "label": "msg1"}]}
                ]},
                # Round 2: B→A
                {"id": "b2", "agent": "B", "actions": [
                    {"target": "b3", "send": [{"channel": "ba", "label": "msg2"}]}
                ]},
                {"id": "a2", "agent": "A", "actions": [
                    {"target": "a3", "receive": [{"channel": "ba", "label": "msg2"}]}
                ]},
                # Round 3: A→B
                {"id": "a3", "agent": "A", "actions": [
                    {"target": "a_done", "send": [{"channel": "ab", "label": "msg3"}]}
                ]},
                {"id": "b3", "agent": "B", "actions": [
                    {"target": "b_done", "receive": [{"channel": "ab", "label": "msg3"}]}
                ]},
                {"id": "a_done", "agent": "A", "actions": []},
                {"id": "b_done", "agent": "B", "actions": []},
            ],
        }
        result = run_ir(ir, seed=1, timeout=5)
        assert result.success
        assert result.steps == 6
        assert result.final_states == {"A": "a_done", "B": "b_done"}

    def test_broadcast_one_to_many(self):
        """A 广播消息给 B 和 C。"""
        ir = {
            "agents": [
                {"id": "A", "initial_state": "a1"},
                {"id": "B", "initial_state": "b1"},
                {"id": "C", "initial_state": "c1"},
            ],
            "resources": [],
            "channels": [
                {"id": "ch_ab", "from": "A", "to": "B"},
                {"id": "ch_ac", "from": "A", "to": "C"},
            ],
            "states": [
                {"id": "a1", "agent": "A", "actions": [
                    {"target": "a_done",
                     "send": [{"channel": "ch_ab", "label": "go"},
                              {"channel": "ch_ac", "label": "go"}]}
                ]},
                {"id": "a_done", "agent": "A", "actions": []},
                {"id": "b1", "agent": "B", "actions": [
                    {"target": "b_done", "receive": [{"channel": "ch_ab", "label": "go"}]}
                ]},
                {"id": "b_done", "agent": "B", "actions": []},
                {"id": "c1", "agent": "C", "actions": [
                    {"target": "c_done", "receive": [{"channel": "ch_ac", "label": "go"}]}
                ]},
                {"id": "c_done", "agent": "C", "actions": []},
            ],
        }
        result = run_ir(ir, seed=1, timeout=5)
        assert result.success
        assert result.final_states == {"A": "a_done", "B": "b_done", "C": "c_done"}

    def test_lock_mutual_exclusion(self):
        """A 和 B 竞争一把锁，验证互斥：不会同时持有。"""
        ir = {
            "agents": [
                {"id": "A", "initial_state": "a1"},
                {"id": "B", "initial_state": "b1"},
            ],
            "resources": [{"id": "mu", "type": "Lock"}],
            "channels": [],
            "states": [
                {"id": "a1", "agent": "A", "actions": [
                    {"target": "a_critical", "acquire": ["mu"]}
                ]},
                {"id": "a_critical", "agent": "A", "actions": [
                    {"target": "a_done", "release": ["mu"]}
                ]},
                {"id": "a_done", "agent": "A", "actions": []},
                {"id": "b1", "agent": "B", "actions": [
                    {"target": "b_critical", "acquire": ["mu"]}
                ]},
                {"id": "b_critical", "agent": "B", "actions": [
                    {"target": "b_done", "release": ["mu"]}
                ]},
                {"id": "b_done", "agent": "B", "actions": []},
            ],
        }
        result = run_ir(ir, seed=1, timeout=5)
        assert result.success
        # 验证互斥：acquire 和 release 交替出现，不会两个 acquire 连续
        lock_events = []
        for e in result.trace:
            for g in e.guards:
                if "acquire(mu)" in g:
                    lock_events.append(("acquire", e.agent))
            for ef in e.effects:
                if "release(mu)" in ef:
                    lock_events.append(("release", e.agent))
        # 应该是: acquire(X) → release(X) → acquire(Y) → release(Y)
        assert len(lock_events) == 4
        assert lock_events[0][0] == "acquire"
        assert lock_events[1] == ("release", lock_events[0][1])  # 同一个 agent 释放
        assert lock_events[2][0] == "acquire"
        assert lock_events[3] == ("release", lock_events[2][1])

    def test_wake_mechanism(self):
        """验证 wake 机制：B 在 A send 之前就开始等待，A send 后 B 被唤醒。"""
        ir = {
            "agents": [
                {"id": "A", "initial_state": "a_work"},
                {"id": "B", "initial_state": "b_wait"},
            ],
            "resources": [],
            "channels": [{"id": "ch", "from": "A", "to": "B"}],
            "states": [
                # A 先做两步"工作"，然后才 send
                {"id": "a_work", "agent": "A", "actions": [
                    {"target": "a_work2"}
                ]},
                {"id": "a_work2", "agent": "A", "actions": [
                    {"target": "a_done", "send": [{"channel": "ch", "label": "ready"}]}
                ]},
                {"id": "a_done", "agent": "A", "actions": []},
                # B 一开始就在等消息
                {"id": "b_wait", "agent": "B", "actions": [
                    {"target": "b_done", "receive": [{"channel": "ch", "label": "ready"}]}
                ]},
                {"id": "b_done", "agent": "B", "actions": []},
            ],
        }
        result = run_ir(ir, seed=1, timeout=5)
        assert result.success
        # B 的 recv 一定在 A 的 send 之后
        send_step = next(e.step for e in result.trace if "send(ch,ready)" in e.effects)
        recv_step = next(e.step for e in result.trace if "recv(ch,ready)" in e.guards)
        assert recv_step > send_step
