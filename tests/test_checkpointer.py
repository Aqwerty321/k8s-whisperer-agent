from backend.app.agent.checkpointer import PersistentInMemorySaver


def test_persistent_in_memory_saver_round_trips_storage(tmp_path) -> None:
    path = tmp_path / "checkpoints.pkl"
    saver = PersistentInMemorySaver(str(path))

    checkpoint = {
        "id": "checkpoint-1",
        "ts": "2026-01-01T00:00:00Z",
        "channel_values": {"foo": {"bar": 1}},
        "channel_versions": {"foo": "00000000000000000000000000000001.0000000000000000"},
        "versions_seen": {},
        "pending_sends": [],
    }
    config = {"configurable": {"thread_id": "incident-1", "checkpoint_ns": ""}}

    saved_config = saver.put(config, checkpoint, {"source": "test"}, checkpoint["channel_versions"])
    saver.put_writes(saved_config, [("foo", {"bar": 1})], task_id="task-1")

    reloaded = PersistentInMemorySaver(str(path))
    restored = reloaded.get_tuple({"configurable": {"thread_id": "incident-1"}})

    assert restored is not None
    assert restored.checkpoint["channel_values"]["foo"] == {"bar": 1}
    assert restored.metadata["source"] == "test"
