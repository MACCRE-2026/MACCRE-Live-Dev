import abc
import json
import logging
from typing import Any
from maccre_core.utils.path_resolver import get_maccre_root

_log = logging.getLogger(__name__)

class MessageQueue(abc.ABC):
    """Abstract interface for the Live Session Message Bus."""
    
    @abc.abstractmethod
    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        pass
        
    @abc.abstractmethod
    def poll(self, topics: list[str]) -> list[tuple[str, dict[str, Any]]]:
        """Returns a list of (topic, payload) since the last poll."""
        pass


class JsonFileQueue(MessageQueue):
    """
    A file-based append-only JSONL queue.
    Replaces ZMQ for inter-process Swarm telemetry and routing.
    """
    def __init__(self, queue_name: str = "live_session_bus", clear: bool = False) -> None:
        self.queue_dir = get_maccre_root() / "__DATACENTER" / "00_Message_Bus"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.queue_dir / f"{queue_name}.jsonl"
        self.cursor = 0
        
        # Ensure file exists without truncating, unless explicitly told to clear
        if clear or not self.filepath.exists():
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write("")
            
    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        message = {"topic": topic, "payload": payload}
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(message) + "\n")
        except Exception as e:
            _log.error(f"[JsonFileQueue] Failed to publish message: {e}")

    def poll(self, topics: list[str]) -> list[tuple[str, dict[str, Any]]]:
        results = []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                # Seek to the last read position
                f.seek(self.cursor)
                
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        msg_topic = msg.get("topic", "")
                        
                        # Match topics (support exact match or wildcard prefixes)
                        matched = False
                        for t in topics:
                            if t.endswith("*") and msg_topic.startswith(t[:-1]):
                                matched = True
                                break
                            elif t == msg_topic:
                                matched = True
                                break
                                
                        if matched:
                            results.append((msg_topic, msg.get("payload", {})))
                    except json.JSONDecodeError:
                        continue
                        
                self.cursor = f.tell()
        except FileNotFoundError:
            pass
        except Exception as e:
            _log.error(f"[JsonFileQueue] Polling error: {e}")
            
        return results
