import time
import math
import random
import threading
from types import SimpleNamespace
from terminal_ui import RESET, BOLD, CYAN, FG_MUTED, VIOLET, GREEN, GOLD


# Constants
SAMPLE_COUNT = 32 # Sampled count for TUI graph

# Scenario naming
SCENARIO_NAMES = {
    0: "Sorted Array",
    1: "Unsorted Array - Randomized",
    2: "Unsorted Array - Reversed",
    3: "Unsorted Array - one number unsorted",
    4: "Unsorted Array - randomized duplicates"
}

SCENARIO_DESCRIPTIONS = {
    0: "A trap round: already sorted input punishes bad pivot choices and rewards best-case detection.",
    1: "The classic benchmark: values shuffled into a clean random battlefield.",
    2: "Worst-case pressure for many simple sorts: every value starts in the opposite direction.",
    3: "Almost perfect order with one value displaced; adaptive algorithms get a real chance here.",
    4: "Many repeated values: partitioning, stability, and counting-style approaches can shine."
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
    def __init__(self, arr, state, context, visual_delay=0.0, publish_mask=4095):
        self.arr = list(arr)
        self.st = state
        self.context = context
        self.visual_delay = visual_delay
        self.operations = 0
        self.reads = 0
        self.writes = 0
        self.publish_mask = publish_mask
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
        
        with self.st.lock:
            self.st.sample = sample
            self.st.hotA = i
            self.st.hotB = j
            self.st.operations = self.operations
            self.st.reads = self.reads
            self.st.writes = self.writes
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

def std_intro_sort(v):
    a = v.data()
    a.sort()
    for i in range(len(a)):
        v.set(i, a[i])

def std_stable_sort(v):
    a = v.data()
    a.sort()  # Python sort is stable (Timsort)
    for i in range(len(a)):
        v.set(i, a[i])

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

def merge_sort_rec(v, l, r):
    v.check()
    if l >= r:
        return
    m = l + (r - l) // 2
    merge_sort_rec(v, l, m)
    merge_sort_rec(v, m + 1, r)
    merge_range(v, l, m, r)

def merge_sort(v):
    merge_sort_rec(v, 0, v.size() - 1)

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
            x = v.get(i)
            if x < pivot:
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
        b.sort()
        for x in b:
            v.set(k, x)
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
    dummy_context = SortContext(None, None, None)
    tmp = VisualArray(a, dummy_state, dummy_context)
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

def exchange_sort(v):
    n = v.size()
    for i in range(n):
        for j in range(i + 1, n):
            if v.get(i) > v.get(j):
                v.swapAt(i, j)

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

def bead_sort(v):
    n = v.size()
    if n == 0:
        return
    mx = 0
    for i in range(n):
        mx = max(mx, v.get(i))
    beads = [0] * mx
    for i in range(n):
        x = v.get(i)
        for j in range(x):
            v.check()
            beads[j] += 1
    out = [0] * n
    for j in range(mx):
        for i in range(n - beads[j], n):
            out[i] += 1
    for i in range(n):
        v.set(i, out[i])

def stooge_small_rec(v, l, h):
    v.check()
    if l >= h:
        return
    if v.get(l) > v.get(h):
        v.swapAt(l, h)
    if h - l + 1 > 2:
        t = (h - l + 1) // 3
        stooge_small_rec(v, l, h - t)
        stooge_small_rec(v, l + t, h)
        stooge_small_rec(v, l, h - t)

def stooge_sort(v):
    n = v.size()
    if n <= 64:
        stooge_small_rec(v, 0, n - 1)
        return
    for p in range(n):
        v.check()
        step = max(1, n // 3)
        changed = False
        for i in range(p % step, n - step, step):
            if v.get(i) > v.get(i + step):
                v.swapAt(i, i + step)
                changed = True
        if not changed and p > step:
            return

def slow_small_rec(v, i, j):
    v.check()
    if i >= j:
        return
    m = (i + j) // 2
    slow_small_rec(v, i, m)
    slow_small_rec(v, m + 1, j)
    if v.get(j) < v.get(m):
        v.swapAt(j, m)
    slow_small_rec(v, i, j - 1)

def slow_sort(v):
    n = v.size()
    if n <= 32:
        slow_small_rec(v, 0, n - 1)
        return
    window = 2
    while window <= n:
        v.check()
        for i in range(0, n - window + 1, max(1, window // 2)):
            m = i + window // 2
            r = i + window - 1
            if v.get(m) > v.get(r):
                v.swapAt(m, r)
        if window == n:
            break
        window = min(n, window + max(1, window // 8))
    for i in range(1, n):
        v.check()
        if v.get(i - 1) > v.get(i):
            v.swapAt(i - 1, i)

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

def bozo_sort(v):
    rng = random.Random(7654321)
    n = v.size()
    while not visual_is_sorted(v):
        i = rng.randint(0, max(0, n - 1))
        j = rng.randint(0, max(0, n - 1))
        v.swapAt(i, j)

def get_algorithms():
    return [
        {"name": "IntroSort", "sort": std_intro_sort},
        {"name": "Stable Sort", "sort": std_stable_sort},
        {"name": "Merge Sort", "sort": merge_sort},
        {"name": "Quick Sort", "sort": quick_sort},
        {"name": "3-Way Quick Sort", "sort": quick3_sort},
        {"name": "Heap Sort", "sort": heap_sort},
        {"name": "Shell Sort", "sort": shell_sort},
        {"name": "Tim/Natural Merge", "sort": natural_merge_sort},
        {"name": "Counting Sort", "sort": counting_sort},
        {"name": "Radix Sort", "sort": radix_sort},
        {"name": "Bucket Sort", "sort": bucket_sort},
        {"name": "Pigeonhole Sort", "sort": counting_sort}, # same as counting
        {"name": "Tree Sort", "sort": tree_sort},
        {"name": "Tournament Sort", "sort": tournament_sort},
        {"name": "Strand Sort", "sort": strand_sort},
        {"name": "Bitonic Sort", "sort": bitonic_sort},
        {"name": "Insertion Sort", "sort": insertion_sort},
        {"name": "Binary Insertion", "sort": binary_insertion_sort},
        {"name": "Selection Sort", "sort": selection_sort},
        {"name": "Exchange Sort", "sort": exchange_sort},
        {"name": "Cycle Sort", "sort": cycle_sort},
        {"name": "Pancake Sort", "sort": pancake_sort},
        {"name": "Comb Sort", "sort": comb_sort},
        {"name": "Gnome Sort", "sort": gnome_sort},
        {"name": "Bubble Sort", "sort": bubble_sort},
        {"name": "Cocktail Shaker", "sort": cocktail_sort},
        {"name": "Odd-Even Sort", "sort": odd_even_sort},
        {"name": "Bead Sort", "sort": bead_sort},
        {"name": "Stooge Sort", "sort": stooge_sort},
        {"name": "Slow Sort", "sort": slow_sort},
        {"name": "Bogo Sort", "sort": bogo_sort},
        {"name": "Bozo Sort", "sort": bozo_sort},
    ]

# --- Sorter Runner ---

class Accumulator:
    def __init__(self):
        self.value = 0

def run_sorter(algo_fn, input_arr, state, cancel_event, pause_event, paused_ns_accum, visual_delay):
    if visual_delay > 0:
        target = max(1, int(0.033 / visual_delay))
        mask = 1
        while mask < target:
            mask = (mask << 1) | 1
        mask = min(511, mask)  # cap at 511 when animating to ensure smooth updates
    else:
        n = len(input_arr)
        target = max(16383, n // 8)
        mask = 16383
        while mask < target:
            mask = (mask << 1) | 1
        
    context = SortContext(cancel_event, pause_event, paused_ns_accum, mask)
    array = VisualArray(input_arr, state, context, visual_delay, publish_mask=mask)

    
    start_time = time.perf_counter_ns()
    try:
        algo_fn(array)
        end_time = time.perf_counter_ns()
        
        elapsed_ns = (end_time - start_time) - paused_ns_accum.value
        elapsed_ns = max(0, elapsed_ns)
        
        final_values = array.snapshot()
        is_srt = array.sorted()
        
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
        
        with state.lock:
            state.sorted = False
            state.cancelled = True
            state.ns = elapsed_ns
            state.elapsed_ms = elapsed_ns // 1_000_000
            state.final_values = final_values
            state.hotA = -1
            state.hotB = -1
            state.done = True
    except Exception as e:
        # Catch unexpected crashes inside sorting algorithms as failed
        end_time = time.perf_counter_ns()
        elapsed_ns = (end_time - start_time) - paused_ns_accum.value
        elapsed_ns = max(0, elapsed_ns)
        with state.lock:
            state.sorted = False
            state.cancelled = False
            state.ns = elapsed_ns
            state.elapsed_ms = elapsed_ns // 1_000_000
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
    return a

def adjacent_disorder(a):
    bad = 0
    for i in range(1, len(a)):
        if a[i - 1] > a[i]:
            bad += 1
    return bad

# --- Tournament Execution Engine ---

def race(algoA, algoB, input_arr, title, scenario, round_num, mode, array_size, visual_delay, timeout, match_score=None, group_id=None, standings=None, algo_names=None, bracket=None, current_match_idx=None, stage_winners=None):
    timeout = min(30.0, timeout)
    stA = VisualState(algoA['name'])
    stB = VisualState(algoB['name'])
    
    cancelA = threading.Event()
    cancelB = threading.Event()
    
    pauseA = threading.Event()
    pauseB = threading.Event()
    
    paused_nsA = Accumulator()
    paused_nsB = Accumulator()
    
    threadA = threading.Thread(
        target=run_sorter,
        args=(algoA['sort'], input_arr, stA, cancelA, pauseA, paused_nsA, visual_delay)
    )
    threadB = threading.Thread(
        target=run_sorter,
        args=(algoB['sort'], input_arr, stB, cancelB, pauseB, paused_nsB, visual_delay)
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
                
        # Handle timeouts/cancellation
        if mode == 'knockout':
            # Instant elimination when opponent finishes sorted
            if doneA and sortedA and not doneB:
                cancelB.set()
            if doneB and sortedB and not doneA:
                cancelA.set()
            # Timeout (forced termination)
            if elapsed > timeout:
                if not doneA: cancelA.set()
                if not doneB: cancelB.set()
        else:  # group mode
            # 1-second grace period once one finishes sorted
            if doneA and sortedA and not doneB and grace_end is None:
                grace_end = now + 1.0
            if doneB and sortedB and not doneA and grace_end is None:
                grace_end = now + 1.0
                
            if grace_end and now > grace_end:
                if not doneA: cancelA.set()
                if not doneB: cancelB.set()
                
            # Timeout (draw)
            if not sortedA and not sortedB and elapsed > timeout:
                forced_tie = True
                cancelA.set()
                cancelB.set()
                
        # Draw TUI updates at ~30 FPS
        terminal_ui.render_live_race(
            stA, stB, SCENARIO_NAMES[scenario], SCENARIO_DESCRIPTIONS[scenario], round_num, array_size,
            match_score=match_score, group_id=group_id, standings=standings, algo_names=algo_names,
            stage_title=title, bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners
        )
        
        if doneA and doneB:
            break
            
        time.sleep(0.033)
        
    threadA.join()
    threadB.join()
    
    # Final draw state update
    terminal_ui.render_live_race(
        stA, stB, SCENARIO_NAMES[scenario], SCENARIO_DESCRIPTIONS[scenario], round_num, array_size,
        match_score=match_score, group_id=group_id, standings=standings, algo_names=algo_names,
        stage_title=title, bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners
    )

    
    # Analyze outcome
    rr = RaceResult()
    with stA.lock:
        rr.nsA = stA.ns
        rr.sortedA = stA.sorted
        rr.cancelledA = stA.cancelled
        finalA = list(stA.final_values)
    with stB.lock:
        rr.nsB = stB.ns
        rr.sortedB = stB.sorted
        rr.cancelledB = stB.cancelled
        finalB = list(stB.final_values)
        
    if forced_tie and mode == 'group':
        rr.tie = True
        rr.winner_slot = -1
    elif rr.sortedA != rr.sortedB:
        rr.winner_slot = 0 if rr.sortedA else 1
    elif rr.sortedA and rr.sortedB:
        rr.winner_slot = 0 if rr.nsA <= rr.nsB else 1
    else:
        # Tie breaker: adjacent disorder count
        badA = adjacent_disorder(finalA)
        badB = adjacent_disorder(finalB)
        if badA != badB:
            rr.winner_slot = 0 if badA < badB else 1
        else:
            rr.winner_slot = 0 if rr.nsA <= rr.nsB else 1
            
    return rr

def play_match(algoA, algoB, stage_title, rng, mode, array_size, visual_delay, timeout, group_id=None, standings=None, algo_names=None, bracket=None, current_match_idx=None, stage_winners=None):
    scenarios = [0, 1, 2, 3, 4]
    winsA = 0
    winsB = 0
    ties = 0
    match_nsA = 0
    match_nsB = 0
    
    import terminal_ui
    
    for round_num in range(1, 6):
        scenario = scenarios[round_num - 1]
        
        # Prepare inputs
        input_arr = make_input(scenario, array_size, rng)
        
        # Race!
        rr = race(
            algoA, algoB, input_arr, stage_title, scenario, round_num, mode,
            array_size, visual_delay, timeout,
            match_score=(winsA, winsB, ties),
            group_id=group_id, standings=standings, algo_names=algo_names,
            bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners
        )

        
        match_nsA += rr.nsA
        match_nsB += rr.nsB
        
        if rr.tie:
            ties += 1
        elif rr.winner_slot == 0:
            winsA += 1
        else:
            winsB += 1
            
        match_decided = winsA == 3 or winsB == 3 or (round_num == 5 and mode == 'group')
        
        if match_decided:
            terminal_ui.draw_round_result(
                algoA['name'], algoB['name'], rr, winsA, winsB, ties, stage_title,
                group_id=group_id, standings=standings, algo_names=algo_names,
                bracket=bracket, current_match_idx=current_match_idx, stage_winners=stage_winners
            )
            if mode == 'knockout':
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
        
    return result

class Tournament:
    def __init__(self, algos, array_size=100000, visual_delay=0.0, timeout=5):
        self.algos = algos
        self.array_size = array_size
        self.visual_delay = visual_delay
        self.timeout = timeout
        self.rng = random.Random()
        
        self.groups = [[] for _ in range(8)]
        self.fixtures = []
        self.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0} for i in range(len(self.algos))]
        self.current_bracket = []
        self.current_stage = "Group Stage"
        self.next_fixture_idx = 0
        
        # Initial draw
        self.draw_groups(animated=False)


    def draw_groups(self, animated=True):
        ids = list(range(len(self.algos)))
        self.rng.shuffle(ids)
        
        self.groups = [[] for _ in range(8)]
        
        import terminal_ui
        
        if animated:
            terminal_ui.clear_screen()
            print(terminal_ui.draw_trophy_header("GROUP DRAW"))
            print("\n  Preparing the lottery. 32 algorithms, 8 groups, 4 elements each...")
            time.sleep(1.0)
            
        # Pot drawing
        for pot in range(4):
            if animated:
                terminal_ui.clear_screen()
                print(terminal_ui.draw_trophy_header(f"GROUP DRAW - POT {pot + 1}"))
                terminal_ui.render_group_draw(self.groups, [a['name'] for a in self.algos], opening_pot=pot)
                time.sleep(1.0)
                
            for g in range(8):
                idx = ids[pot * 8 + g]
                self.groups[g].append(idx)
                self.standings[idx]['group'] = g
                
                if animated:
                    # Highlight group draw
                    terminal_ui.render_group_draw(self.groups, [a['name'] for a in self.algos], highlighted_group=g, opening_pot=pot)
                    time.sleep(0.15)
                    
        self.build_schedule()

    def build_schedule(self):
        self.fixtures = []
        pairs = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
        for round_idx in range(6):
            for g in range(8):
                g1, g2 = pairs[round_idx]
                self.fixtures.append({
                    'group': g,
                    'a': self.groups[g][g1],
                    'b': self.groups[g][g2]
                })

    def play_group_stage(self):
        import terminal_ui
        terminal_ui.clear_screen()
        
        # Start from next_fixture_idx to support resuming
        start_idx = getattr(self, 'next_fixture_idx', 0)
        
        # Play fixtures
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
            
            # Duel
            res = play_match(
                self.algos[f['a']],
                self.algos[f['b']],
                f"Group {chr(ord('A') + f['group'])} Match {idx + 1} / {len(self.fixtures)}",
                self.rng,
                'group',
                self.array_size,
                self.visual_delay,
                self.timeout,
                group_id=f['group'],
                standings=self.standings,
                algo_names=[a['name'] for a in self.algos]
            )


            
            # Record standings
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
            import database
            database.save_tournament(self)
                
        # Group stage is fully complete
        self.current_stage = "ROUND OF 16"
        import database
        database.save_tournament(self)

        # Display final group tables (interactive, no auto-skip)
        page = 0
        while True:
            terminal_ui.render_standings_view(self.standings, [a['name'] for a in self.algos], page=page)
            k = terminal_ui.read_key(block=True)
            if k == 'enter':
                break
            elif k == 'left' or k == 'h':
                page = 0
            elif k == 'right' or k == 'l':
                page = 1


    def qualified(self):
        """Finds top 2 algorithms from each group."""
        q = []
        for g in range(8):
            group_stands = [s for s in self.standings if s['group'] == g]
            # sort standings for this group
            group_stands.sort(key=lambda x: (
                -x['points'],
                -x['matchWins'],
                -(x['roundWins'] - x['roundLosses']),
                x['ns']
            ))
            q.append((g, 0, group_stands[0]['algo'])) # 1st place
            q.append((g, 1, group_stands[1]['algo'])) # 2nd place
            
        # Draw bracket matches matching C++ qualified() logic
        # Push 1st place A vs 2nd place B, etc.
        # Qualified mappings:
        # A1-B2, C1-D2, E1-F2, G1-H2, B1-A2, D1-C2, F1-E2, H1-G2
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
        import terminal_ui
        
        stages = ["ROUND OF 16", "QUARTER FINALS", "SEMI FINALS", "FINAL"]
        
        if self.current_stage == "Finished":
            if self.current_bracket:
                champ_name = self.algos[self.current_bracket[0]]['name']
                self.render_champion(champ_name)
            return
            
        # If we have no bracket, qualify teams
        if not self.current_bracket:
            self.current_bracket = self.qualified()
            
        # Determine starting stage index
        start_stage_idx = 0
        if self.current_stage in stages:
            start_stage_idx = stages.index(self.current_stage)
            
        entrants = list(self.current_bracket)
        
        for stage_idx in range(start_stage_idx, len(stages)):
            stage = stages[stage_idx]
            self.current_stage = stage
            self.current_bracket = list(entrants)
            
            # Auto-save before each stage
            import database
            database.save_tournament(self)
            
            terminal_ui.render_bracket_view(entrants, stage, [a['name'] for a in self.algos])
            print("\n  Press Enter to start this knockout stage...")
            while True:
                if terminal_ui.read_key(block=True) == 'enter':
                    break
            
            winners = []
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
                
                res = play_match(
                    self.algos[a],
                    self.algos[b],
                    stage,
                    self.rng,
                    'knockout',
                    1000000,
                    self.visual_delay,
                    max(15, self.timeout),
                    group_id=None,
                    standings=self.standings,
                    algo_names=[al['name'] for al in self.algos],
                    bracket=entrants,
                    current_match_idx=i // 2,
                    stage_winners=winners
                )

                winner_idx = a if res.winner == 0 else b
                winners.append(winner_idx)

                
            entrants = winners
            self.current_bracket = list(entrants)
            
        # Final Champion
        champ_name = self.algos[entrants[0]]['name']
        self.current_stage = "Finished"
        import database
        database.save_tournament(self)
        self.render_champion(champ_name)


    def render_champion(self, name):
        import terminal_ui
        import random
        import time
        
        # Access colors from terminal_ui
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
            "                 ___________________________",
            "              .-'                           '-.",
            "             /      SORTING WORLD CUP          \\",
            "            /___________________________________\\",
            "            |                                   |",
            "       _____|                                   |_____",
            "      /     |                                   |     \\",
            "     /      |                                   |      \\",
            "     \\      |                                   |      /",
            "      \\_____|                                   |_____/",
            "            |                                   |",
            "            |___________________________________|",
            "                    \\                 /",
            "                     \\               /",
            "                      \\_____________/",
            "                            | |",
            "                            | |",
            "                         ___| |___",
            "                        /_________\\"
        ]
        
        colors = [RED, GREEN, BLUE, CYAN, VIOLET, AMBER, GOLD]
        particles = []  # format: [row, col, char, color]
        frame_count = 0
        
        while True:
            # Move particles down
            for p in particles:
                p[0] += 1
            # Remove offscreen particles
            particles = [p for p in particles if p[0] < 20]
            
            # Spawn new particles at top (row 0)
            if random.random() < 0.6:
                particles.append([0, random.randint(0, 7), random.choice(['*', '+', 'o', '•', '★', 'x', '°', '✨']), random.choice(colors)])
            if random.random() < 0.6:
                particles.append([0, random.randint(64, 71), random.choice(['*', '+', 'o', '•', '★', 'x', '°', '✨']), random.choice(colors)])
                
            # Create a 20x72 grid
            grid = [[" "] * 72 for _ in range(20)]
            
            # Overlay cup in the center
            for r, line in enumerate(cup):
                pad = (72 - len(line)) // 2
                for col_idx, char in enumerate(line):
                    grid[r][pad + col_idx] = GOLD + char + RESET
                    
            # Overlay particles in margins
            for p in particles:
                row, col, char, color = p
                if 0 <= row < 20 and 0 <= col < 72:
                    grid[row][col] = color + char + RESET
                    
            # Build TUI content
            content = ["".join(row) for row in grid]
            content.append("")
            
            # Flashing champion text
            flash_color = colors[frame_count % len(colors)]
            content.append(f" CHAMPION OF THE WORLD: {BOLD}{flash_color}{name.upper()}{RESET}!")
            content.append(" Congratulations to the most optimal sorting engine of 2026!")
            content.append("")
            content.append(" Press Enter to return to Main Menu...")
            
            # Draw
            header = terminal_ui.draw_trophy_header("TOURNAMENT COMPLETE")
            box = terminal_ui.draw_box("🏆 WORLD CUP CHAMPION 🏆", content, width=76, color=GOLD)
            terminal_ui.write_screen(header + "\n" + box)
            
            # Check key press (non-blocking)
            k = terminal_ui.read_key(block=False)
            if k == 'enter':
                break
                
            frame_count += 1
            time.sleep(0.1)
