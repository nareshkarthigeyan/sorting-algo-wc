import threading
import time
import sorting_world_cup
import traceback
import sys

# Let's patch run_sorter in sorting_world_cup to print the traceback when an exception is caught!
original_run_sorter = sorting_world_cup.run_sorter

def patched_run_sorter(*args, **kwargs):
    try:
        return original_run_sorter(*args, **kwargs)
    except Exception as e:
        print(f"Patched run_sorter caught: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise

sorting_world_cup.run_sorter = patched_run_sorter

def debug_algo(algo_name, algo_fn):
    print(f"\n--- Debugging {algo_name} on size 10,000 ---")
    arr = list(range(10000, 0, -1)) # Reversed array of size 10,000
    st = sorting_world_cup.VisualState(algo_name)
    cancel = threading.Event()
    pause = threading.Event()
    paused_ns = sorting_world_cup.Accumulator()
    
    worker = threading.Thread(
        target=original_run_sorter, # We target the original so we can catch inside or see final state
        args=(algo_fn, arr, st, cancel, pause, paused_ns, 0.0)
    )
    worker.start()
    
    time.sleep(0.1) # Let it run for 100ms
    cancel.set()
    worker.join()
    
    with st.lock:
        print(f"Done: {st.done}")
        print(f"Sorted: {st.sorted}")
        print(f"Cancelled: {st.cancelled}")
        if st.done and not st.sorted and not st.cancelled:
            print("STATUS: FAILED (cancelled is False but done is True!)")
        elif st.done and st.cancelled:
            print("STATUS: TERMINATED")

algos = sorting_world_cup.get_algorithms()
stooge = next(a for a in algos if a['name'] == "Stooge Sort")
slow = next(a for a in algos if a['name'] == "Slow Sort")

debug_algo("Stooge Sort", stooge['sort'])
debug_algo("Slow Sort", slow['sort'])
