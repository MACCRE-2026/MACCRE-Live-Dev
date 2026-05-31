"""
b:\\MACCREv2\\scripts\\edge_feasibility_test.py

Benchmarks the Personal Cloud Edge endpoint (e.g. S25 running Gemma)
by firing consecutive requests to measure latency and schema parsing stability.

To configure the endpoint, set MACCRE_EDGE_URL.
Example:
    set MACCRE_EDGE_URL=http://192.168.1.100:8080/v1/chat/completions
    omni run scripts/edge_feasibility_test.py
"""
import time
import json
from maccre_core.maccre_router import AgentRouter
from maccre_core.utils.path_resolver import get_datacenter_path

def run_feasibility_test() -> None:
    print("🚀 Starting Edge Feasibility Test against the Personal Cloud (S25)")
    router = AgentRouter()
    
    # 10 Consecutive Intent Generations
    iterations = 10
    model = "edge-gemma-4b" # Generic edge model tag
    
    dummy_transcript = (
        "USER: I think we need to pivot the architecture to use a local edge device.\n"
        "AI_1: I agree, the latency for cloud round-trips is killing our swarm physics."
    )
    
    latencies = []
    successes = 0
    
    for i in range(iterations):
        print(f"\n[Iteration {i+1}/{iterations}] Sending payload...")
        start_t = time.monotonic()
        
        try:
            # We use AgentRouter.chat because it enforces the structured schema 
            # and tests both the LLM's adherence and the parsing latency.
            response = router.chat(
                agent_name="Edge_Benchmark",
                message=dummy_transcript,
                session_id="benchmark_session",
                model=model
            )
            elapsed_ms = (time.monotonic() - start_t) * 1000
            
            if "FATAL ERROR" in response:
                print(f"❌ Failed: {response}")
            else:
                successes += 1
                latencies.append(elapsed_ms)
                print(f"✅ Success in {elapsed_ms:.1f}ms")
                # print(f"Response: {response}")
                
        except Exception as e:
            elapsed_ms = (time.monotonic() - start_t) * 1000
            print(f"❌ Error in {elapsed_ms:.1f}ms: {e}")

    # Summary
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
    else:
        avg_latency = min_latency = max_latency = 0.0

    print("\n" + "="*40)
    print("📊 FEASIBILITY TEST RESULTS")
    print("="*40)
    print(f"Total Requests: {iterations}")
    print(f"Successful:     {successes} / {iterations}")
    print(f"Avg Latency:    {avg_latency:.1f}ms")
    print(f"Min Latency:    {min_latency:.1f}ms")
    print(f"Max Latency:    {max_latency:.1f}ms")
    print("="*40)
    
    # Log to Datacenter
    ledger_dir = get_datacenter_path("03_Agent_Ledgers", "edge_benchmarks")
    ledger_dir.mkdir(parents=True, exist_ok=True)
    report_file = ledger_dir / f"benchmark_{int(time.time())}.json"
    
    report_data = {
        "model": model,
        "iterations": iterations,
        "success_rate": successes / iterations if iterations else 0,
        "metrics_ms": {
            "avg": avg_latency,
            "min": min_latency,
            "max": max_latency,
            "raw": latencies
        }
    }
    
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
        
    print(f"💾 Report saved to: {report_file}")

if __name__ == "__main__":
    run_feasibility_test()
