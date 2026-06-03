import time
import math
import random
import threading
import sys
from types import SimpleNamespace
from terminal_ui import RESET, BOLD, CYAN, FG_MUTED, VIOLET, GREEN, GOLD

sys.setrecursionlimit(2000000)

# Constants
SAMPLE_COUNT = 32 # Sampled count for TUI graph

# Scenario naming
SCENARIO_NAMES = {
    0: "Sorted Array",
    1: "Unsorted Array - Randomized",
    2: "Unsorted Array - Reversed",
    3: "Unsorted Array - one number unsorted",
    4: "Unsorted Array - randomized duplicates",
    5: "Random with tiny range (0-31)",
    6: "Random with huge range (0-1B)",
    7: "Organ Pipe",
    8: "Sawtooth",
    9: "Half Reversed Half Sorted"
}

SCENARIO_DESCRIPTIONS = {
    0: "A trap round: already sorted input punishes bad pivot choices and rewards best-case detection.",
    1: "The classic benchmark: values shuffled into a clean random battlefield.",
    2: "Worst-case pressure for many simple sorts: every value starts in the opposite direction.",
    3: "Almost perfect order with one value displaced; adaptive algorithms get a real chance here.",
    4: "Many repeated values: partitioning, stability, and counting-style approaches can shine.",
    5: "Values restricted only between 0 and 31. Heavily favors counting/distribution/radix algorithms.",
    6: "Massive range of values up to 1,000,000,000. Tests pivot distributions and comparison limits.",
    7: "Increasing to the middle, then decreasing. Tests symmetric pattern handling.",
    8: "Repeating ascending sawtooth pattern. Tests block-oriented and run-based sorts.",
    9: "First half reversed, second half sorted. Tests merges and sub-sequence boundaries."
}

class CancelledException(Exception):
    """Exception thrown when a sorting algorithm is cancelled during a race."""
    pass

class SortContext:
    def __init__(self, cancel_flag, pause_flag, paused_ns_accum, mask=4095):
        self.cancel_flag = cancel_flag
        self.pause_flag = pause_flag
        self.paused_ns_accum = paused_ns_accum
        self.counter = 0
        self.mask = mask

    def check(self):
        self.counter += 1
        if (self.counter & 1023) == 0:
            if self.cancel_flag and self.cancel_flag.is_set():
                raise CancelledException()
        if (self.counter & self.mask) == 0:
            self.force_check()

    def force_check(self):
        if self.pause_flag and self.pause_flag.is_set():
            t0 = time.perf_counter_ns()
            while self.pause_flag.is_set():
                if self.cancel_flag and self.cancel_flag.is_set():
                    raise CancelledException()
                time.sleep(0.01)
            t1 = time.perf_counter_ns()
            if self.paused_ns_accum is not None:
                self.paused_ns_accum.value += (t1 - t0)

        if self.cancel_flag and self.cancel_flag.is_set():
            raise CancelledException()

