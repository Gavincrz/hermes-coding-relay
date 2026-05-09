import unittest

from agent_spawner import StreamEvent
from event_adapter import RelayEvent, adapt_stream_event, adapt_stream_events


class EventAdapterTests(unittest.TestCase):
    def test_adapt_stream_event_maps_thread_started(self):
        events = adapt_stream_event(
            StreamEvent(kind="raw_event", payload={"type": "thread.started", "thread_id": "thread-123"})
        )

        self.assertEqual(events, [RelayEvent(kind="session_init", payload={"codex_thread_id": "thread-123"})])

    def test_adapt_stream_event_maps_agent_message(self):
        events = adapt_stream_event(
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.completed",
                    "item": {"id": "item_1", "type": "agent_message", "text": "done"},
                },
            )
        )

        self.assertEqual(events, [RelayEvent(kind="agent_text", payload={"item_id": "item_1", "text": "done"})])

    def test_adapt_stream_event_maps_command_started(self):
        events = adapt_stream_event(
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.started",
                    "item": {
                        "id": "item_2",
                        "type": "command_execution",
                        "command": "pytest -q",
                        "aggregated_output": "",
                        "status": "in_progress",
                        "exit_code": None,
                    },
                },
            )
        )

        self.assertEqual(
            events,
            [
                RelayEvent(
                    kind="command_started",
                    payload={
                        "item_id": "item_2",
                        "command": "pytest -q",
                        "output": "",
                        "exit_code": None,
                        "status": "in_progress",
                    },
                )
            ],
        )

    def test_adapt_stream_event_maps_command_finished(self):
        events = adapt_stream_event(
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.completed",
                    "item": {
                        "id": "item_3",
                        "type": "command_execution",
                        "command": "pytest -q",
                        "aggregated_output": "1 passed\n",
                        "status": "completed",
                        "exit_code": 0,
                    },
                },
            )
        )

        self.assertEqual(
            events,
            [
                RelayEvent(
                    kind="command_finished",
                    payload={
                        "item_id": "item_3",
                        "command": "pytest -q",
                        "output": "1 passed\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                )
            ],
        )

    def test_adapt_stream_event_maps_file_change(self):
        events = adapt_stream_event(
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.completed",
                    "item": {
                        "id": "item_4",
                        "type": "file_change",
                        "status": "completed",
                        "path": "src/app.py",
                        "changes": [{"path": "src/app.py", "kind": "modified"}],
                    },
                },
            )
        )

        self.assertEqual(
            events,
            [
                RelayEvent(
                    kind="file_change",
                    payload={
                        "item_id": "item_4",
                        "phase": "completed",
                        "status": "completed",
                        "path": "src/app.py",
                        "changes": [{"path": "src/app.py", "kind": "modified"}],
                    },
                )
            ],
        )

    def test_adapt_stream_event_maps_top_level_error(self):
        events = adapt_stream_event(
            StreamEvent(kind="raw_event", payload={"type": "error", "message": "Reconnecting..."})
        )

        self.assertEqual(
            events,
            [RelayEvent(kind="relay_error", payload={"reason": "codex_error", "message": "Reconnecting..."})],
        )

    def test_adapt_stream_event_passthrough_transport_error(self):
        events = adapt_stream_event(
            StreamEvent(kind="relay_error", payload={"reason": "process_exit", "message": "failed"})
        )

        self.assertEqual(
            events,
            [RelayEvent(kind="relay_error", payload={"reason": "process_exit", "message": "failed"})],
        )

    def test_adapt_stream_event_maps_turn_completed(self):
        events = adapt_stream_event(
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "turn.completed",
                    "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5},
                },
            )
        )

        self.assertEqual(
            events,
            [
                RelayEvent(
                    kind="turn_completed",
                    payload={"usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5}},
                )
            ],
        )

    def test_adapt_stream_event_ignores_unknown_event(self):
        events = adapt_stream_event(StreamEvent(kind="raw_event", payload={"type": "turn.started"}))

        self.assertEqual(events, [])

    def test_adapt_stream_events_normalizes_sequence(self):
        events = list(
            adapt_stream_events(
                [
                    StreamEvent(kind="raw_event", payload={"type": "thread.started", "thread_id": "thread-123"}),
                    StreamEvent(
                        kind="raw_event",
                        payload={
                            "type": "item.completed",
                            "item": {"id": "item_1", "type": "agent_message", "text": "done"},
                        },
                    ),
                ]
            )
        )

        self.assertEqual(
            events,
            [
                RelayEvent(kind="session_init", payload={"codex_thread_id": "thread-123"}),
                RelayEvent(kind="agent_text", payload={"item_id": "item_1", "text": "done"}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
