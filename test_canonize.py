import os
from maccre_core.memory.knowledge_store import get_knowledge_store

os.environ["MACCRE_ACTIVE_PROJECT"] = "MEMORY_TEST"
session_name = "job_20260609-182003-7gfp-resume"
sess_db_name = f"session_{session_name}_thought_pins.db"

sess_store = get_knowledge_store("MEMORY_TEST", db_name=sess_db_name)
all_pins = sess_store.get_all("swarm_memory")
print(f"File: {sess_db_name}")
print(f"Count from get_all: {len(all_pins)}")

# Let's also do a raw query just to be absolutely sure
rows = sess_store._conn.execute("SELECT COUNT(*) FROM pins WHERE collection='swarm_memory';").fetchone()
print(f"Count from raw query: {rows[0]}")