class VisualArray:
    def __init__(self, arr, state, context, visual_delay=0.0, publish_mask=4095, scale_factor=1.0):
        self.arr = list(arr)
        self.st = state
        self.context = context
        self.visual_delay = visual_delay
        self.operations = 0
        self.reads = 0
        self.writes = 0
        self.publish_mask = publish_mask
        self.scale_factor = scale_factor
        self.publish(-1, -1)

    def size(self):
        return len(self.arr)

    def get(self, i):
        self.context.check()
        self.reads += 1
        self.operations += 1
        if (self.operations & self.publish_mask) == 0:
            self.publish(i, -1)
        if self.visual_delay > 0:
            time.sleep(self.visual_delay)
        return self.arr[i]

    def set(self, i, value):
        self.context.check()
        self.arr[i] = value
        self.writes += 1
        self.operations += 1
        if (self.operations & self.publish_mask) == 0:
            self.publish(i, -1)
        if self.visual_delay > 0:
            time.sleep(self.visual_delay)

    def swapAt(self, i, j):
        self.context.check()
        if i != j:
            self.arr[i], self.arr[j] = self.arr[j], self.arr[i]
        self.writes += 2
        self.operations += 1
        if (self.operations & self.publish_mask) == 0:
            self.publish(i, j)
        if self.visual_delay > 0:
            time.sleep(self.visual_delay)

    def data(self):
        self.context.force_check()
        # Track that we read the whole array
        self.reads += len(self.arr)
        self.operations += len(self.arr)
        return list(self.arr)

    def snapshot(self):
        return list(self.arr)

    def replaceAll(self, next_arr):
        self.context.force_check()
        self.arr = list(next_arr)
        self.writes += len(self.arr)
        self.publish(-1, -1)

    def sorted(self):
        for i in range(1, len(self.arr)):
            if self.arr[i-1] > self.arr[i]:
                return False
        return True

    def check(self):
        self.context.force_check()

    def publish(self, i, j):
        n = len(self.arr)
        sample = []
        if n > 0:
            for k in range(SAMPLE_COUNT):
                idx = min(n - 1, (k * (n - 1)) // max(1, SAMPLE_COUNT - 1))
                sample.append(self.arr[idx])
        
        ordered = 0
        for k in range(1, len(sample)):
            if sample[k-1] <= sample[k]:
                ordered += 1
        
        meter = 100.0 if len(sample) < 2 else (100.0 * ordered) / (len(sample) - 1)
        
        scaled_ops = int(self.operations * self.scale_factor)
        scaled_reads = int(self.reads * self.scale_factor)
        scaled_writes = int(self.writes * self.scale_factor)
        
        with self.st.lock:
            self.st.sample = sample
            self.st.hotA = i
            self.st.hotB = j
            self.st.operations = scaled_ops
            self.st.reads = scaled_reads
            self.st.writes = scaled_writes
            self.st.order_meter = meter

class VisualState:
    def __init__(self, name=""):
        self.lock = threading.Lock()
        self.name = name
        self.sample = []
        self.final_values = []
        self.hotA = -1
        self.hotB = -1
        self.done = False
        self.cancelled = False
        self.sorted = False
        self.ns = 0
        self.elapsed_ms = 0
        self.operations = 0
        self.reads = 0
        self.writes = 0
        self.order_meter = 0.0

class RaceResult:
    def __init__(self):
        self.winner_slot = 0
        self.tie = False
        self.nsA = 0
        self.nsB = 0
        self.opsA = 0
        self.opsB = 0
        self.sortedA = False
        self.sortedB = False
        self.cancelledA = False
        self.cancelledB = False

class MatchResult:
    def __init__(self):
        self.winner = -1
        self.loser = -1
        self.tie = False
        self.winsA = 0
        self.winsB = 0
        self.ties = 0
        self.nsA = 0
        self.nsB = 0

# --- Sorter Implementations ---

def intro_sort(v):
    n = v.size()
    max_depth = 2 * math.floor(math.log2(n)) if n > 0 else 0
    intro_sort_helper(v, 0, n - 1, max_depth)

def intro_sort_helper(v, lo, hi, depth_limit):
    v.check()
    if hi - lo <= 16:
        # Insertion sort for small ranges
        for i in range(lo + 1, hi + 1):
            key = v.get(i)
            j = i - 1
            while j >= lo and v.get(j) > key:
                v.set(j + 1, v.get(j))
                j -= 1
            v.set(j + 1, key)
        return
    if depth_limit == 0:
        # Fall back to heapsort
        intro_heapsort(v, lo, hi)
        return
    
    # Partition (using median-of-three pivot)
    mid = lo + (hi - lo) // 2
    if v.get(mid) < v.get(lo): v.swapAt(mid, lo)
    if v.get(hi) < v.get(lo): v.swapAt(hi, lo)
    if v.get(hi) < v.get(mid): v.swapAt(hi, mid)
    pivot = v.get(mid)
    
    i = lo
    j = hi
    while True:
        while v.get(i) < pivot:
            i += 1
        while v.get(j) > pivot:
            j -= 1
        if i >= j:
            p = j
            break
        v.swapAt(i, j)
        i += 1
        j -= 1
        
    intro_sort_helper(v, lo, p, depth_limit - 1)
    intro_sort_helper(v, p + 1, hi, depth_limit - 1)

def intro_heapsort(v, lo, hi):
    n = hi - lo + 1
    for i in range(n // 2 - 1, -1, -1):
        intro_heapify(v, n, i, lo)
    for i in range(n - 1, 0, -1):
        v.swapAt(lo, lo + i)
        intro_heapify(v, i, 0, lo)

def intro_heapify(v, n, i, lo):
    v.check()
    largest = i
    l = 2 * i + 1
    r = 2 * i + 2
    if l < n and v.get(lo + l) > v.get(lo + largest):
        largest = l
    if r < n and v.get(lo + r) > v.get(lo + largest):
        largest = r
    if largest != i:
        v.swapAt(lo + i, lo + largest)
        intro_heapify(v, n, largest, lo)

def get_minrun(n):
    r = 0
    while n >= 64:
        r |= (n & 1)
        n >>= 1
    return n + r

def tim_sort(v):
    n = v.size()
    if n < 2:
        return
    minrun = get_minrun(n)
    runs = []
    
    i = 0
    while i < n:
        v.check()
        start = i
        if i == n - 1:
            runs.append((start, 1))
            break
            
        i += 1
        if v.get(i) < v.get(i - 1): # Descending
            while i < n and v.get(i) < v.get(i - 1):
                i += 1
            # Reverse descending run
            l = start
            r = i - 1
            while l < r:
                v.swapAt(l, r)
                l += 1
                r -= 1
        else: # Ascending
            while i < n and v.get(i) >= v.get(i - 1):
                i += 1
                
        run_len = i - start
        if run_len < minrun and i < n:
            force_len = min(n - start, minrun)
            # Insertion sort
            for j in range(start + run_len, start + force_len):
                key = v.get(j)
                k = j - 1
                while k >= start and v.get(k) > key:
                    v.set(k + 1, v.get(k))
                    k -= 1
                v.set(k + 1, key)
            run_len = force_len
            i = start + force_len
            
        runs.append((start, run_len))
        
        while len(runs) >= 2:
            if len(runs) >= 3 and runs[-3][1] <= runs[-2][1] + runs[-1][1]:
                if runs[-3][1] < runs[-1][1]:
                    runs[-3] = merge_timsort_runs(v, runs[-3], runs[-2])
                    runs.pop(-2)
                else:
                    runs[-2] = merge_timsort_runs(v, runs[-2], runs[-1])
                    runs.pop(-1)
            elif runs[-2][1] <= runs[-1][1]:
                runs[-2] = merge_timsort_runs(v, runs[-2], runs[-1])
                runs.pop(-1)
            else:
                break
                
    while len(runs) >= 2:
        runs[-2] = merge_timsort_runs(v, runs[-2], runs[-1])
        runs.pop(-1)

def merge_timsort_runs(v, run1, run2):
    start1, len1 = run1
    start2, len2 = run2
    merge_range(v, start1, start1 + len1 - 1, start2 + len2 - 1)
    return (start1, len1 + len2)

def merge_range(v, l, m, r):
    left = [v.get(i) for i in range(l, m + 1)]
    right = [v.get(i) for i in range(m + 1, r + 1)]
    i = j = 0
    k = l
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            v.set(k, left[i])
            i += 1
        else:
            v.set(k, right[j])
            j += 1
        k += 1
    while i < len(left):
        v.set(k, left[i])
        i += 1
        k += 1
    while j < len(right):
        v.set(k, right[j])
        j += 1
        k += 1

def merge_sort(v):
    n = v.size()
    curr_size = 1
    while curr_size < n:
        left = 0
        while left < n - 1:
            mid = min(left + curr_size - 1, n - 1)
            right = min(left + 2 * curr_size - 1, n - 1)
            merge_range(v, left, mid, right)
            left += 2 * curr_size
        curr_size *= 2

def quick_sort(v):
    stack = [(0, v.size() - 1)]
    while stack:
        lo, hi = stack.pop()
        while hi - lo > 24:
            v.check()
            mid = lo + (hi - lo) // 2
            if v.get(mid) < v.get(lo): v.swapAt(mid, lo)
            if v.get(hi) < v.get(lo): v.swapAt(hi, lo)
            if v.get(hi) < v.get(mid): v.swapAt(hi, mid)
            pivot = v.get(mid)
            i, j = lo, hi
            while i <= j:
                while v.get(i) < pivot: i += 1
                while v.get(j) > pivot: j -= 1
                if i <= j:
                    v.swapAt(i, j)
                    i += 1
                    j -= 1
            if j - lo < hi - i:
                if i < hi: stack.append((i, hi))
                hi = j
            else:
                if lo < j: stack.append((lo, j))
                lo = i
        for i in range(lo + 1, hi + 1):
            key = v.get(i)
            j = i - 1
            while j >= lo and v.get(j) > key:
                v.set(j + 1, v.get(j))
                j -= 1
            v.set(j + 1, key)

def quick3_sort(v):
    stack = [(0, v.size() - 1)]
    while stack:
        lo, hi = stack.pop()
        if lo >= hi:
            continue
        if hi - lo <= 24:
            for i in range(lo + 1, hi + 1):
                key = v.get(i)
                j = i - 1
                while j >= lo and v.get(j) > key:
                    v.set(j + 1, v.get(j))
                    j -= 1
                v.set(j + 1, key)
            continue
        mid = lo + (hi - lo) // 2
        if v.get(mid) < v.get(lo): v.swapAt(mid, lo)
        if v.get(hi) < v.get(lo): v.swapAt(hi, lo)
        if v.get(hi) < v.get(mid): v.swapAt(hi, mid)
        pivot = v.get(mid)
        lt = lo
        i = lo
        gt = hi
        while i <= gt:
            v.check()
            while i <= gt and v.get(gt) > pivot:
                gt -= 1
            if i > gt:
                break
            x = v.get(i)
            if x < pivot:
                if lt != i:
                    v.swapAt(lt, i)
                lt += 1
                i += 1
            elif x > pivot:
                v.swapAt(i, gt)
                gt -= 1
            else:
                i += 1
        if lt - lo > hi - gt:
            if lo < lt - 1: stack.append((lo, lt - 1))
            if gt + 1 < hi: stack.append((gt + 1, hi))
        else:
            if gt + 1 < hi: stack.append((gt + 1, hi))
            if lo < lt - 1: stack.append((lo, lt - 1))


def heapify(v, n, i):
    v.check()
    largest = i
    l = 2 * i + 1
    r = 2 * i + 2
    if l < n and v.get(l) > v.get(largest):
        largest = l
    if r < n and v.get(r) > v.get(largest):
        largest = r
    if largest != i:
        v.swapAt(i, largest)
        heapify(v, n, largest)

def heap_sort(v):
    n = v.size()
    for i in range(n // 2 - 1, -1, -1):
        heapify(v, n, i)
    for i in range(n - 1, 0, -1):
        v.swapAt(0, i)
        heapify(v, i, 0)

def shell_sort(v):
    gaps = [701, 301, 132, 57, 23, 10, 4, 1]
    n = v.size()
    for gap in gaps:
        if gap >= n:
            continue
        for i in range(gap, n):
            temp = v.get(i)
            j = i
            while j >= gap and v.get(j - gap) > temp:
                v.set(j, v.get(j - gap))
                j -= gap
            v.set(j, temp)

def natural_merge_sort(v):
    n = v.size()
    if n < 2:
        return
    done = False
    while not done:
        done = True
        l = 0
        while l < n:
            m = l
            while m + 1 < n and v.get(m) <= v.get(m + 1):
                m += 1
            if m == n - 1:
                break
            r = m + 1
            while r + 1 < n and v.get(r) <= v.get(r + 1):
                r += 1
            merge_range(v, l, m, r)
            done = False
            l = r + 1

def counting_sort(v):
    n = v.size()
    if n == 0:
        return
    mn = mx = v.get(0)
    for i in range(1, n):
        val = v.get(i)
        mn = min(mn, val)
        mx = max(mx, val)
    count = [0] * (mx - mn + 1)
    for i in range(n):
        count[v.get(i) - mn] += 1
    k = 0
    for val in range(mn, mx + 1):
        while count[val - mn] > 0:
            v.set(k, val)
            count[val - mn] -= 1
            k += 1

def radix_sort(v):
    n = v.size()
    if n == 0:
        return
    mx = 0
    for i in range(n):
        mx = max(mx, v.get(i))
    exp = 1
    while mx // exp > 0:
        output = [0] * n
        count = [0] * 10
        for i in range(n):
            count[(v.get(i) // exp) % 10] += 1
        for i in range(1, 10):
            count[i] += count[i - 1]
        for i in range(n - 1, -1, -1):
            x = v.get(i)
            digit = (x // exp) % 10
            count[digit] -= 1
            output[count[digit]] = x
        for i in range(n):
            v.set(i, output[i])
        exp *= 10

def msd_radix_sort(v):
    n = v.size()
    if n < 2:
        return
    mx = v.get(0)
    for i in range(1, n):
        val = v.get(i)
        if val > mx:
            mx = val
    exp = 1
    while mx // (exp * 10) > 0:
        exp *= 10
    msd_radix_helper(v, 0, n - 1, exp)

def msd_radix_helper(v, lo, hi, exp):
    if lo >= hi or exp <= 0:
        return
    v.check()
    
    n = hi - lo + 1
    count = [0] * 11
    for i in range(lo, hi + 1):
        digit = (v.get(i) // exp) % 10
        count[digit + 1] += 1
        
    for i in range(1, 10):
        count[i] += count[i - 1]
        
    offsets = list(count)
    temp = [0] * n
    
    for i in range(lo, hi + 1):
        val = v.get(i)
        digit = (val // exp) % 10
        temp[offsets[digit]] = val
        offsets[digit] += 1
        
    for i in range(n):
        v.set(lo + i, temp[i])
        
    for i in range(10):
        start = lo + count[i]
        end = lo + count[i + 1] - 1
        if start < end:
            msd_radix_helper(v, start, end, exp // 10)

def bucket_sort(v):
    n = v.size()
    if n == 0:
        return
    mn = mx = v.get(0)
    for i in range(1, n):
        val = v.get(i)
        mn = min(mn, val)
        mx = max(mx, val)
    bucket_count = max(1, int(math.sqrt(n)))
    buckets = [[] for _ in range(bucket_count)]
    range_v = max(1, mx - mn + 1)
    for i in range(n):
        val = v.get(i)
        idx = min(bucket_count - 1, ((val - mn) * bucket_count) // range_v)
        buckets[idx].append(val)
    k = 0
    for b in buckets:
        # Custom insertion sort for the bucket
        for i in range(1, len(b)):
            key = b[i]
            j = i - 1
            while j >= 0 and b[j] > key:
                b[j + 1] = b[j]
                j -= 1
            b[j + 1] = key
        for x in b:
            v.set(k, x)
            k += 1

def pigeonhole_sort(v):
    n = v.size()
    if n < 2:
        return
    mn = mx = v.get(0)
    for i in range(1, n):
        val = v.get(i)
        mn = min(mn, val)
        mx = max(mx, val)
        
    size = mx - mn + 1
    holes = [[] for _ in range(size)]
    for i in range(n):
        val = v.get(i)
        holes[val - mn].append(val)
        
    k = 0
    for hole in holes:
        v.check()
        for val in hole:
            v.set(k, val)
            k += 1

class BSTNode:
    def __init__(self, val):
        self.val = val
        self.left = None
        self.right = None
        self.count = 1

def tree_sort(v):
    n = v.size()
    if n == 0:
        return
    root = BSTNode(v.get(0))
    for i in range(1, n):
        v.check()
        val = v.get(i)
        curr = root
        while True:
            if val == curr.val:
                curr.count += 1
                break
            elif val < curr.val:
                if curr.left is None:
                    curr.left = BSTNode(val)
                    break
                curr = curr.left
            else:
                if curr.right is None:
                    curr.right = BSTNode(val)
                    break
                curr = curr.right
    
    k = 0
    stack = []
    curr = root
    while stack or curr:
        v.check()
        while curr:
            stack.append(curr)
            curr = curr.left
        curr = stack.pop()
        for _ in range(curr.count):
            v.set(k, curr.val)
            k += 1
        curr = curr.right

def tournament_sort(v):
    a = v.data()
    out = []
    while a:
        v.check()
        min_i = 0
        for i in range(1, len(a)):
            if a[i] < a[min_i]:
                min_i = i
        out.append(a[min_i])
        a.pop(min_i)
        for i in range(len(out)):
            v.set(i, out[i])

def strand_sort(v):
    n = v.size()
    input_list = [v.get(i) for i in range(n)]
    output = []
    while input_list:
        v.check()
        strand = [input_list.pop(0)]
        i = 0
        while i < len(input_list):
            v.check()
            if input_list[i] >= strand[-1]:
                strand.append(input_list.pop(i))
            else:
                i += 1
        merged = []
        x = y = 0
        while x < len(output) and y < len(strand):
            if output[x] <= strand[y]:
                merged.append(output[x])
                x += 1
            else:
                merged.append(strand[y])
                y += 1
        merged.extend(output[x:])
        merged.extend(strand[y:])
        output = merged
        for idx in range(len(output)):
            v.set(idx, output[idx])


def bitonic_merge(v, low, count, up):
    v.check()
    if count <= 1:
        return
    k = count // 2
    for i in range(low, low + k):
        if (v.get(i) > v.get(i + k)) == up:
            v.swapAt(i, i + k)
    bitonic_merge(v, low, k, up)
    bitonic_merge(v, low + k, k, up)

def bitonic_sort_rec(v, low, count, up):
    v.check()
    if count <= 1:
        return
    k = count // 2
    bitonic_sort_rec(v, low, k, True)
    bitonic_sort_rec(v, low + k, k, False)
    bitonic_merge(v, low, count, up)

def bitonic_sort(v):
    n = v.size()
    power = 1
    while power < n:
        power <<= 1
    a = v.data()
    sentinel = 0 if not a else max(a) + 1
    while len(a) < power:
        a.append(sentinel)
        sentinel += 1
    dummy_state = SimpleNamespace(
        lock=threading.Lock(),
        sample=[], hotA=-1, hotB=-1, operations=0, reads=0, writes=0, order_meter=0
    )
    tmp = VisualArray(a, dummy_state, v.context, scale_factor=v.scale_factor)
    bitonic_sort_rec(tmp, 0, power, True)
    out = tmp.snapshot()
    for i in range(n):
        v.set(i, out[i])

def insertion_sort(v):
    n = v.size()
    for i in range(1, n):
        key = v.get(i)
        j = i - 1
        while j >= 0 and v.get(j) > key:
            v.set(j + 1, v.get(j))
            j -= 1
        v.set(j + 1, key)

def binary_insertion_sort(v):
    n = v.size()
    for i in range(1, n):
        key = v.get(i)
        left = 0
        right = i
        while left < right:
            mid = left + (right - left) // 2
            if key < v.get(mid):
                right = mid
            else:
                left = mid + 1
        for j in range(i, left, -1):
            v.set(j, v.get(j - 1))
        v.set(left, key)

def selection_sort(v):
    n = v.size()
    for i in range(n):
        min_i = i
        for j in range(i + 1, n):
            if v.get(j) < v.get(min_i):
                min_i = j
        v.swapAt(i, min_i)

def cycle_sort(v):
    n = v.size()
    for cycle_start in range(n - 1):
        item = v.get(cycle_start)
        pos = cycle_start
        for i in range(cycle_start + 1, n):
            if v.get(i) < item:
                pos += 1
        if pos == cycle_start:
            continue
        while pos < n and item == v.get(pos):
            pos += 1
        if pos >= n:
            continue
        temp = v.get(pos)
        v.set(pos, item)
        item = temp
        while pos != cycle_start:
            pos = cycle_start
            for i in range(cycle_start + 1, n):
                if v.get(i) < item:
                    pos += 1
            while pos < n and item == v.get(pos):
                pos += 1
            if pos >= n:
                break
            temp = v.get(pos)
            v.set(pos, item)
            item = temp

def pancake_sort(v):
    def flip(k):
        i = 0
        while i < k:
            v.swapAt(i, k)
            i += 1
            k -= 1
    for curr in range(v.size(), 1, -1):
        max_i = 0
        for i in range(1, curr):
            if v.get(i) > v.get(max_i):
                max_i = i
        if max_i == curr - 1:
            continue
        flip(max_i)
        flip(curr - 1)

def comb_sort(v):
    n = v.size()
    gap = n
    swapped = True
    while gap != 1 or swapped:
        gap = max(1, (gap * 10) // 13)
        swapped = False
        for i in range(n - gap):
            if v.get(i) > v.get(i + gap):
                v.swapAt(i, i + gap)
                swapped = True

def gnome_sort(v):
    i = 0
    n = v.size()
    while i < n:
        if i == 0 or v.get(i - 1) <= v.get(i):
            i += 1
        else:
            v.swapAt(i - 1, i)
            i -= 1

def bubble_sort(v):
    n = v.size()
    for i in range(n):
        changed = False
        for j in range(n - i - 1):
            if v.get(j) > v.get(j + 1):
                v.swapAt(j, j + 1)
                changed = True
        if not changed:
            return

def cocktail_sort(v):
    start = 0
    end = v.size() - 1
    swapped = True
    while swapped:
        swapped = False
        for i in range(start, end):
            if v.get(i) > v.get(i + 1):
                v.swapAt(i, i + 1)
                swapped = True
        if not swapped:
            break
        swapped = False
        end -= 1
        for i in range(end - 1, start - 1, -1):
            if v.get(i) > v.get(i + 1):
                v.swapAt(i, i + 1)
                swapped = True
        start += 1

def odd_even_sort(v):
    sorted_flag = False
    n = v.size()
    while not sorted_flag:
        sorted_flag = True
        for i in range(1, n - 1, 2):
            if v.get(i) > v.get(i + 1):
                v.swapAt(i, i + 1)
                sorted_flag = False
        for i in range(0, n - 1, 2):
            if v.get(i) > v.get(i + 1):
                v.swapAt(i, i + 1)
                sorted_flag = False

def smooth_sort(v):
    n = v.size()
    if n < 2:
        return
    lp = [1, 1, 3, 5, 9, 15, 25, 41, 67, 109, 177, 287, 465, 753, 1221, 1977, 3199, 5177, 8377, 13555, 21933, 35489, 57423, 92913, 150337, 243251, 393589, 636841, 1030431, 1667273, 2697705, 4364979]
    heap_sizes = []
    
    for i in range(n):
        v.check()
        if len(heap_sizes) >= 2 and heap_sizes[-2] == heap_sizes[-1] + 1:
            heap_sizes.pop()
            heap_sizes[-1] += 1
        else:
            if len(heap_sizes) >= 1 and heap_sizes[-1] == 1:
                heap_sizes.append(0)
            else:
                heap_sizes.append(1)
        smooth_sift_up(v, i, heap_sizes, lp)
        
    for i in range(n - 1, 0, -1):
        v.check()
        size = heap_sizes.pop()
        if size > 1:
            heap_sizes.append(size - 1)
            heap_sizes.append(size - 2)
            left_root = i - lp[size - 2] - 1
            right_root = i - 1
            smooth_sift_up(v, left_root, heap_sizes[:-1], lp)
            smooth_sift_up(v, right_root, heap_sizes, lp)

def smooth_sift_up(v, r, heap_sizes, lp):
    i = len(heap_sizes) - 1
    while i > 0:
        v.check()
        prev_r = r - lp[heap_sizes[i]]
        val_r = v.get(r)
        val_prev = v.get(prev_r)
        if val_prev <= val_r:
            break
        size = heap_sizes[i]
        if size >= 2:
            child1 = r - 1
            child2 = r - lp[size - 2] - 1
            if v.get(child1) >= val_prev or v.get(child2) >= val_prev:
                break
        v.swapAt(r, prev_r)
        r = prev_r
        i -= 1
    smooth_sift_down(v, r, heap_sizes[i], lp)

def smooth_sift_down(v, r, size, lp):
    while size >= 2:
        v.check()
        child1 = r - 1
        child2 = r - lp[size - 2] - 1
        val1 = v.get(child1)
        val2 = v.get(child2)
        val_r = v.get(r)
        if val_r >= val1 and val_r >= val2:
            break
        if val1 >= val2:
            v.swapAt(r, child1)
            r = child1
            size -= 1
        else:
            v.swapAt(r, child2)
            r = child2
            size -= 2

def patience_sort(v):
    n = v.size()
    if n < 2:
        return
    piles = []
    for i in range(n):
        val = v.get(i)
        lo = 0
        hi = len(piles)
        while lo < hi:
            mid = (lo + hi) // 2
            if piles[mid][-1] >= val:
                hi = mid
            else:
                lo = mid + 1
        if lo == len(piles):
            piles.append([val])
        else:
            piles[lo].append(val)
            
    for i in range(n):
        v.check()
        min_val = None
        min_p = -1
        for p in range(len(piles)):
            if piles[p]:
                top = piles[p][-1]
                if min_val is None or top < min_val:
                    min_val = top
                    min_p = p
        piles[min_p].pop()
        v.set(i, min_val)

def library_sort(v):
    n = v.size()
    if n < 2:
        return
    gapped_size = 2 * n
    gapped = [None] * gapped_size
    gapped[0] = v.get(0)
    inserted = 1
    target = 1
    
    for i in range(1, n):
        v.check()
        val = v.get(i)
        active_indices = [idx for idx in range(gapped_size) if gapped[idx] is not None]
        lo = 0
        hi = len(active_indices)
        while lo < hi:
            mid = (lo + hi) // 2
            if gapped[active_indices[mid]] > val:
                hi = mid
            else:
                lo = mid + 1
        if lo == len(active_indices):
            insert_idx = active_indices[-1] + 1 if active_indices else 0
        else:
            insert_idx = active_indices[lo]
            
        if insert_idx < gapped_size and gapped[insert_idx] is None:
            gapped[insert_idx] = val
        else:
            empty_idx = insert_idx
            while empty_idx < gapped_size and gapped[empty_idx] is not None:
                empty_idx += 1
            if empty_idx < gapped_size:
                for shift in range(empty_idx, insert_idx, -1):
                    gapped[shift] = gapped[shift - 1]
                gapped[insert_idx] = val
            else:
                empty_idx = insert_idx
                while empty_idx >= 0 and gapped[empty_idx] is not None:
                    empty_idx -= 1
                if empty_idx >= 0:
                    for shift in range(empty_idx, insert_idx - 1):
                        gapped[shift] = gapped[shift + 1]
                    gapped[insert_idx - 1] = val
                    
        inserted += 1
        if inserted == target or i == n - 1:
            active_vals = [x for x in gapped if x is not None]
            gapped = [None] * gapped_size
            step = max(1, gapped_size // (2 * len(active_vals)))
            for idx, val_act in enumerate(active_vals):
                gapped[idx * step] = val_act
            target *= 2
            
    sorted_vals = [x for x in gapped if x is not None]
    for idx in range(min(n, len(sorted_vals))):
        v.set(idx, sorted_vals[idx])

def stooge_sort_rec(v, l, h):
    v.check()
    if l >= h:
        return
    if v.get(l) > v.get(h):
        v.swapAt(l, h)
    if h - l + 1 > 2:
        t = (h - l + 1) // 3
        stooge_sort_rec(v, l, h - t)
        stooge_sort_rec(v, l + t, h)
        stooge_sort_rec(v, l, h - t)

def stooge_sort(v):
    stooge_sort_rec(v, 0, v.size() - 1)

def visual_is_sorted(v):
    for i in range(1, v.size()):
        if v.get(i - 1) > v.get(i):
            return False
    return True

def bogo_sort(v):
    rng = random.Random(1234567)
    n = v.size()
    while not visual_is_sorted(v):
        for i in range(n - 1, 0, -1):
            idx = rng.randint(0, i)
            v.swapAt(i, idx)

# --- Expanded Roster: 8 New Sorting Algorithms ---

def pdq_sort(v):
    n = v.size()
    if n <= 1:
        return
    pdq_sort_helper(v, 0, n - 1, limit=int(math.log2(n) * 2))

def pdq_sort_helper(v, lo, hi, limit):
    if hi - lo < 12:
        # Insertion sort fallback
        for i in range(lo + 1, hi + 1):
            val = v.get(i)
            j = i
            while j > lo and v.get(j - 1) > val:
                v.set(j, v.get(j - 1))
                j -= 1
            v.set(j, val)
        return
    if limit == 0:
        # Heapsort fallback
        pdq_heapsort(v, lo, hi)
        return
    # Partitioning
    p = pdq_partition(v, lo, hi)
    left_len = p - lo
    right_len = hi - p
    if left_len < (hi - lo) // 8 or right_len < (hi - lo) // 8:
        limit -= 1
    pdq_sort_helper(v, lo, p - 1, limit)
    pdq_sort_helper(v, p + 1, hi, limit)

def pdq_heapsort(v, lo, hi):
    n = hi - lo + 1
    for i in range(n // 2 - 1, -1, -1):
        pdq_sift_down(v, n, i, lo)
    for i in range(n - 1, 0, -1):
        v.swapAt(lo, lo + i)
        pdq_sift_down(v, i, 0, lo)

def pdq_sift_down(v, n, i, lo):
    root = i
    while root * 2 + 1 < n:
        child = root * 2 + 1
        if child + 1 < n and v.get(lo + child) < v.get(lo + child + 1):
            child += 1
        if v.get(lo + root) < v.get(lo + child):
            v.swapAt(lo + root, lo + child)
            root = child
        else:
            break

def pdq_partition(v, lo, hi):
    mid = (lo + hi) // 2
    if v.get(lo) > v.get(mid):
        v.swapAt(lo, mid)
    if v.get(lo) > v.get(hi):
        v.swapAt(lo, hi)
    if v.get(mid) > v.get(hi):
        v.swapAt(mid, hi)
    v.swapAt(mid, hi)
    pivot = v.get(hi)
    i = lo
    for j in range(lo, hi):
        if v.get(j) < pivot:
            v.swapAt(i, j)
            i += 1
    v.swapAt(i, hi)
    return i

def grail_sort(v):
    n = v.size()
    grail_sort_helper(v, 0, n - 1)

def grail_sort_helper(v, l, r):
    if l >= r:
        return
    mid = (l + r) // 2
    grail_sort_helper(v, l, mid)
    grail_sort_helper(v, mid + 1, r)
    grail_merge_inplace(v, l, mid, r)

def grail_merge_inplace(v, l, mid, r):
    i = l
    j = mid + 1
    while i <= mid and j <= r:
        if v.get(i) <= v.get(j):
            i += 1
        else:
            val = v.get(j)
            k = j
            while k > i:
                v.swapAt(k, k - 1)
                k -= 1
            i += 1
            mid += 1
            j += 1

def flash_sort(v):
    n = v.size()
    if n <= 1:
        return
    min_val = v.get(0)
    max_idx = 0
    for i in range(1, n):
        val = v.get(i)
        if val < min_val:
            min_val = val
        if val > v.get(max_idx):
            max_idx = i
            
    max_val = v.get(max_idx)
    if min_val == max_val:
        return
        
    m = int(0.43 * n)
    if m < 2:
        m = 2
        
    L = [0] * m
    c1 = (m - 1) / (max_val - min_val)
    for i in range(n):
        val = v.get(i)
        k = max(0, min(m - 1, int(c1 * (val - min_val))))
        L[k] += 1
        
    for k in range(1, m):
        L[k] += L[k - 1]
        
    v.swapAt(0, max_idx)
    
    move = 0
    j = 0
    k = m - 1
    while move < n - 1:
        while j > L[k] - 1:
            j += 1
            val = v.get(j)
            k = max(0, min(m - 1, int(c1 * (val - min_val))))
        flash_val = v.get(j)
        while j != L[k]:
            k = max(0, min(m - 1, int(c1 * (flash_val - min_val))))
            L[k] -= 1
            hold = v.get(L[k])
            v.set(L[k], flash_val)
            flash_val = hold
            move += 1
        j += 1
        
    # Insertion sort pass
    for i in range(1, n):
        val = v.get(i)
        j = i
        while j > 0 and v.get(j - 1) > val:
            v.set(j, v.get(j - 1))
            j -= 1
        v.set(j, val)

def wiki_sort(v):
    n = v.size()
    width = 1
    while width < n:
        for i in range(0, n, 2 * width):
            mid = min(i + width - 1, n - 1)
            r = min(i + 2 * width - 1, n - 1)
            grail_merge_inplace(v, i, mid, r)
        width *= 2

def sleep_sort(v):
    n = v.size()
    if n <= 1:
        return
    heap = []
    for i in range(n):
        heap.append(v.get(i))
        
    def sift_down(arr, heap_size, root):
        while root * 2 + 1 < heap_size:
            child = root * 2 + 1
            if child + 1 < heap_size and arr[child] > arr[child + 1]:
                child += 1
            if arr[root] > arr[child]:
                arr[root], arr[child] = arr[child], arr[root]
                root = child
            else:
                break
                
    for i in range(n // 2 - 1, -1, -1):
        sift_down(heap, n, i)
        
    for i in range(n):
        min_val = heap[0]
        v.set(i, min_val)
        if len(heap) > 1:
            heap[0] = heap[len(heap) - 1]
            heap.pop()
            sift_down(heap, len(heap), 0)

def american_flag_sort(v):
    n = v.size()
    if n <= 1:
        return
    max_val = v.get(0)
    for i in range(1, n):
        val = v.get(i)
        if val > max_val:
            max_val = val
    radix = 10
    exp = 1
    while max_val // exp > 0:
        american_flag_sort_helper(v, 0, n - 1, exp, radix)
        exp *= radix

def american_flag_sort_helper(v, lo, hi, exp, radix):
    count = [0] * radix
    for i in range(lo, hi + 1):
        digit = (v.get(i) // exp) % radix
        count[digit] += 1
    offset = [0] * radix
    offset[0] = lo
    for i in range(1, radix):
        offset[i] = offset[i - 1] + count[i - 1]
    next_anchor = list(offset)
    for r in range(radix):
        limit = offset[r] + count[r] if r < radix - 1 else hi + 1
        while next_anchor[r] < limit:
            val = v.get(next_anchor[r])
            digit = (val // exp) % radix
            if digit == r:
                next_anchor[r] += 1
            else:
                dest = next_anchor[digit]
                next_anchor[digit] += 1
                hold = v.get(dest)
                v.set(dest, val)
                v.set(next_anchor[r], hold)

def gravity_sort(v):
    n = v.size()
    if n <= 1:
        return
    max_val = v.get(0)
    for i in range(1, n):
        val = v.get(i)
        if val > max_val:
            max_val = val
    if max_val <= 0:
        return
    beads = [0] * max_val
    for i in range(n):
        val = v.get(i)
        for col in range(min(val, max_val)):
            beads[col] += 1
    for i in range(n - 1, -1, -1):
        val = 0
        for col in range(max_val):
            if beads[col] > 0:
                val += 1
                beads[col] -= 1
        v.set(i, val)

def slow_sort(v):
    n = v.size()
    slow_sort_helper(v, 0, n - 1)

def slow_sort_helper(v, i, j):
    if i >= j:
        return
    m = (i + j) // 2
    slow_sort_helper(v, i, m)
    slow_sort_helper(v, m + 1, j)
    if v.get(m) > v.get(j):
        v.swapAt(m, j)
    slow_sort_helper(v, i, j - 1)


# --- Algorithms Roster and Metadata ---

def get_algorithms():
    return [
        # POOL 1 — ELITE CONTENDERS
        {
            "name": "IntroSort", "sort": intro_sort, "category": "Elite Contenders",
            "year": 1997, "inventor": "David Musser", "complexity": "O(N log N)",
            "stable": False, "memory": "O(log N)",
            "description": "Dynamic hybrid: Quick Sort falling back to Heap Sort and Insertion Sort.",
            "personality": "Calculated and adaptive. Ready to swap strategies to prevent worst cases."
        },
        {
            "name": "Timsort", "sort": tim_sort, "category": "Elite Contenders",
            "year": 2002, "inventor": "Tim Peters", "complexity": "O(N log N)",
            "stable": True, "memory": "O(N)",
            "description": "Real-world optimizer that identifies runs and merges them.",
            "personality": "Sleek and adaptive. Loves real-world patterns."
        },
        {
            "name": "Merge Sort", "sort": merge_sort, "category": "Elite Contenders",
            "year": 1945, "inventor": "John von Neumann", "complexity": "O(N log N)",
            "stable": True, "memory": "O(N)",
            "description": "Classic divide-and-conquer algorithm using run merges.",
            "personality": "Predictable, steady, and memory-hungry."
        },
        {
            "name": "Quick Sort", "sort": quick_sort, "category": "Elite Contenders",
            "year": 1959, "inventor": "Tony Hoare", "complexity": "O(N log N)",
            "stable": False, "memory": "O(log N)",
            "description": "Pivot-based partitioner. Standard in performance benchmarks.",
            "personality": "Live fast, die by bad pivots."
        },
        {
            "name": "3-Way Quick Sort", "sort": quick3_sort, "category": "Elite Contenders",
            "year": 1960, "inventor": "Tony Hoare / Sedgewick", "complexity": "O(N log N)",
            "stable": False, "memory": "O(log N)",
            "description": "Quicksort with three partitions. Optimal for duplicated keys.",
            "personality": "Duplicates make me faster!"
        },
        {
            "name": "Heap Sort", "sort": heap_sort, "category": "Elite Contenders",
            "year": 1964, "inventor": "J. W. J. Williams", "complexity": "O(N log N)",
            "stable": False, "memory": "O(1)",
            "description": "Selection-based sort that builds a binary heap.",
            "personality": "Reliable. Boring. Effective."
        },
        {
            "name": "Shell Sort", "sort": shell_sort, "category": "Elite Contenders",
            "year": 1959, "inventor": "Donald Shell", "complexity": "O(N (log N)^2)",
            "stable": False, "memory": "O(1)",
            "description": "Insertion sort generalization using shrinking gaps.",
            "personality": "Mind the gap. I jump far."
        },
        {
            "name": "Natural Merge Sort", "sort": natural_merge_sort, "category": "Elite Contenders",
            "year": 1945, "inventor": "John von Neumann", "complexity": "O(N log N)",
            "stable": True, "memory": "O(N)",
            "description": "Merge sort that scans for natural sorted subsegments.",
            "personality": "A path-finder that merges pre-sorted runs."
        },
        
        # POOL 2 — LINEAR-TIME SPECIALISTS
        {
            "name": "Counting Sort", "sort": counting_sort, "category": "Linear-Time Specialists",
            "year": 1954, "inventor": "Harold H. Seward", "complexity": "O(N + K)",
            "stable": True, "memory": "O(N + K)",
            "description": "Sorts by building a count dictionary directly.",
            "personality": "I don't compare; I count."
        },
        {
            "name": "Radix Sort (LSD)", "sort": radix_sort, "category": "Linear-Time Specialists",
            "year": 1929, "inventor": "Herman Hollerith", "complexity": "O(N * W)",
            "stable": True, "memory": "O(N + K)",
            "description": "LSD radix sorting values digit by digit.",
            "personality": "Loves integers. Builds order digit by digit."
        },
        {
            "name": "MSD Radix Sort", "sort": msd_radix_sort, "category": "Linear-Time Specialists",
            "year": 1954, "inventor": "Harold H. Seward", "complexity": "O(N * W)",
            "stable": True, "memory": "O(N + K)",
            "description": "Recursive digit sorter from most significant down.",
            "personality": "Top-down precision. Divides by powerful digits."
        },
        {
            "name": "Bucket Sort", "sort": bucket_sort, "category": "Linear-Time Specialists",
            "year": 1956, "inventor": "E. J. Isaac", "complexity": "O(N + K)",
            "stable": True, "memory": "O(N + K)",
            "description": "Distributes values into buckets, then sorts them individually.",
            "personality": "Organized compartmentalizer. Let's bucket it."
        },
        {
            "name": "Pigeonhole Sort", "sort": pigeonhole_sort, "category": "Linear-Time Specialists",
            "year": 1842, "inventor": "Peter Gustav Dirichlet", "complexity": "O(N + Range)",
            "stable": True, "memory": "O(N + Range)",
            "description": "Places items in value holes and aggregates them.",
            "personality": "Dirichlet's pride. One pigeon per hole."
        },
        {
            "name": "Tree Sort", "sort": tree_sort, "category": "Linear-Time Specialists",
            "year": 1962, "inventor": "Robert W. Floyd", "complexity": "O(N log N)",
            "stable": True, "memory": "O(N)",
            "description": "Builds a Binary Search Tree and performs in-order traversal.",
            "personality": "Branching out. I grow trees to find order."
        },
        {
            "name": "Tournament Sort", "sort": tournament_sort, "category": "Linear-Time Specialists",
            "year": 1957, "inventor": "H. H. Seward", "complexity": "O(N log N)",
            "stable": False, "memory": "O(N)",
            "description": "Selects minimums using a knockout tree structure.",
            "personality": "Bracket builder. The winner goes to the top."
        },
        {
            "name": "Strand Sort", "sort": strand_sort, "category": "Linear-Time Specialists",
            "year": 1970, "inventor": "Unknown", "complexity": "O(N^2)",
            "stable": True, "memory": "O(N)",
            "description": "Extracts ascending strands and merges them recursively.",
            "personality": "Extracting threads of order from confusion."
        },
        
        # POOL 3 — MID-TIER CHALLENGERS
        {
            "name": "Bitonic Sort", "sort": bitonic_sort, "category": "Mid-Tier Challengers",
            "year": 1968, "inventor": "Ken Batcher", "complexity": "O(N (log N)^2)",
            "stable": False, "memory": "O(N log N)",
            "description": "Parallel sorting network using bitonic sequence merges.",
            "personality": "Symmetry in motion. Up and down merge networks."
        },
        {
            "name": "Comb Sort", "sort": comb_sort, "category": "Mid-Tier Challengers",
            "year": 1980, "inventor": "Wlodzimierz Dobosiewicz", "complexity": "O(N log N)",
            "stable": False, "memory": "O(1)",
            "description": "Combats Bubble Sort turtles using gap sizes.",
            "personality": "A Bubble sort with a comb to smooth the kinks."
        },
        {
            "name": "Binary Insertion Sort", "sort": binary_insertion_sort, "category": "Mid-Tier Challengers",
            "year": 1946, "inventor": "John Mauchly", "complexity": "O(N^2)",
            "stable": True, "memory": "O(1)",
            "description": "Insertion sort with binary search for faster insertion indexes.",
            "personality": "Searches fast, shifts slow."
        },
        {
            "name": "Cycle Sort", "sort": cycle_sort, "category": "Mid-Tier Challengers",
            "year": 2013, "inventor": "W. P. Barlow", "complexity": "O(N^2)",
            "stable": False, "memory": "O(1)",
            "description": "In-place write miser. Minimizes array writes.",
            "personality": "I hate writing. I only swap if forced."
        },
        {
            "name": "Pancake Sort", "sort": pancake_sort, "category": "Mid-Tier Challengers",
            "year": 1979, "inventor": "Harry Dweighter", "complexity": "O(N^2)",
            "stable": False, "memory": "O(1)",
            "description": "Flips prefixes of the array using a spatula.",
            "personality": "Spatula flipper. Let's make breakfast."
        },
        {
            "name": "Insertion Sort", "sort": insertion_sort, "category": "Mid-Tier Challengers",
            "year": 1959, "inventor": "Unknown", "complexity": "O(N^2)",
            "stable": True, "memory": "O(1)",
            "description": "Slides cards into their proper position in the sorted hand.",
            "personality": "Classic card-dealer style. Patiently inserting."
        },
        {
            "name": "Selection Sort", "sort": selection_sort, "category": "Mid-Tier Challengers",
            "year": 1956, "inventor": "Unknown", "complexity": "O(N^2)",
            "stable": False, "memory": "O(1)",
            "description": "Repeatedly finds minimum values and places them in order.",
            "personality": "Slowly scans, picks the smallest, and repeats."
        },
        {
            "name": "Bubble Sort", "sort": bubble_sort, "category": "Mid-Tier Challengers",
            "year": 1956, "inventor": "Edward H. Friend", "complexity": "O(N^2)",
            "stable": True, "memory": "O(1)",
            "description": "Repeatedly floats adjacent large values to the top.",
            "personality": "Float up like bubbles. Slow, heavy, classic."
        },
        
        # POOL 4 — WEIRDOS AND MEMES
        {
            "name": "Cocktail Shaker Sort", "sort": cocktail_sort, "category": "Weirdos and Memes",
            "year": 1980, "inventor": "Unknown", "complexity": "O(N^2)",
            "stable": True, "memory": "O(1)",
            "description": "Bi-directional bubble sort that clears turtles quickly.",
            "personality": "Shakes back and forth. Double the bubbles."
        },
        {
            "name": "Gnome Sort", "sort": gnome_sort, "category": "Weirdos and Memes",
            "year": 2000, "inventor": "Hamid Sarbazi-Azad", "complexity": "O(N^2)",
            "stable": True, "memory": "O(1)",
            "description": "Garden gnome sorting method that steps back to fix errors.",
            "personality": "A stubborn garden gnome shuffling flowerpots."
        },
        {
            "name": "Odd-Even Sort", "sort": odd_even_sort, "category": "Weirdos and Memes",
            "year": 1972, "inventor": "N. Habermann", "complexity": "O(N^2)",
            "stable": True, "memory": "O(1)",
            "description": "Bubble variant that checks odd pairs, then even pairs.",
            "personality": "Strict alternation. Odd pairs, then even pairs."
        },
        {
            "name": "Smoothsort", "sort": smooth_sort, "category": "Weirdos and Memes",
            "year": 1981, "inventor": "Edsger Dijkstra", "complexity": "O(N log N)",
            "stable": False, "memory": "O(1)",
            "description": "Adaptive heapsort using Leonardo numbers.",
            "personality": "Dijkstra's pride. Over-engineered but O(N) on sorted inputs!"
        },
        {
            "name": "Patience Sort", "sort": patience_sort, "category": "Weirdos and Memes",
            "year": 2001, "inventor": "C. L. Mallows", "complexity": "O(N log N)",
            "stable": False, "memory": "O(N)",
            "description": "Uses piles of descending elements like solitaire.",
            "personality": "Solitaire master. Builds piles and merges them."
        },
        {
            "name": "Library Sort", "sort": library_sort, "category": "Weirdos and Memes",
            "year": 2004, "inventor": "Michael A. Bender", "complexity": "O(N log N)",
            "stable": False, "memory": "O(N)",
            "description": "Gapped insertion sort. Speeds insertions by leaving spaces.",
            "personality": "Leaving spaces on the bookshelves. Don't crowd me."
        },
        {
            "name": "Stooge Sort", "sort": stooge_sort, "category": "Weirdos and Memes",
            "year": 1984, "inventor": "Howard, Fine, et al.", "complexity": "O(N^2.7)",
            "stable": False, "memory": "O(N)",
            "description": "Recursively swaps end values and sorts 2/3rds in a slow loop.",
            "personality": "Pure chaos. The three stooges slapping numbers."
        },
        {
            "name": "Bogo Sort", "sort": bogo_sort, "category": "Weirdos and Memes",
            "year": 1980, "inventor": "Unknown", "complexity": "O(N * N!)",
            "stable": False, "memory": "O(1)",
            "description": "Shuffles randomly until sorted. Highly inefficient.",
            "personality": "Has absolutely no plan."
        },
        # --- NEWCOMERS (DEBUT YEAR 2026) ---
        {
            "name": "PDQSort", "sort": pdq_sort, "category": "Elite Contenders",
            "year": 2016, "inventor": "Orson Peters", "complexity": "O(N log N)",
            "stable": False, "memory": "O(log N)",
            "description": "Pattern-Defeating Quicksort. Fast hybrid that adapts to pre-sorted patterns.",
            "personality": "Ultra-modern speed demon. Hates predictable inputs.",
            "debut_year": 2026
        },
        {
            "name": "GrailSort", "sort": grail_sort, "category": "Elite Contenders",
            "year": 2013, "inventor": "Andrey Astrelin", "complexity": "O(N log N)",
            "stable": True, "memory": "O(1)",
            "description": "Block Merge Sort. In-place stable merge sort using buffer blocks.",
            "personality": "Defends stability with absolute minimal resources.",
            "debut_year": 2026
        },
        {
            "name": "Flash Sort", "sort": flash_sort, "category": "Linear-Time Specialists",
            "year": 1998, "inventor": "Karl-Dietrich Neubert", "complexity": "O(N)",
            "stable": False, "memory": "O(1)",
            "description": "Flashsort. In-place distribution sort utilizing permutation cycles.",
            "personality": "Flashes through uniform arrays in linear speed.",
            "debut_year": 2026
        },
        {
            "name": "WikiSort", "sort": wiki_sort, "category": "Elite Contenders",
            "year": 2014, "inventor": "Mike McFarlane", "complexity": "O(N log N)",
            "stable": True, "memory": "O(1)",
            "description": "In-place block merge sort variation optimized for speed and simplicity.",
            "personality": "Pragmatic divider. Merging without extra room.",
            "debut_year": 2026
        },
        {
            "name": "Sleep Sort", "sort": sleep_sort, "category": "Weirdos and Memes",
            "year": 2011, "inventor": "4chan Anonymous", "complexity": "O(N + max(A))",
            "stable": True, "memory": "O(N)",
            "description": "Simulated multi-threaded sleeping queue. Rest and rise in order.",
            "personality": "Extremely relaxed. Takes a nap before doing anything.",
            "debut_year": 2026
        },
        {
            "name": "American Flag Sort", "sort": american_flag_sort, "category": "Linear-Time Specialists",
            "year": 1993, "inventor": "Peter McIlroy", "complexity": "O(N * W)",
            "stable": False, "memory": "O(K)",
            "description": "In-place bucket-radix sort grouping elements by digits.",
            "personality": "Patriotic partitioner. Saluting structured values.",
            "debut_year": 2026
        },
        {
            "name": "Gravity Sort", "sort": gravity_sort, "category": "Weirdos and Memes",
            "year": 2002, "inventor": "Arulanandham et al.", "complexity": "O(N * Max)",
            "stable": True, "memory": "O(N * Max)",
            "description": "Bead Sort. Slides numbers down like beads on gravity poles.",
            "personality": "Antigravity enthusiast! Let beads fall into place.",
            "debut_year": 2026
        },
        {
            "name": "Slowsort", "sort": slow_sort, "category": "Weirdos and Memes",
            "year": 1989, "inventor": "McIlroy et al.", "complexity": "O(N^(log N))",
            "stable": False, "memory": "O(log N)",
            "description": "Humorous worst-case sorter. Purely academic.",
            "personality": "Purely academic. Procrastinates recursively.",
            "debut_year": 2026
        }
    ]


# --- Sorter Runner ---

class Accumulator:
    def __init__(self):
        self.value = 0

def run_sorter(algo_fn, input_arr, state, cancel_event, pause_event, paused_ns_accum, visual_delay, scale_factor=1.0):
    if visual_delay > 0:
        target = max(1, int(0.033 / visual_delay))
        mask = 1
        while mask < target:
            mask = (mask << 1) | 1
        mask = min(511, mask)
    else:
        n = len(input_arr)
        target = max(16383, n // 8)
        mask = 16383
        while mask < target:
            mask = (mask << 1) | 1
        
    context = SortContext(cancel_event, pause_event, paused_ns_accum, mask)
    array = VisualArray(input_arr, state, context, visual_delay, publish_mask=mask, scale_factor=scale_factor)

    start_time = time.perf_counter_ns()
    try:
        algo_fn(array)
        end_time = time.perf_counter_ns()
        
        elapsed_ns = (end_time - start_time) - paused_ns_accum.value
        elapsed_ns = max(0, elapsed_ns)
        
        final_values = array.snapshot()
        is_srt = array.sorted()
        array.publish(-1, -1)
        
        with state.lock:
            state.sorted = is_srt
            state.cancelled = False
            state.ns = elapsed_ns
            state.elapsed_ms = elapsed_ns // 1_000_000
            state.final_values = final_values
            state.hotA = -1
            state.hotB = -1
            state.done = True
    except CancelledException:
        end_time = time.perf_counter_ns()
        elapsed_ns = (end_time - start_time) - paused_ns_accum.value
        elapsed_ns = max(0, elapsed_ns)
        final_values = array.snapshot()
        array.publish(-1, -1)
        
        with state.lock:
            state.sorted = False
            state.cancelled = True
            state.ns = elapsed_ns
            state.elapsed_ms = elapsed_ns // 1_000_000
            state.final_values = final_values
            state.hotA = -1
            state.hotB = -1
            state.done = True
    except Exception:
        end_time = time.perf_counter_ns()
        elapsed_ns = (end_time - start_time) - paused_ns_accum.value
        elapsed_ns = max(0, elapsed_ns)
        final_values = array.snapshot()
        array.publish(-1, -1)
        
        with state.lock:
            state.sorted = False
            state.cancelled = False
            state.ns = elapsed_ns
            state.elapsed_ms = elapsed_ns // 1_000_000
            state.final_values = final_values
            state.hotA = -1
            state.hotB = -1
            state.done = True

def make_input(scenario_type, n, rng):
    a = list(range(1, n + 1))
    if scenario_type == 0:  # Sorted
        return a
    elif scenario_type == 1:  # Randomized
        rng.shuffle(a)
        return a
    elif scenario_type == 2:  # Reversed
        a.reverse()
        return a
    elif scenario_type == 3:  # OneNumberUnsorted
        from_idx = (n * 3) // 4
        to_idx = n // 4
        val = a.pop(from_idx)
        a.insert(to_idx, val)
        return a
    elif scenario_type == 4:  # RandomizedDuplicates
        res = []
        for _ in range(n):
            res.append(5 + rng.randint(0, 7) * 11)
        rng.shuffle(res)
        return res
    elif scenario_type == 5:  # Random with tiny range (0-31)
        return [rng.randint(0, 31) for _ in range(n)]
    elif scenario_type == 6:  # Random with huge range (0-1B)
        return [rng.randint(0, 1_000_000_000) for _ in range(n)]
    elif scenario_type == 7:  # Organ Pipe
        half = n // 2
        first_half = list(range(1, half + 1))
        second_half = list(range(n - half, 0, -1))
        if len(first_half) + len(second_half) < n:
            first_half.append(half + 1)
        return first_half + second_half
    elif scenario_type == 8:  # Sawtooth
        period = max(1, n // 5)
        res = []
        for i in range(n):
            res.append(i % period)
        return res
    elif scenario_type == 9:  # Half Reversed Half Sorted
        half = n // 2
        first_half = list(range(half, 0, -1))
        second_half = list(range(half + 1, n + 1))
        if len(first_half) + len(second_half) < n:
            first_half.append(half + 1)
        return first_half + second_half
    return a

def adjacent_disorder(a):
    bad = 0
    for i in range(1, len(a)):
        if a[i - 1] > a[i]:
            bad += 1
    return bad

# --- ELO and Win Probability Helper Functions ---

def update_elo(algoA, algoB, result, K=32):
    rA = algoA.get('elo', 1500.0)
    rB = algoB.get('elo', 1500.0)
    
    eA = 1.0 / (1.0 + 10.0 ** ((rB - rA) / 400.0))
    eB = 1.0 / (1.0 + 10.0 ** ((rA - rB) / 400.0))
    
    if result.tie:
        sA = 0.5
        sB = 0.5
    elif result.winner == 0:
        sA = 1.0
        sB = 0.0
    else:
        sA = 0.0
        sB = 1.0
        
    diffA = K * (sA - eA)
    diffB = K * (sB - eB)
    
    algoA['elo'] = rA + diffA
    algoB['elo'] = rB + diffB
    
    algoA['tournament_elo_diff'] = algoA.get('tournament_elo_diff', 0.0) + diffA
    algoB['tournament_elo_diff'] = algoB.get('tournament_elo_diff', 0.0) + diffB
    
    import database
    database.save_elo_ratings({
        algoA['name']: algoA['elo'],
        algoB['name']: algoB['elo']
    })

def estimate_win_probability(algoA, algoB):
    rA = algoA.get('elo', 1500.0)
    rB = algoB.get('elo', 1500.0)
    
    # Expected ELO probability
    prob_elo = 1.0 / (1.0 + 10.0 ** ((rB - rA) / 400.0))
    
    # Historical win rate
    import database
    stats = database.get_historical_stats()
    
    wrA = 0.5
    if algoA['name'] in stats:
        sA = stats[algoA['name']]
        if sA['played'] > 0:
            wrA = sA['won'] / sA['played']
            
    wrB = 0.5
    if algoB['name'] in stats:
        sB = stats[algoB['name']]
        if sB['played'] > 0:
            wrB = sB['won'] / sB['played']
            
    prob_hist = 0.5
    if wrA != 0.5 or wrB != 0.5:
        prob_hist = wrA / (wrA + wrB) if (wrA + wrB) > 0 else 0.5
        
    # Scenario performance matching
    scen_perf = database.get_scenario_performance()
    scen_winsA = 0
    scen_winsB = 0
    
    perfA = scen_perf.get(algoA['name'], {})
    perfB = scen_perf.get(algoB['name'], {})
    
    for s_id in range(10):
        pA = perfA.get(s_id) or perfA.get(str(s_id))
        pB = perfB.get(s_id) or perfB.get(str(s_id))
        if pA and pB:
            if pA['avg_time_ns'] < pB['avg_time_ns']:
                scen_winsA += 1
            elif pA['avg_time_ns'] > pB['avg_time_ns']:
                scen_winsB += 1
                
    prob_scen = 0.5
    if (scen_winsA + scen_winsB) > 0:
        prob_scen = scen_winsA / (scen_winsA + scen_winsB)
        
    # Weights: ELO (60%), History (20%), Scenario strengths (20%)
    weight_elo = 0.6
    weight_hist = 0.2 if (wrA != 0.5 or wrB != 0.5) else 0.0
    weight_scen = 0.2 if (scen_winsA + scen_winsB) > 0 else 0.0
    
    total_w = weight_elo + weight_hist + weight_scen
    final_prob = (prob_elo * weight_elo + prob_hist * weight_hist + prob_scen * weight_scen) / total_w
    final_prob = max(0.01, min(0.99, final_prob))
    
    pctA = int(final_prob * 100)
    pctB = 100 - pctA
    return pctA, pctB

def compute_rankings(algos):
    sorted_algos = sorted(algos, key=lambda x: x.get('elo', 1500.0), reverse=True)
    return {a['name']: idx + 1 for idx, a in enumerate(sorted_algos)}

# --- Tournament Execution Engine ---

def race(algoA, algoB, input_arr, title, scenario, round_num, mode, array_size, visual_delay, timeout, match_score=None, group_id=None, standings=None, algo_names=None, bracket=None, current_match_idx=None, stage_winners=None, display_size=None, stage_scores=None):
    timeout = min(240.0, timeout)
    stA = VisualState(algoA['name'])
    stB = VisualState(algoB['name'])
    
    cancelA = threading.Event()
    cancelB = threading.Event()
    
    pauseA = threading.Event()
    pauseB = threading.Event()
    
    paused_nsA = Accumulator()
    paused_nsB = Accumulator()
    
    tui_size = display_size if display_size is not None else array_size
    scale_factor = float(tui_size) / len(input_arr)
    
    threadA = threading.Thread(
        target=run_sorter,
        args=(algoA['sort'], input_arr, stA, cancelA, pauseA, paused_nsA, visual_delay, scale_factor)
    )
    threadB = threading.Thread(
        target=run_sorter,
        args=(algoB['sort'], input_arr, stB, cancelB, pauseB, paused_nsB, visual_delay, scale_factor)
    )
    
    threadA.start()
    threadB.start()
    
    start_time = time.perf_counter()
    grace_end = None
    forced_tie = False
    
    import terminal_ui
    
    while True:
        with stA.lock:
            doneA = stA.done
            sortedA = stA.sorted
        with stB.lock:
            doneB = stB.done
            sortedB = stB.sorted
            
        now = time.perf_counter()
        elapsed = now - start_time
        elapsed_ms = int(elapsed * 1000)
        
        with stA.lock:
            if not stA.done:
                stA.elapsed_ms = elapsed_ms
        with stB.lock:
            if not stB.done:
                stB.elapsed_ms = elapsed_ms
                
        if mode == 'knockout':
            if doneA and sortedA and not doneB:
                cancelB.set()
            if doneB and sortedB and not doneA:
                cancelA.set()
            if elapsed > timeout:
                if not doneA: cancelA.set()
                if not doneB: cancelB.set()
        else:  # group mode
            if doneA and sortedA and not doneB and grace_end is None:
                grace_end = now + 1.0
            if doneB and sortedB and not doneA and grace_end is None:
                grace_end = now + 1.0
                
            if grace_end and now > grace_end:
                if not doneA: cancelA.set()
                if not doneB: cancelB.set()
                
            if not sortedA and not sortedB and elapsed > timeout:
                forced_tie = True
                cancelA.set()
                cancelB.set()
                
        terminal_ui.render_live_race(
            stA, stB, SCENARIO_NAMES[scenario], SCENARIO_DESCRIPTIONS[scenario], round_num, tui_size,
            match_score=match_score, group_id=group_id, standings=standings, algo_names=algo_names,
            stage_title=title, bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners,
            stage_scores=stage_scores
        )
        
        if doneA and doneB:
            break
            
        time.sleep(0.033)
        
    threadA.join()
    threadB.join()
    
    terminal_ui.render_live_race(
        stA, stB, SCENARIO_NAMES[scenario], SCENARIO_DESCRIPTIONS[scenario], round_num, tui_size,
        match_score=match_score, group_id=group_id, standings=standings, algo_names=algo_names,
        stage_title=title, bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners,
        stage_scores=stage_scores
    )

    rr = RaceResult()
    with stA.lock:
        rr.nsA = stA.ns
        rr.sortedA = stA.sorted
        rr.cancelledA = stA.cancelled
        rr.opsA = stA.operations
        finalA = list(stA.final_values)
    with stB.lock:
        rr.nsB = stB.ns
        rr.sortedB = stB.sorted
        rr.cancelledB = stB.cancelled
        rr.opsB = stB.operations
        finalB = list(stB.final_values)
        
    if forced_tie and mode == 'group':
        rr.tie = True
        rr.winner_slot = -1
    elif rr.sortedA != rr.sortedB:
        rr.winner_slot = 0 if rr.sortedA else 1
    elif rr.sortedA and rr.sortedB:
        rr.winner_slot = 0 if rr.nsA <= rr.nsB else 1
    else:
        badA = adjacent_disorder(finalA)
        badB = adjacent_disorder(finalB)
        if badA != badB:
            rr.winner_slot = 0 if badA < badB else 1
        else:
            rr.winner_slot = 0 if rr.nsA <= rr.nsB else 1
            
    return rr

def play_match(algoA, algoB, stage_title, rng, mode, array_size, visual_delay, timeout, group_id=None, standings=None, algo_names=None, bracket=None, current_match_idx=None, stage_winners=None, display_size=None, stage_scores=None, algo_list=None, tournament=None):
    if mode == 'knockout':
        scenarios = rng.sample(range(10), 5)
    else:
        scenarios = [0, 1, 2, 3, 4]
    winsA = 0
    winsB = 0
    ties = 0
    match_nsA = 0
    match_nsB = 0
    
    import terminal_ui
    
    # Pre-match Showdown Preview
    if algo_list:
        rankings = compute_rankings(algo_list)
        rankA = rankings.get(algoA['name'], 32)
        rankB = rankings.get(algoB['name'], 32)
        probA, probB = estimate_win_probability(algoA, algoB)
        terminal_ui.render_pre_match_intro(algoA, algoB, rankA, rankB, probA, probB, stage_title)
        
        # Flush key buffer to prevent skip
        time.sleep(0.5)
        if tournament and getattr(tournament, 'autoplay', False):
            time.sleep(1.5)
        else:
            while terminal_ui.read_key(block=False) is not None:
                pass
            while True:
                if terminal_ui.read_key(block=True) == 'enter':
                    break
                
    for round_num in range(1, 6):
        scenario = scenarios[round_num - 1]
        input_arr = make_input(scenario, array_size, rng)
        
        rr = race(
            algoA, algoB, input_arr, stage_title, scenario, round_num, mode,
            array_size, visual_delay, timeout,
            match_score=(winsA, winsB, ties),
            group_id=group_id, standings=standings, algo_names=algo_names,
            bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners,
            display_size=display_size,
            stage_scores=stage_scores
        )

        match_nsA += rr.nsA
        match_nsB += rr.nsB
        
        if rr.tie:
            ties += 1
        elif rr.winner_slot == 0:
            winsA += 1
        else:
            winsB += 1
            
        # Update database scenario stats per round
        import database
        if rr.sortedA:
            database.update_historical_stats(algoA['name'], round_time_ns=rr.nsA)
            database.update_scenario_performance(algoA['name'], scenario, rr.nsA, rr.opsA)
        if rr.sortedB:
            database.update_historical_stats(algoB['name'], round_time_ns=rr.nsB)
            database.update_scenario_performance(algoB['name'], scenario, rr.nsB, rr.opsB)
            
        # Update tournament-wide stats
        if tournament:
            if rr.sortedA:
                tournament.total_sorted_rounds[algoA['name']] += 1
                tournament.total_sorted_time_ns[algoA['name']] += rr.nsA
                if rr.nsA < tournament.fastest_round_ns:
                    tournament.fastest_round_ns = rr.nsA
                    tournament.fastest_round_algo = algoA['name']
                if rr.opsA < tournament.lowest_ops_round_val:
                    tournament.lowest_ops_round_val = rr.opsA
                    tournament.lowest_ops_round_algo = algoA['name']
            if rr.sortedB:
                tournament.total_sorted_rounds[algoB['name']] += 1
                tournament.total_sorted_time_ns[algoB['name']] += rr.nsB
                if rr.nsB < tournament.fastest_round_ns:
                    tournament.fastest_round_ns = rr.nsB
                    tournament.fastest_round_algo = algoB['name']
                if rr.opsB < tournament.lowest_ops_round_val:
                    tournament.lowest_ops_round_val = rr.opsB
                    tournament.lowest_ops_round_algo = algoB['name']
                    
        match_decided = winsA == 3 or winsB == 3 or (round_num == 5 and mode == 'group')
        
        if match_decided:
            terminal_ui.draw_round_result(
                algoA['name'], algoB['name'], rr, winsA, winsB, ties, stage_title,
                group_id=group_id, standings=standings, algo_names=algo_names,
                bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners,
                stage_scores=stage_scores
            )
            if mode == 'knockout':
                if tournament and getattr(tournament, 'autoplay', False):
                    time.sleep(1.5)
                else:
                    print("\n  Press Enter to continue to the next knockout match...")
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
            else:
                time.sleep(2.0)
            break
        else:
            time.sleep(0.3)

    result = MatchResult()
    result.winsA = winsA
    result.winsB = winsB
    result.ties = ties
    result.nsA = match_nsA
    result.nsB = match_nsB
    
    if winsA == winsB and mode == 'group':
        result.tie = True
        result.winner = -1
        result.loser = -1
    else:
        result.winner = 0 if winsA > winsB else 1
        result.loser = 1 if winsA > winsB else 0
        
    # Update match stats in database
    wonA = 1 if result.winner == 0 else 0
    lostA = 1 if result.winner == 1 else 0
    wonB = 1 if result.winner == 1 else 0
    lostB = 1 if result.winner == 0 else 0
    
    ptsA = 3 if wonA else (1 if result.tie else 0)
    ptsB = 3 if wonB else (1 if result.tie else 0)
    draws_inc = 1 if result.tie else 0
    
    import database
    database.update_historical_stats(
        algoA['name'],
        match_played=1,
        match_won=wonA,
        match_lost=lostA,
        match_draws=draws_inc,
        points_inc=ptsA,
        round_wins=winsA,
        round_losses=winsB
    )
    database.update_historical_stats(
        algoB['name'],
        match_played=1,
        match_won=wonB,
        match_lost=lostB,
        match_draws=draws_inc,
        points_inc=ptsB,
        round_wins=winsB,
        round_losses=winsA
    )
    
    # Update ELO ratings
    update_elo(algoA, algoB, result)
    
    # Update Giant Killer stat
    if tournament and result.winner is not None and not result.tie:
        winner = algoA if result.winner == 0 else algoB
        loser = algoB if result.winner == 0 else algoA
        if winner['elo'] < loser['elo']:
            elo_diff = loser['elo'] - winner['elo']
            tournament.giant_kills.append({
                "winner": winner['name'],
                "loser": loser['name'],
                "elo_diff": elo_diff
            })
            
    if stage_scores is not None:
        stage_scores.append((winsA, winsB))
        
    return result

class Tournament:
    def __init__(self, algos, array_size=100000, knockouts_size=1000000, final_size=10000000, visual_delay=0.0, group_timeout=30, ko_timeout=60, final_timeout=240, autoplay=False):
        self.algos = algos
        self.array_size = array_size
        self.knockouts_size = knockouts_size
        self.final_size = final_size
        self.visual_delay = visual_delay
        self.group_timeout = group_timeout
        self.ko_timeout = ko_timeout
        self.final_timeout = final_timeout
        self.autoplay = autoplay
        self.rng = random.Random()
        
        self.groups = [[] for _ in range(8)]
        self.fixtures = []
        self.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0, 'ko_played': 0, 'ko_points': 0, 'ko_matchWins': 0, 'ko_matchLosses': 0, 'ko_roundWins': 0, 'ko_roundLosses': 0, 'ko_ns': 0} for i in range(len(self.algos))]
        self.current_bracket = []
        self.bracket_entrants = []
        self.current_stage = "Group Stage"
        self.next_fixture_idx = 0
        self.year = 2026
        
        # Division details
        new_algo_names = ["PDQSort", "GrailSort", "Flash Sort", "WikiSort", "Sleep Sort", "American Flag Sort", "Gravity Sort", "Slowsort"]
        self.wc_teams = [a['name'] for a in self.algos if a['name'] not in new_algo_names]
        self.challenger_teams = [a['name'] for a in self.algos if a['name'] in new_algo_names]
        self.relegated_teams = []
        self.promoted_teams = []
        self.challenger_cup_winner = ""
        self.active_cup = "World Cup"
        
        # Challenger Cup bracket states
        self.cc_current_bracket = []
        self.cc_bracket_entrants = []
        self.cc_lcp_bracket = []
        self.cc_lcp_entrants = []
        
        # Knockout result details
        self.knockout_results = {
            "ROUND OF 16": [],
            "QUARTER FINALS": [],
            "SEMI FINALS": [],
            "FINAL": []
        }
        self.cc_knockout_results = {
            "CHALLENGER QF": [],
            "CHALLENGER SF": [],
            "LCP SEMI": [],
            "CHALLENGER FINAL": [],
            "LCP FINAL": []
        }
        
        # Cached WC details for end-of-season archiving
        self.archive_wc_standings = []
        self.archive_wc_bracket = []
        self.archive_wc_fixtures = []
        self.archive_wc_champ = ""
        self.archive_wc_results = {}
        
        # Persistent metrics
        self.paths = {a['name']: ["Group Stage"] for a in self.algos}
        self.total_sorted_rounds = {a['name']: 0 for a in self.algos}
        self.total_sorted_time_ns = {a['name']: 0 for a in self.algos}
        self.fastest_round_ns = 999999999999
        self.fastest_round_algo = ""
        self.lowest_ops_round_val = 999999999999
        self.lowest_ops_round_algo = ""
        self.giant_kills = []

        try:
            import sqlite3
            import database
            conn = sqlite3.connect(database.DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'year'")
            row = cursor.fetchone()
            if row:
                self.year = int(row[0])
            conn.close()
        except Exception:
            pass
        
        # Load ratings
        import database
        saved_elos = database.get_elo_ratings()
        for a in self.algos:
            a['elo'] = saved_elos.get(a['name'], 1500.0)
            a['tournament_elo_diff'] = 0.0
            
        self.draw_groups(animated=False)

    def find_algo_idx_by_name(self, name):
        for idx, a in enumerate(self.algos):
            if a['name'] == name:
                return idx
        return -1

    def get_decorated_algo_names(self):
        names = []
        for a in self.algos:
            name = a['name']
            if a.get('debut_year') == self.year:
                names.append(f"{name} (NEW)")
            else:
                names.append(name)
        return names

    def draw_groups(self, animated=True):
        # Filter indices to only WC teams
        wc_indices = [self.find_algo_idx_by_name(name) for name in self.wc_teams]
        # Sort indices based on current ELO ratings
        sorted_indices = sorted(wc_indices, key=lambda i: self.algos[i].get('elo', 1500.0), reverse=True)
        potA = sorted_indices[0:8]
        potB = sorted_indices[8:16]
        potC = sorted_indices[16:24]
        potD = sorted_indices[24:32]
        
        # Shuffle each pot separately
        self.rng.shuffle(potA)
        self.rng.shuffle(potB)
        self.rng.shuffle(potC)
        self.rng.shuffle(potD)
        
        self.groups = [[] for _ in range(8)]
        self.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0, 'ko_played': 0, 'ko_points': 0, 'ko_matchWins': 0, 'ko_matchLosses': 0, 'ko_roundWins': 0, 'ko_roundLosses': 0, 'ko_ns': 0} for i in range(len(self.algos))]
        
        import terminal_ui
        import database
        
        if animated:
            terminal_ui.clear_screen()
            print(terminal_ui.draw_trophy_header("GROUP DRAW"))
            print("\n  Preparing the lottery. 32 algorithms drawn from 4 seeded pots...")
            time.sleep(1.0)
            
        pots = [potA, potB, potC, potD]
        for pot_idx in range(4):
            current_pot = pots[pot_idx]
            if animated:
                terminal_ui.clear_screen()
                print(terminal_ui.draw_trophy_header(f"GROUP DRAW - POT {pot_idx + 1}"))
                terminal_ui.render_group_draw(self.groups, self.get_decorated_algo_names(), opening_pot=pot_idx, num_groups=8)
                time.sleep(1.0)
                
            for g in range(8):
                idx = current_pot[g]
                self.groups[g].append(idx)
                self.standings[idx]['group'] = g
                
                # Increment group appearance in database (only done when animated, i.e., start of new tournament)
                if animated:
                    database.update_historical_stats(self.algos[idx]['name'], group_stage_inc=1)
                
                if animated:
                    terminal_ui.render_group_draw(self.groups, self.get_decorated_algo_names(), highlighted_group=g, opening_pot=pot_idx, num_groups=8)
                    time.sleep(0.15)
                    
        self.build_schedule()

    def draw_challenger_groups(self, animated=True):
        # Challenger Cup teams: relegated_teams + challenger_teams
        cc_names = list(self.relegated_teams) + list(self.challenger_teams)
        cc_indices = [self.find_algo_idx_by_name(name) for name in cc_names if name]
        # Sort them by ELO
        sorted_cc_indices = sorted(cc_indices, key=lambda i: self.algos[i].get('elo', 1500.0), reverse=True)
        
        potA = sorted_cc_indices[0:4]
        potB = sorted_cc_indices[4:8]
        potC = sorted_cc_indices[8:12]
        potD = sorted_cc_indices[12:16]
        
        self.rng.shuffle(potA)
        self.rng.shuffle(potB)
        self.rng.shuffle(potC)
        self.rng.shuffle(potD)
        
        self.groups = [[] for _ in range(4)]
        self.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0, 'ko_played': 0, 'ko_points': 0, 'ko_matchWins': 0, 'ko_matchLosses': 0, 'ko_roundWins': 0, 'ko_roundLosses': 0, 'ko_ns': 0} for i in range(len(self.algos))]
        
        import terminal_ui
        import database
        
        if animated:
            terminal_ui.clear_screen()
            print(terminal_ui.draw_trophy_header("CHALLENGER CUP DRAW"))
            print("\n  Preparing the lottery. 16 challenger algorithms drawn from 4 seeded pots...")
            time.sleep(1.0)
            
        pots = [potA, potB, potC, potD]
        for pot_idx in range(4):
            current_pot = pots[pot_idx]
            if animated:
                terminal_ui.clear_screen()
                print(terminal_ui.draw_trophy_header(f"CHALLENGER DRAW - POT {pot_idx + 1}"))
                terminal_ui.render_group_draw(self.groups, self.get_decorated_algo_names(), opening_pot=pot_idx, num_groups=4)
                time.sleep(1.0)
                
            for g in range(4):
                idx = current_pot[g]
                self.groups[g].append(idx)
                self.standings[idx]['group'] = g
                
                # Increment group appearance in database (only done when animated, i.e., start of new tournament)
                if animated:
                    database.update_historical_stats(self.algos[idx]['name'], group_stage_inc=1)
                
                if animated:
                    terminal_ui.render_group_draw(self.groups, self.get_decorated_algo_names(), highlighted_group=g, opening_pot=pot_idx, num_groups=4)
                    time.sleep(0.15)
                    
        self.build_schedule()

    def build_schedule(self):
        self.fixtures = []
        pairs = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
        num_groups = len(self.groups)
        active_groups = [g for g in range(num_groups) if len(self.groups[g]) == 4]
        for round_idx in range(6):
            for g in active_groups:
                g1, g2 = pairs[round_idx]
                self.fixtures.append({
                    'group': g,
                    'a': self.groups[g][g1],
                    'b': self.groups[g][g2]
                })

    def challenger_qualified(self):
        q = []
        for g in range(4):
            group_stands = [s for s in self.standings if s['group'] == g]
            group_stands.sort(key=lambda x: (
                -x['points'],
                -x['matchWins'],
                -(x['roundWins'] - x['roundLosses']),
                x['ns']
            ))
            q.append((g, 0, group_stands[0]['algo']))
            q.append((g, 1, group_stands[1]['algo']))
            
        def find_algo(g, rank):
            for item in q:
                if item[0] == g and item[1] == rank:
                    return item[2]
            return -1
            
        bracket = [
            find_algo(0, 0), find_algo(1, 1), # A1 vs B2
            find_algo(1, 0), find_algo(0, 1), # B1 vs A2
            find_algo(2, 0), find_algo(3, 1), # C1 vs D2
            find_algo(3, 0), find_algo(2, 1)  # D1 vs C2
        ]
        return bracket

    def play_group_stage(self):
        if self.current_stage not in ["Group Stage", "Challenger Group Stage"]:
            return
        import terminal_ui
        import database
        
        terminal_ui.clear_screen()
        start_idx = getattr(self, 'next_fixture_idx', 0)
        
        for idx in range(start_idx, len(self.fixtures)):
            f = self.fixtures[idx]
            terminal_ui.clear_screen()
            print(terminal_ui.draw_simple_header(f"MATCH DAY - MATCH {idx + 1} / {len(self.fixtures)}"))
            
            box_lines = [
                f" Group {chr(ord('A') + f['group'])} Showcase Duel:",
                "",
                f"   {BOLD}{CYAN}{self.algos[f['a']]['name']}{RESET}",
                f"        {BOLD}{FG_MUTED}VS{RESET}",
                f"   {BOLD}{VIOLET}{self.algos[f['b']]['name']}{RESET}",
                ""
            ]
            print(terminal_ui.draw_box("CONCURRENT RUN", box_lines, width=76, color=GREEN))
            time.sleep(0.7)
            
            actual_size = self.array_size
            display_size = None
            if actual_size > 10000000:
                display_size = actual_size
                actual_size = 2000000
 
            res = play_match(
                self.algos[f['a']],
                self.algos[f['b']],
                f"Group {chr(ord('A') + f['group'])} Match {idx + 1} / {len(self.fixtures)}",
                self.rng,
                'group',
                actual_size,
                self.visual_delay,
                self.group_timeout,
                group_id=f['group'],
                standings=self.standings,
                algo_names=self.get_decorated_algo_names(),
                display_size=display_size,
                algo_list=self.algos,
                tournament=self
            )
            
            sa = self.standings[f['a']]
            sb = self.standings[f['b']]
            
            sa['played'] += 1
            sb['played'] += 1
            sa['roundWins'] += res.winsA
            sa['roundLosses'] += res.winsB
            sb['roundWins'] += res.winsB
            sb['roundLosses'] += res.winsA
            sa['ns'] += res.nsA
            sb['ns'] += res.nsB
            
            if res.tie:
                sa['points'] += 1
                sb['points'] += 1
                sa['matchDraws'] += 1
                sb['matchDraws'] += 1
            elif res.winner == 0:
                sa['points'] += 3
                sa['matchWins'] += 1
                sb['matchLosses'] += 1
            else:
                sb['points'] += 3
                sb['matchWins'] += 1
                sa['matchLosses'] += 1
            
            self.next_fixture_idx = idx + 1
            database.save_tournament(self)
                
        # Group stage complete
        if self.active_cup == "World Cup":
            self.current_stage = "ROUND OF 16"
            self.current_bracket = self.qualified()
            self.bracket_entrants = list(self.current_bracket)
            for algo_idx in self.current_bracket:
                database.update_historical_stats(self.algos[algo_idx]['name'], r16_inc=1)
        else:
            self.current_stage = "CHALLENGER QF"
            self.cc_current_bracket = self.challenger_qualified()
            self.cc_bracket_entrants = list(self.cc_current_bracket)
            self.cc_lcp_bracket = []
            self.cc_lcp_entrants = []
            for algo_idx in self.cc_current_bracket:
                database.update_historical_stats(self.algos[algo_idx]['name'], qf_inc=1)
            
        database.save_tournament(self)
 
        if getattr(self, 'autoplay', False):
            if self.active_cup == "World Cup":
                terminal_ui.render_standings_view(self.standings, self.get_decorated_algo_names(), page=0)
                time.sleep(2.0)
                terminal_ui.render_standings_view(self.standings, self.get_decorated_algo_names(), page=1)
                time.sleep(2.0)
            else:
                terminal_ui.render_standings_view(self.standings, self.get_decorated_algo_names(), page=0, num_groups=4)
                time.sleep(2.0)
        else:
            page = 0
            while True:
                terminal_ui.render_standings_view(self.standings, self.get_decorated_algo_names(), page=page, num_groups=(4 if self.active_cup == "Challenger Cup" else 8))
                k = terminal_ui.read_key(block=True)
                if k == 'enter':
                    break
                elif (k == 'left' or k == 'h') and self.active_cup == "World Cup":
                    page = 0
                elif (k == 'right' or k == 'l') and self.active_cup == "World Cup":
                    page = 1

    def qualified(self):
        q = []
        for g in range(8):
            group_stands = [s for s in self.standings if s['group'] == g]
            group_stands.sort(key=lambda x: (
                -x['points'],
                -x['matchWins'],
                -(x['roundWins'] - x['roundLosses']),
                x['ns']
            ))
            q.append((g, 0, group_stands[0]['algo']))
            q.append((g, 1, group_stands[1]['algo']))
            
        bracket = []
        def find_algo(g, rank):
            for item in q:
                if item[0] == g and item[1] == rank:
                    return item[2]
            return -1
            
        pairings = [
            (0, 1), # A1 vs B2
            (2, 3), # C1 vs D2
            (4, 5), # E1 vs F2
            (6, 7), # G1 vs H2
            (1, 0), # B1 vs A2
            (3, 2), # D1 vs C2
            (5, 4), # F1 vs E2
            (7, 6)  # H1 vs G2
        ]
        
        for g_first, g_sec in pairings:
            bracket.append(find_algo(g_first, 0))
            bracket.append(find_algo(g_sec, 1))
            
        return bracket

    def play_knockouts(self):
        if getattr(self, "active_cup", "World Cup") == "Challenger Cup":
            self.play_challenger_knockouts()
            return

        import terminal_ui
        import database
        
        stages = ["ROUND OF 16", "QUARTER FINALS", "SEMI FINALS", "FINAL"]
        
        if self.current_stage == "Finished":
            if self.current_bracket:
                champ_name = self.algos[self.current_bracket[0]]['name']
                self.show_awards_and_champion(champ_name)
            return
            
        if not self.current_bracket:
            self.current_bracket = self.qualified()
            self.bracket_entrants = list(self.current_bracket)
            for algo_idx in self.current_bracket:
                database.update_historical_stats(self.algos[algo_idx]['name'], r16_inc=1)
            database.save_tournament(self)
            
        start_stage_idx = 0
        if self.current_stage in stages:
            start_stage_idx = stages.index(self.current_stage)
            
        entrants = list(self.current_bracket)
        
        for stage_idx in range(start_stage_idx, len(stages)):
            stage = stages[stage_idx]
            self.current_stage = stage
            self.current_bracket = list(entrants)
            
            database.save_tournament(self)
            
            bracket_data = {
                "wc": list(self.bracket_entrants),
                "wc_results": getattr(self, "knockout_results", {})
            }
            if stage == "ROUND OF 16":
                default_page = 0
            elif stage == "QUARTER FINALS":
                default_page = 1
            else:
                default_page = 2
                
            if getattr(self, 'autoplay', False):
                terminal_ui.render_bracket_view(bracket_data, stage, self.get_decorated_algo_names(), page=default_page)
                time.sleep(2.0)
            else:
                page = default_page
                while True:
                    terminal_ui.render_bracket_view(bracket_data, stage, self.get_decorated_algo_names(), page=page)
                    print("\n  Use ← / → Arrows to browse bracket. Press Enter to start this knockout stage...")
                    k = terminal_ui.read_key(block=True)
                    if k == 'enter':
                        break
                    elif k == 'left' or k == 'h':
                        page = max(0, page - 1)
                    elif k == 'right' or k == 'l':
                        page = min(2, page + 1)
            
            winners = []
            stage_scores = []
            for i in range(0, len(entrants), 2):
                a = entrants[i]
                b = entrants[i + 1]
                
                terminal_ui.clear_screen()
                print(terminal_ui.draw_simple_header(f"{stage} MATCH"))
                
                box_lines = [
                    f" Knockout Duel - Stage: {stage}",
                    "",
                    f"   {BOLD}{CYAN}{self.algos[a]['name']}{RESET}",
                    f"        {BOLD}{FG_MUTED}VS{RESET}",
                    f"   {BOLD}{VIOLET}{self.algos[b]['name']}{RESET}",
                    "",
                    " Single-elimination: first sorted finish terminates opponent immediately."
                ]
                print(terminal_ui.draw_box("KNOCKOUT LIVE", box_lines, width=76, color=VIOLET))
                time.sleep(0.7)
                
                if stage == "FINAL":
                    actual_size = self.final_size
                else:
                    actual_size = self.knockouts_size
                
                if actual_size > 10000000:
                    display_size = actual_size
                    actual_size = 2000000
                else:
                    display_size = None
                
                stage_timeout = self.final_timeout if stage == "FINAL" else self.ko_timeout
                res = play_match(
                    self.algos[a],
                    self.algos[b],
                    stage,
                    self.rng,
                    'knockout',
                    actual_size,
                    self.visual_delay,
                    stage_timeout,
                    group_id=None,
                    standings=self.standings,
                    algo_names=self.get_decorated_algo_names(),
                    bracket=entrants,
                    current_match_idx=i // 2,
                    stage_winners=winners,
                    display_size=display_size,
                    stage_scores=stage_scores,
                    algo_list=self.algos,
                    tournament=self
                )

                winner_idx = a if res.winner == 0 else b
                loser_idx = b if res.winner == 0 else a
                winners.append(winner_idx)
                
                if stage == "FINAL":
                    runner_up_idx = loser_idx
                
                # Update standings for the consolidated points table to count knockouts
                sa = self.standings[a]
                sb = self.standings[b]
                sa['ko_played'] += 1
                sb['ko_played'] += 1
                sa['ko_roundWins'] += res.winsA
                sa['ko_roundLosses'] += res.winsB
                sb['ko_roundWins'] += res.winsB
                sb['ko_roundLosses'] += res.winsA
                sa['ko_ns'] += res.nsA
                sb['ko_ns'] += res.nsB
                
                if res.winner == 0:
                    sa['ko_points'] += 3
                    sa['ko_matchWins'] += 1
                    sb['ko_matchLosses'] += 1
                else:
                    sb['ko_points'] += 3
                    sb['ko_matchWins'] += 1
                    sa['ko_matchLosses'] += 1
                
                # Record result detail
                match_result_dict = {
                    "algoA": self.algos[a]['name'],
                    "algoB": self.algos[b]['name'],
                    "winsA": res.winsA,
                    "winsB": res.winsB,
                    "winner": self.algos[winner_idx]['name'],
                    "loser": self.algos[loser_idx]['name']
                }
                if not hasattr(self, 'knockout_results') or self.knockout_results is None:
                    self.knockout_results = {"ROUND OF 16": [], "QUARTER FINALS": [], "SEMI FINALS": [], "FINAL": []}
                if stage not in self.knockout_results:
                    self.knockout_results[stage] = []
                self.knockout_results[stage].append(match_result_dict)

                # Save tournament state after every match to update stats/ELO tables immediately
                database.save_tournament(self)
                
                # Record path updates
                self.paths[self.algos[winner_idx]['name']].append(f"{stage} def {self.algos[loser_idx]['name']}")
                self.paths[self.algos[loser_idx]['name']].append(f"{stage} lost to {self.algos[winner_idx]['name']}")

                # Log detailed match results for historical stats in database
                winner_name = self.algos[winner_idx]['name']
                loser_name = self.algos[loser_idx]['name']
                score_winner = f"{res.winsA if res.winner == 0 else res.winsB}-{res.winsB if res.winner == 0 else res.winsA}"
                score_loser = f"{res.winsB if res.winner == 0 else res.winsA}-{res.winsA if res.winner == 0 else res.winsB}"
                
                if stage == "ROUND OF 16":
                    database.update_historical_stats(winner_name, r16_result={"year": self.year, "opponent": loser_name, "score": score_winner, "result": "won"})
                    database.update_historical_stats(loser_name, r16_result={"year": self.year, "opponent": winner_name, "score": score_loser, "result": "lost"})
                elif stage == "QUARTER FINALS":
                    database.update_historical_stats(winner_name, qf_result={"year": self.year, "opponent": loser_name, "score": score_winner, "result": "won"})
                    database.update_historical_stats(loser_name, qf_result={"year": self.year, "opponent": winner_name, "score": score_loser, "result": "lost"})
                elif stage == "SEMI FINALS":
                    database.update_historical_stats(winner_name, sf_result={"year": self.year, "opponent": loser_name, "score": score_winner, "result": "won"})
                    database.update_historical_stats(loser_name, sf_result={"year": self.year, "opponent": winner_name, "score": score_loser, "result": "lost"})

            entrants = winners
            self.current_bracket = list(entrants)
            
            if stage == "ROUND OF 16":
                self.current_stage = "QUARTER FINALS"
                # Save QF apps for the winners
                for algo_idx in entrants:
                    database.update_historical_stats(self.algos[algo_idx]['name'], qf_inc=1)
            elif stage == "QUARTER FINALS":
                self.current_stage = "SEMI FINALS"
                # Save SF apps for the winners
                for algo_idx in entrants:
                    database.update_historical_stats(self.algos[algo_idx]['name'], sf_inc=1)
            elif stage == "SEMI FINALS":
                self.current_stage = "FINAL"
            elif stage == "FINAL":
                self.current_stage = "Finished"
                
            database.save_tournament(self)
            
        champ_name = self.algos[entrants[0]]['name']
        runner_up_name = self.algos[runner_up_idx]['name']
        self.current_stage = "Finished"
        
        # Record championship and runner-up details in Database / Hall of Fame
        database.update_historical_stats(champ_name, championship_inc=1, championship_year=self.year)
        database.update_historical_stats(runner_up_name, runner_up_inc=1, runner_up_year=self.year)
        
        # Calculate record string
        champ_idx = entrants[0]
        st_champ = self.standings[champ_idx]
        ko_wins = 4
        total_wins = st_champ['matchWins'] + ko_wins
        total_losses = st_champ['matchLosses']
        total_draws = st_champ['matchDraws']
        record_str = f"{total_wins}W-{total_losses}L-{total_draws}D"
        
        avg_finish = 0.0
        if self.total_sorted_rounds[champ_name] > 0:
            avg_finish = (self.total_sorted_time_ns[champ_name] / self.total_sorted_rounds[champ_name]) / 1e9
            
        path_str = " -> ".join(self.paths[champ_name])
        
        # Add to Hall of Fame
        database.add_hall_of_fame_entry(champ_name, self.year, record_str, avg_finish, path_str)
        
        database.save_tournament(self)
        self.show_awards_and_champion(champ_name)
        
        self.reset_season(champ_name)

    def reset_season(self, champ_name="None"):
        import database
        # 1. Cache World Cup results
        self.archive_wc_standings = list(self.standings)
        self.archive_wc_bracket = list(self.bracket_entrants)
        self.archive_wc_fixtures = list(self.fixtures)
        self.archive_wc_champ = champ_name
        self.archive_wc_results = dict(self.knockout_results) if hasattr(self, 'knockout_results') and self.knockout_results else {}
        
        # 2. Determine relegation: Rank all 32 World Cup teams using current season consolidated standings
        current_list = []
        for s in self.standings:
            name = self.algos[s['algo']]['name']
            if name in self.wc_teams:
                played = s['played'] + s.get('ko_played', 0)
                points = s['points'] + s.get('ko_points', 0)
                wins = s['matchWins'] + s.get('ko_matchWins', 0)
                draws = s['matchDraws']
                losses = s['matchLosses'] + s.get('ko_matchLosses', 0)
                r_wins = s['roundWins'] + s.get('ko_roundWins', 0)
                r_losses = s['roundLosses'] + s.get('ko_roundLosses', 0)
                ns = s['ns'] + s.get('ko_ns', 0)
                current_list.append({
                    'name': name,
                    'points': points,
                    'matchWins': wins,
                    'roundWins': r_wins,
                    'roundLosses': r_losses,
                    'ns': ns
                })
        current_list.sort(key=lambda x: (
            -x['points'],
            -x['matchWins'],
            -(x['roundWins'] - x['roundLosses']),
            x['ns']
        ))
        
        relegated_objs = current_list[24:32]
        self.relegated_teams = [obj['name'] for obj in relegated_objs]
        
        retained_objs = current_list[0:24]
        self.wc_teams = [obj['name'] for obj in retained_objs]
        
        # 3. Transition to Challenger Cup
        self.active_cup = "Challenger Cup"
        self.current_stage = "Challenger Group Stage"
        self.next_fixture_idx = 0
        self.cc_current_bracket = []
        self.cc_bracket_entrants = []
        self.cc_lcp_bracket = []
        self.cc_lcp_entrants = []
        
        self.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0, 'ko_played': 0, 'ko_points': 0, 'ko_matchWins': 0, 'ko_matchLosses': 0, 'ko_roundWins': 0, 'ko_roundLosses': 0, 'ko_ns': 0} for i in range(len(self.algos))]
        self.groups = [[] for _ in range(4)]
        self.fixtures = []
        
        database.delete_saved_tournament()
        database.save_tournament(self)
        self.draw_challenger_groups(animated=False)
        database.save_tournament(self)

    def play_challenger_knockouts(self):
        import terminal_ui
        import database
        
        stages = ["CHALLENGER QF", "CHALLENGER SF", "LCP SEMI", "CHALLENGER FINAL", "LCP FINAL"]
        
        if self.current_stage == "Challenger Finished":
            if self.challenger_cup_winner:
                self.show_challenger_awards_and_champion(self.challenger_cup_winner)
            return
            
        if self.current_stage not in stages:
            self.current_stage = "CHALLENGER QF"
            self.cc_current_bracket = self.challenger_qualified()
            self.cc_bracket_entrants = list(self.cc_current_bracket)
            self.cc_lcp_bracket = []
            self.cc_lcp_entrants = []
            for algo_idx in self.cc_current_bracket:
                database.update_historical_stats(self.algos[algo_idx]['name'], qf_inc=1)
            database.save_tournament(self)

        start_stage_idx = stages.index(self.current_stage)
        
        for stage_idx in range(start_stage_idx, len(stages)):
            stage = stages[stage_idx]
            self.current_stage = stage
            database.save_tournament(self)
            
            if stage in ["CHALLENGER QF", "CHALLENGER SF", "CHALLENGER FINAL"]:
                entrants = list(self.cc_current_bracket)
            else:
                entrants = list(self.cc_lcp_bracket)
                
            if not entrants:
                continue
                
            cc_bracket_data = {
                "cc_main": list(self.cc_bracket_entrants),
                "cc_lcp": list(self.cc_lcp_entrants),
                "cc_results": getattr(self, "cc_knockout_results", {})
            }
            
            if stage == "CHALLENGER QF":
                default_page = 0
            elif stage in ["CHALLENGER SF", "CHALLENGER FINAL"]:
                default_page = 1
            else:
                default_page = 2
                
            if getattr(self, 'autoplay', False):
                terminal_ui.render_challenger_bracket_view(cc_bracket_data, stage, self.get_decorated_algo_names(), page=default_page)
                time.sleep(2.0)
            else:
                page = default_page
                while True:
                    terminal_ui.render_challenger_bracket_view(cc_bracket_data, stage, self.get_decorated_algo_names(), page=page)
                    print(f"\n  Use ← / → Arrows to browse bracket. Press Enter to start {stage} stage...")
                    k = terminal_ui.read_key(block=True)
                    if k == 'enter':
                        break
                    elif k == 'left' or k == 'h':
                        page = max(0, page - 1)
                    elif k == 'right' or k == 'l':
                        page = min(2, page + 1)
                        
            winners = []
            losers = []
            stage_scores = []
            
            for i in range(0, len(entrants), 2):
                a = entrants[i]
                b = entrants[i + 1]
                
                terminal_ui.clear_screen()
                print(terminal_ui.draw_simple_header(f"{stage} MATCH"))
                
                box_lines = [
                    f" Challenger Duel - Stage: {stage}",
                    "",
                    f"   {BOLD}{CYAN}{self.algos[a]['name']}{RESET}",
                    f"        {BOLD}{FG_MUTED}VS{RESET}",
                    f"   {BOLD}{VIOLET}{self.algos[b]['name']}{RESET}",
                    "",
                    " Single-elimination: first sorted finish wins."
                ]
                print(terminal_ui.draw_box("KNOCKOUT LIVE", box_lines, width=76, color=VIOLET))
                time.sleep(0.7)
                
                if stage in ["CHALLENGER FINAL", "LCP FINAL"]:
                    actual_size = self.final_size
                else:
                    actual_size = self.knockouts_size
                    
                if actual_size > 10000000:
                    display_size = actual_size
                    actual_size = 2000000
                else:
                    display_size = None
                    
                stage_timeout = self.final_timeout if stage in ["CHALLENGER FINAL", "LCP FINAL"] else self.ko_timeout
                
                res = play_match(
                    self.algos[a],
                    self.algos[b],
                    stage,
                    self.rng,
                    'knockout',
                    actual_size,
                    self.visual_delay,
                    stage_timeout,
                    group_id=None,
                    standings=self.standings,
                    algo_names=self.get_decorated_algo_names(),
                    bracket=entrants,
                    current_match_idx=i // 2,
                    stage_winners=winners,
                    display_size=display_size,
                    stage_scores=stage_scores,
                    algo_list=self.algos,
                    tournament=self
                )
                
                winner_idx = a if res.winner == 0 else b
                loser_idx = b if res.winner == 0 else a
                winners.append(winner_idx)
                losers.append(loser_idx)
                
                sa = self.standings[a]
                sb = self.standings[b]
                sa['ko_played'] += 1
                sb['ko_played'] += 1
                sa['ko_roundWins'] += res.winsA
                sa['ko_roundLosses'] += res.winsB
                sb['ko_roundWins'] += res.winsB
                sb['ko_roundLosses'] += res.winsA
                sa['ko_ns'] += res.nsA
                sb['ko_ns'] += res.nsB
                if res.winner == 0:
                    sa['ko_points'] += 3
                    sa['ko_matchWins'] += 1
                    sb['ko_matchLosses'] += 1
                else:
                    sb['ko_points'] += 3
                    sb['ko_matchWins'] += 1
                    sa['ko_matchLosses'] += 1
                # Record result detail
                match_result_dict = {
                    "algoA": self.algos[a]['name'],
                    "algoB": self.algos[b]['name'],
                    "winsA": res.winsA,
                    "winsB": res.winsB,
                    "winner": self.algos[winner_idx]['name'],
                    "loser": self.algos[loser_idx]['name']
                }
                if not hasattr(self, 'cc_knockout_results') or self.cc_knockout_results is None:
                    self.cc_knockout_results = {
                        "CHALLENGER QF": [],
                        "CHALLENGER SF": [],
                        "LCP SEMI": [],
                        "CHALLENGER FINAL": [],
                        "LCP FINAL": []
                    }
                if stage not in self.cc_knockout_results:
                    self.cc_knockout_results[stage] = []
                self.cc_knockout_results[stage].append(match_result_dict)

                database.save_tournament(self)
                
                self.paths[self.algos[winner_idx]['name']].append(f"{stage} def {self.algos[loser_idx]['name']}")
                self.paths[self.algos[loser_idx]['name']].append(f"{stage} lost to {self.algos[winner_idx]['name']}")
                
                winner_name = self.algos[winner_idx]['name']
                loser_name = self.algos[loser_idx]['name']
                score_winner = f"{res.winsA if res.winner == 0 else res.winsB}-{res.winsB if res.winner == 0 else res.winsA}"
                score_loser = f"{res.winsB if res.winner == 0 else res.winsA}-{res.winsA if res.winner == 0 else res.winsB}"
                
                if stage == "CHALLENGER QF":
                    database.update_historical_stats(winner_name, qf_result={"year": self.year, "opponent": loser_name, "score": score_winner, "result": "won"})
                    database.update_historical_stats(loser_name, qf_result={"year": self.year, "opponent": winner_name, "score": score_loser, "result": "lost"})
                elif stage == "CHALLENGER SF":
                    database.update_historical_stats(winner_name, sf_result={"year": self.year, "opponent": loser_name, "score": score_winner, "result": "won"})
                    database.update_historical_stats(loser_name, sf_result={"year": self.year, "opponent": winner_name, "score": score_loser, "result": "lost"})
                    
            if stage == "CHALLENGER QF":
                self.cc_current_bracket = list(winners)
                self.cc_lcp_bracket = list(losers)
                self.cc_bracket_entrants = list(winners)
                self.cc_lcp_entrants = list(losers)
                
                self.current_stage = "CHALLENGER SF"
                
                self.promoted_teams = [self.algos[w_idx]['name'] for w_idx in winners]
                
                for algo_idx in self.cc_current_bracket:
                    database.update_historical_stats(self.algos[algo_idx]['name'], sf_inc=1)
                for algo_idx in self.cc_lcp_bracket:
                    database.update_historical_stats(self.algos[algo_idx]['name'], sf_inc=1)
                    
            elif stage == "CHALLENGER SF":
                self.cc_current_bracket = list(winners)
                self.current_stage = "LCP SEMI"
                
            elif stage == "LCP SEMI":
                self.cc_lcp_bracket = list(winners)
                self.current_stage = "CHALLENGER FINAL"
                
                for lcp_ent in entrants:
                    name = self.algos[lcp_ent]['name']
                    if name not in self.promoted_teams:
                        self.promoted_teams.append(name)
                        
            elif stage == "CHALLENGER FINAL":
                champ_idx = winners[0]
                champ_name = self.algos[champ_idx]['name']
                self.challenger_cup_winner = champ_name
                
                self.algos[champ_idx]['elo'] = self.algos[champ_idx].get('elo', 1500.0) + 100.0
                self.algos[champ_idx]['tournament_elo_diff'] = self.algos[champ_idx].get('tournament_elo_diff', 0.0) + 100.0
                database.save_elo_ratings({champ_name: self.algos[champ_idx]['elo']})
                
                self.paths[champ_name].append(f"Won Challenger Cup")
                self.current_stage = "LCP FINAL"
                
            elif stage == "LCP FINAL":
                self.current_stage = "Challenger Finished"
                
            database.save_tournament(self)
            
        self.show_challenger_awards_and_champion(self.challenger_cup_winner)
        self.reset_season_challenger()

    def show_challenger_awards_and_champion(self, champ_name):
        import terminal_ui
        terminal_ui.clear_screen()
        header = terminal_ui.draw_trophy_header("CHALLENGER CUP CHAMPION")
        
        lines = [
            f"   {BOLD}{GOLD}🏆 CHALLENGER CUP CHAMPION: {champ_name} 🏆{RESET}",
            "",
            f"   The winner receives: Automatic World Cup Qualification",
            f"   and a {BOLD}{GREEN}+100 Elo bonus{RESET} for the next season!",
            "",
            f"   {BOLD}PROMOTED TO DIVISION 1 (WORLD CUP):{RESET}",
            f"     " + ", ".join(self.promoted_teams),
            "",
            f"   {BOLD}REMAINING IN DIVISION 2 (CHALLENGER CUP):{RESET}",
            f"     " + ", ".join(self.challenger_teams),
            "",
            "   Press Enter to advance to the next season..."
        ]
        box = terminal_ui.draw_box("CHALLENGER SUMMARY", lines, width=76, color=terminal_ui.GOLD)
        terminal_ui.write_screen(header + "\n" + box)
        while True:
            if terminal_ui.read_key(block=True) == 'enter':
                break

    def reset_season_challenger(self):
        import database
        # Fallback if reset is done before completion of Challenger Cup knockouts
        if not self.promoted_teams:
            try:
                q_indices = self.challenger_qualified()
                self.promoted_teams = [self.algos[i]['name'] for i in q_indices]
            except Exception:
                # Absolute fallback
                self.promoted_teams = list(self.challenger_teams)[:8]
                
        if not self.challenger_cup_winner and self.promoted_teams:
            self.challenger_cup_winner = self.promoted_teams[0]

        # 1. Determine bottom 8 remaining in D2
        all_cc_teams = list(self.relegated_teams) + list(self.challenger_teams)
        self.challenger_teams = [name for name in all_cc_teams if name not in self.promoted_teams]
        
        # 2. Roster WC for next season
        self.wc_teams = list(self.wc_teams) + list(self.promoted_teams)
        
        # 3. Save dual-cup archives
        database.archive_tournament_season(
            self.year,
            self.archive_wc_standings,
            self.archive_wc_bracket,
            self.archive_wc_fixtures,
            self.archive_wc_champ,
            cc_standings=self.standings,
            cc_bracket=self.cc_bracket_entrants if self.cc_bracket_entrants else self.cc_current_bracket,
            cc_fixtures=self.fixtures,
            cc_champ=self.challenger_cup_winner,
            cc_lcp_bracket=self.cc_lcp_bracket,
            wc_results=getattr(self, "archive_wc_results", {}),
            cc_results=getattr(self, "cc_knockout_results", {})
        )
        
        # 4. Increment year and reset
        self.year += 1
        self.active_cup = "World Cup"
        self.current_stage = "Group Stage"
        self.next_fixture_idx = 0
        self.relegated_teams = []
        self.promoted_teams = []
        self.challenger_cup_winner = ""
        
        self.cc_current_bracket = []
        self.cc_bracket_entrants = []
        self.cc_lcp_bracket = []
        self.cc_lcp_entrants = []
        
        self.archive_wc_standings = []
        self.archive_wc_bracket = []
        self.archive_wc_fixtures = []
        self.archive_wc_champ = ""
        self.archive_wc_results = {}
        
        self.knockout_results = {
            "ROUND OF 16": [],
            "QUARTER FINALS": [],
            "SEMI FINALS": [],
            "FINAL": []
        }
        self.cc_knockout_results = {
            "CHALLENGER QF": [],
            "CHALLENGER SF": [],
            "LCP SEMI": [],
            "CHALLENGER FINAL": [],
            "LCP FINAL": []
        }
        
        self.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0, 'ko_played': 0, 'ko_points': 0, 'ko_matchWins': 0, 'ko_matchLosses': 0, 'ko_roundWins': 0, 'ko_roundLosses': 0, 'ko_ns': 0} for i in range(len(self.algos))]
        self.groups = [[] for _ in range(8)]
        self.fixtures = []
        
        database.delete_saved_tournament()
        database.save_tournament(self)
        self.draw_groups(animated=False)
        database.save_tournament(self)


    def show_awards_and_champion(self, champ_name):
        import terminal_ui
        import database
        
        # Find worst performer for Wooden Spoon
        worst_algo = None
        worst_pts = 999
        worst_wins = 999
        worst_diff = 999
        worst_ns = 0
        for s in self.standings:
            pts = s['points']
            wins = s['matchWins']
            diff = s['roundWins'] - s['roundLosses']
            ns = s['ns']
            # Lowest points, then lowest wins, then lowest diff, then highest time
            if (pts < worst_pts or 
                (pts == worst_pts and wins < worst_wins) or 
                (pts == worst_pts and wins == worst_wins and diff < worst_diff) or
                (pts == worst_pts and wins == worst_wins and diff == worst_diff and ns > worst_ns)):
                worst_pts = pts
                worst_wins = wins
                worst_diff = diff
                worst_ns = ns
                worst_algo = self.algos[s['algo']]['name']
                
        # Most memory-efficient (O(1) memory algorithms)
        # Find all O(1) memory and list their inventors
        ram_algos = [a['name'] for a in self.algos if a['memory'] == "O(1)"]
        ram_winner = "Heap Sort / Shell Sort / Bubble / Insertion"
        
        # Giant killer winner
        gk_winner = "None"
        if self.giant_kills:
            # Maximum ELO difference defeat
            best_gk = max(self.giant_kills, key=lambda x: x['elo_diff'])
            gk_winner = f"{best_gk['winner']} (def. {best_gk['loser']} +{best_gk['elo_diff']:.1f} ELO)"
            
        awards = {
            "champion": champ_name,
            "fastest_time": f"{self.fastest_round_ns / 1e9:.6f}s ({self.fastest_round_algo})" if self.fastest_round_algo else "N/A",
            "lowest_ops": f"{self.lowest_ops_round_val:,} ops ({self.lowest_ops_round_algo})" if self.lowest_ops_round_algo else "N/A",
            "ram_winner": ram_winner,
            "gk_winner": gk_winner,
            "wooden_spoon": worst_algo if worst_algo else "N/A"
        }
        
        terminal_ui.render_awards_screen(awards)
        while True:
            if terminal_ui.read_key(block=True) == 'enter':
                break
                
        self.render_champion(champ_name)

    def render_champion(self, name):
        import terminal_ui
        import random
        import time
        
        time.sleep(0.5)
        try:
            import termios
            import sys
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        except Exception:
            pass
        while terminal_ui.read_key(block=False) is not None:
            pass
            
        GOLD = terminal_ui.GOLD
        RESET = terminal_ui.RESET
        BOLD = terminal_ui.BOLD
        GREEN = terminal_ui.GREEN
        RED = terminal_ui.RED
        BLUE = terminal_ui.BLUE
        CYAN = terminal_ui.CYAN
        VIOLET = terminal_ui.VIOLET
        AMBER = terminal_ui.AMBER
        
        cup = [
            "                    .-----.         ",
            "                  .'   __  '.       ",
            "                 /   .'  '.  \\      ",
            "                |   |      |  |     ",
            "                 \\   '.__.'  /      ",
            "                  '.       .'       ",
            "                    )  _  (         ",
            "                   /  ( )  \\        ",
            "                  /  /   \\  \\       ",
            "                 |  |  _  |  |      ",
            "                 |  | ( ) |  |      ",
            "                 |  |  V  |  |      ",
            "                /  /       \\  \\     ",
            "               |  |         |  |    ",
            "               |  |=========|  |    ",
            "               |  |=========|  |    ",
            "              /  /===========\\  \\   ",
            "             |_________________|    ",
            "             |                 |    "
        ]
        
        colors = [RED, GREEN, BLUE, CYAN, VIOLET, AMBER, GOLD]
        particles = []
        frame_count = 0
        
        while True:
            for p in particles:
                p[0] += 1
            particles = [p for p in particles if p[0] < 20]
            
            if random.random() < 0.6:
                particles.append([0, random.randint(0, 7), random.choice(['*', '+', 'o', '•', '★', 'x', '°', '✨']), random.choice(colors)])
            if random.random() < 0.6:
                particles.append([0, random.randint(64, 71), random.choice(['*', '+', 'o', '•', '★', 'x', '°', '✨']), random.choice(colors)])
                
            grid = [[" "] * 72 for _ in range(20)]
            
            for r, line in enumerate(cup):
                pad = (72 - len(line)) // 2
                for col_idx, char in enumerate(line):
                    if (r == 14 or r == 15) and char == "=":
                        grid[r][pad + col_idx] = GREEN + char + RESET
                    else:
                        grid[r][pad + col_idx] = GOLD + char + RESET
                    
            for p in particles:
                row, col, char, color = p
                if 0 <= row < 20 and 0 <= col < 72:
                    grid[row][col] = color + char + RESET
                    
            content = ["".join(row) for row in grid]
            content.append("")
            
            flash_color = colors[frame_count % len(colors)]
            content.append(f" CHAMPION OF THE WORLD: {BOLD}{flash_color}{name.upper()}{RESET}!")
            content.append(" Congratulations to the most optimal sorting engine of 2026!")
            content.append("")
            content.append(" Press Enter to return to Main Menu...")
            
            header = terminal_ui.draw_trophy_header("TOURNAMENT COMPLETE")
            box = terminal_ui.draw_box("🏆 WORLD CUP CHAMPION 🏆", content, width=76, color=GOLD)
            terminal_ui.write_screen(header + "\n" + box)
            
            k = terminal_ui.read_key(block=False)
            if k == 'enter':
                break
                
            frame_count += 1
            time.sleep(0.1)
