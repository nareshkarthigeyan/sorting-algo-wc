#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <numeric>
#include <optional>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using namespace std;
using Clock = chrono::steady_clock;
using Ns = chrono::nanoseconds;

static constexpr int ARRAY_SIZE = 100000;
static constexpr int SAMPLE_COUNT = 48;

struct Cancelled {};

struct VisualState {
    string name;
    vector<int> sample;
    vector<int> finalValues;
    int hotA = -1;
    int hotB = -1;
    bool done = false;
    bool cancelled = false;
    bool sorted = false;
    long long ns = 0;
    long long elapsedMs = 0;
    unsigned long long operations = 0;
    unsigned long long reads = 0;
    unsigned long long writes = 0;
    double orderMeter = 0.0;
    mutable mutex m;
};

struct SortContext {
    atomic<bool>* cancel = nullptr;
    atomic<bool>* pause = nullptr;
    atomic<long long>* pausedNs = nullptr;

    void check() const {
        if (pause && pause->load(memory_order_relaxed)) {
            auto pausedAt = Clock::now();
            while (pause->load(memory_order_relaxed)) {
                if (cancel && cancel->load(memory_order_relaxed)) {
                    throw Cancelled();
                }
                this_thread::sleep_for(chrono::milliseconds(10));
            }
            if (pausedNs) {
                auto waited = chrono::duration_cast<Ns>(Clock::now() - pausedAt).count();
                pausedNs->fetch_add(waited, memory_order_relaxed);
            }
        }
        if (cancel && cancel->load(memory_order_relaxed)) {
            throw Cancelled();
        }
    }
};

class VisualArray {
public:
    VisualArray(vector<int> source, shared_ptr<VisualState> state, SortContext& ctx)
        : a(std::move(source)), st(std::move(state)), context(ctx) {
        publish(-1, -1);
    }

    int size() const { return static_cast<int>(a.size()); }

    int get(int i) {
        context.check();
        ++reads;
        publishMaybe(i, -1);
        return a[i];
    }

    void set(int i, int value) {
        context.check();
        a[i] = value;
        ++writes;
        publishMaybe(i, -1);
    }

    void swapAt(int i, int j) {
        context.check();
        if (i != j) {
            swap(a[i], a[j]);
        }
        writes += 2;
        publishMaybe(i, j);
    }

    vector<int> data() {
        context.check();
        return a;
    }

    vector<int> snapshot() const {
        return a;
    }

    void replaceAll(const vector<int>& next) {
        context.check();
        a = next;
        writes += static_cast<unsigned long long>(a.size());
        publishMaybe(-1, -1, true);
    }

    bool sorted() const {
        return is_sorted(a.begin(), a.end());
    }

    int inversionsCapped(int cap = 1000000) const {
        int inv = 0;
        for (int i = 0; i < size(); ++i) {
            for (int j = i + 1; j < size(); ++j) {
                if (a[i] > a[j] && ++inv >= cap) {
                    return cap;
                }
            }
        }
        return inv;
    }

    void check() const {
        context.check();
    }

private:
    vector<int> a;
    shared_ptr<VisualState> st;
    SortContext& context;
    unsigned long long operations = 0;
    unsigned long long reads = 0;
    unsigned long long writes = 0;

    void publish(int i, int j) {
        vector<int> sample;
        sample.reserve(SAMPLE_COUNT);
        int n = static_cast<int>(a.size());
        if (n > 0) {
            for (int k = 0; k < SAMPLE_COUNT; ++k) {
                int idx = min(n - 1, static_cast<int>((1LL * k * (n - 1)) / max(1, SAMPLE_COUNT - 1)));
                sample.push_back(a[idx]);
            }
        }
        int ordered = 0;
        for (int k = 1; k < static_cast<int>(sample.size()); ++k) {
            if (sample[k - 1] <= sample[k]) ++ordered;
        }
        double meter = sample.size() < 2 ? 100.0 : (100.0 * ordered) / (sample.size() - 1);
        lock_guard<mutex> lock(st->m);
        st->sample = std::move(sample);
        st->hotA = i;
        st->hotB = j;
        st->operations = operations;
        st->reads = reads;
        st->writes = writes;
        st->orderMeter = meter;
    }

    void publishMaybe(int i, int j, bool force = false) {
        ++operations;
        if (force || (operations & 4095ULL) == 0) {
            publish(i, j);
        }
    }
};

using SortFn = function<void(VisualArray&)>;

struct Algorithm {
    string name;
    SortFn sort;
};

static string fmtNs(long long ns) {
    string s = to_string(ns);
    string out;
    int first = static_cast<int>(s.size()) % 3;
    if (first == 0) first = 3;
    for (int i = 0; i < static_cast<int>(s.size()); ++i) {
        if (i && (i - first) % 3 == 0) out += ',';
        out += s[i];
    }
    return out + " ns";
}

static void clearScreen() {
    cout << "\033[H\033[2J";
}

static void sleepMs(int ms) {
    this_thread::sleep_for(chrono::milliseconds(ms));
}

static void waitEnter(const string& prompt = "Press Enter to continue...") {
    cout << "\n" << prompt;
    cout.flush();
    string line;
    getline(cin, line);
}

static void trophyHeader(const string& title) {
    cout << "      ___________        .-=========-.        ___________\n";
    cout << "     '._==_==_=_.'      /             \\      '._=_==_==_.'\n";
    cout << "     .-\\:      /-.     /   SORTING     \\     .-\\      :/-.\n";
    cout << "    | (|:.     |) |   |   WORLD CUP     |   | (|     .:|) |\n";
    cout << "     '-|:.     |-'     \\     2026      /     '-|     .:|-'\n";
    cout << "       \\::.    /        '-=========-'        \\    .::/\n";
    cout << "        '::. .'                               '. .::'\n";
    cout << "          ) (               " << title << "\n";
    cout << "        _.' '._\n";
    cout << "       `\"\"\"\"\"\"\"`\n";
}

static string fmtCount(unsigned long long value) {
    string s = to_string(value);
    string out;
    int first = static_cast<int>(s.size()) % 3;
    if (first == 0) first = 3;
    for (int i = 0; i < static_cast<int>(s.size()); ++i) {
        if (i && (i - first) % 3 == 0) out += ',';
        out += s[i];
    }
    return out;
}

static string fmtMs(long long ms) {
    stringstream ss;
    ss << fixed << setprecision(3) << (ms / 1000.0) << "s";
    return ss.str();
}

static void copyVisual(const VisualState& state,
                       string& name,
                       vector<int>& sample,
                       bool& done,
                       bool& cancelled,
                       bool& sorted,
                       long long& ns,
                       long long& elapsedMs,
                       unsigned long long& operations,
                       unsigned long long& reads,
                       unsigned long long& writes,
                       double& orderMeter) {
    lock_guard<mutex> lock(state.m);
    name = state.name;
    sample = state.sample;
    done = state.done;
    cancelled = state.cancelled;
    sorted = state.sorted;
    ns = state.ns;
    elapsedMs = state.elapsedMs;
    operations = state.operations;
    reads = state.reads;
    writes = state.writes;
    orderMeter = state.orderMeter;
}

static string runnerBrief(const VisualState& state) {
    string name;
    vector<int> sample;
    bool done, cancelled, sorted;
    long long ns, elapsedMs;
    unsigned long long operations, reads, writes;
    double orderMeter;
    copyVisual(state, name, sample, done, cancelled, sorted, ns, elapsedMs, operations, reads, writes, orderMeter);

    string status = done ? (sorted ? "DONE" : (cancelled ? "KILL" : "FAIL")) : "RUN";
    stringstream ss;
    ss << name << " " << status << " "
       << fmtMs(done ? ns / 1000000 : elapsedMs)
       << " " << fixed << setprecision(0) << orderMeter << "%"
       << " ops " << fmtCount(operations);
    return ss.str();
}

static void renderRaceHeader(const string& title,
                             const string& scenario,
                             const string& description,
                             int round) {
    cout << "+==========================================================================+\n";
    cout << "|                         SORTING WORLD CUP LIVE RACE                      |\n";
    cout << "+==========================================================================+\n";
    cout << "| " << left << setw(72) << title.substr(0, 72) << " |\n";
    cout << "| Round " << round << " / 5  |  " << left << setw(48) << scenario.substr(0, 48) << " |\n";
    cout << "| Array size: " << left << setw(61) << fmtCount(ARRAY_SIZE) << " |\n";
    cout << "| " << left << setw(72) << description.substr(0, 72) << " |\n";
    cout << "+==========================================================================+\n\n";
    cout << "Live: ";
    cout.flush();
}

static void renderRaceStatus(const shared_ptr<VisualState>& a,
                             const shared_ptr<VisualState>& b) {
    string line = runnerBrief(*a) + "  ||  " + runnerBrief(*b);
    if (line.size() > 150) line = line.substr(0, 150);
    cout << "\rLive: " << left << setw(150) << line << flush;
}

static void finishRaceStatus() {
    cout << "\n";
}

static int adjacentDisorder(const vector<int>& a) {
    int bad = 0;
    for (int i = 1; i < static_cast<int>(a.size()); ++i) {
        if (a[i - 1] > a[i]) ++bad;
    }
    return bad;
}

static void bubbleSort(VisualArray& v) {
    int n = v.size();
    for (int i = 0; i < n; ++i) {
        bool changed = false;
        for (int j = 0; j + 1 < n - i; ++j) {
            if (v.get(j) > v.get(j + 1)) {
                v.swapAt(j, j + 1);
                changed = true;
            }
        }
        if (!changed) return;
    }
}

static void cocktailSort(VisualArray& v) {
    int start = 0, end = v.size() - 1;
    bool swapped = true;
    while (swapped) {
        swapped = false;
        for (int i = start; i < end; ++i) {
            if (v.get(i) > v.get(i + 1)) {
                v.swapAt(i, i + 1);
                swapped = true;
            }
        }
        if (!swapped) break;
        swapped = false;
        --end;
        for (int i = end - 1; i >= start; --i) {
            if (v.get(i) > v.get(i + 1)) {
                v.swapAt(i, i + 1);
                swapped = true;
            }
        }
        ++start;
    }
}

static void oddEvenSort(VisualArray& v) {
    bool sorted = false;
    int n = v.size();
    while (!sorted) {
        sorted = true;
        for (int i = 1; i + 1 < n; i += 2) {
            if (v.get(i) > v.get(i + 1)) {
                v.swapAt(i, i + 1);
                sorted = false;
            }
        }
        for (int i = 0; i + 1 < n; i += 2) {
            if (v.get(i) > v.get(i + 1)) {
                v.swapAt(i, i + 1);
                sorted = false;
            }
        }
    }
}

static void combSort(VisualArray& v) {
    int n = v.size();
    int gap = n;
    bool swapped = true;
    while (gap != 1 || swapped) {
        gap = max(1, (gap * 10) / 13);
        swapped = false;
        for (int i = 0; i + gap < n; ++i) {
            if (v.get(i) > v.get(i + gap)) {
                v.swapAt(i, i + gap);
                swapped = true;
            }
        }
    }
}

static void gnomeSort(VisualArray& v) {
    int i = 0;
    int n = v.size();
    while (i < n) {
        if (i == 0 || v.get(i - 1) <= v.get(i)) {
            ++i;
        } else {
            v.swapAt(i - 1, i);
            --i;
        }
    }
}

static void selectionSort(VisualArray& v) {
    int n = v.size();
    for (int i = 0; i < n; ++i) {
        int minI = i;
        for (int j = i + 1; j < n; ++j) {
            if (v.get(j) < v.get(minI)) minI = j;
        }
        v.swapAt(i, minI);
    }
}

static void insertionSort(VisualArray& v) {
    int n = v.size();
    for (int i = 1; i < n; ++i) {
        int key = v.get(i);
        int j = i - 1;
        while (j >= 0 && v.get(j) > key) {
            v.set(j + 1, v.get(j));
            --j;
        }
        v.set(j + 1, key);
    }
}

static void binaryInsertionSort(VisualArray& v) {
    int n = v.size();
    for (int i = 1; i < n; ++i) {
        int key = v.get(i);
        int left = 0, right = i;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (key < v.get(mid)) right = mid;
            else left = mid + 1;
        }
        for (int j = i; j > left; --j) {
            v.set(j, v.get(j - 1));
        }
        v.set(left, key);
    }
}

static void exchangeSort(VisualArray& v) {
    int n = v.size();
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            if (v.get(i) > v.get(j)) v.swapAt(i, j);
        }
    }
}

static void shellSort(VisualArray& v) {
    vector<int> gaps = {701, 301, 132, 57, 23, 10, 4, 1};
    int n = v.size();
    for (int gap : gaps) {
        if (gap >= n) continue;
        for (int i = gap; i < n; ++i) {
            int temp = v.get(i);
            int j = i;
            while (j >= gap && v.get(j - gap) > temp) {
                v.set(j, v.get(j - gap));
                j -= gap;
            }
            v.set(j, temp);
        }
    }
}

static void mergeRange(VisualArray& v, int l, int m, int r) {
    vector<int> left, right;
    for (int i = l; i <= m; ++i) left.push_back(v.get(i));
    for (int i = m + 1; i <= r; ++i) right.push_back(v.get(i));
    int i = 0, j = 0, k = l;
    while (i < static_cast<int>(left.size()) && j < static_cast<int>(right.size())) {
        if (left[i] <= right[j]) v.set(k++, left[i++]);
        else v.set(k++, right[j++]);
    }
    while (i < static_cast<int>(left.size())) v.set(k++, left[i++]);
    while (j < static_cast<int>(right.size())) v.set(k++, right[j++]);
}

static void mergeSortRec(VisualArray& v, int l, int r) {
    v.check();
    if (l >= r) return;
    int m = l + (r - l) / 2;
    mergeSortRec(v, l, m);
    mergeSortRec(v, m + 1, r);
    mergeRange(v, l, m, r);
}

static void mergeSort(VisualArray& v) {
    mergeSortRec(v, 0, v.size() - 1);
}

static void naturalMergeSort(VisualArray& v) {
    int n = v.size();
    if (n < 2) return;
    bool done = false;
    while (!done) {
        done = true;
        int l = 0;
        while (l < n) {
            int m = l;
            while (m + 1 < n && v.get(m) <= v.get(m + 1)) ++m;
            if (m == n - 1) break;
            int r = m + 1;
            while (r + 1 < n && v.get(r) <= v.get(r + 1)) ++r;
            mergeRange(v, l, m, r);
            done = false;
            l = r + 1;
        }
    }
}

static void quickSort(VisualArray& v) {
    vector<pair<int, int>> stack;
    stack.push_back({0, v.size() - 1});
    while (!stack.empty()) {
        auto [lo, hi] = stack.back();
        stack.pop_back();
        while (hi - lo > 24) {
            v.check();
            int mid = lo + (hi - lo) / 2;
            if (v.get(mid) < v.get(lo)) v.swapAt(mid, lo);
            if (v.get(hi) < v.get(lo)) v.swapAt(hi, lo);
            if (v.get(hi) < v.get(mid)) v.swapAt(hi, mid);
            int pivot = v.get(mid);
            int i = lo;
            int j = hi;
            while (i <= j) {
                while (v.get(i) < pivot) ++i;
                while (v.get(j) > pivot) --j;
                if (i <= j) v.swapAt(i++, j--);
            }
            if (j - lo < hi - i) {
                if (i < hi) stack.push_back({i, hi});
                hi = j;
            } else {
                if (lo < j) stack.push_back({lo, j});
                lo = i;
            }
        }
        for (int i = lo + 1; i <= hi; ++i) {
            int key = v.get(i);
            int j = i - 1;
            while (j >= lo && v.get(j) > key) {
                v.set(j + 1, v.get(j));
                --j;
            }
            v.set(j + 1, key);
        }
    }
}

static void quick3Sort(VisualArray& v) {
    vector<pair<int, int>> stack;
    stack.push_back({0, v.size() - 1});
    while (!stack.empty()) {
        auto [lo, hi] = stack.back();
        stack.pop_back();
        if (lo >= hi) continue;
        if (hi - lo <= 24) {
            for (int i = lo + 1; i <= hi; ++i) {
                int key = v.get(i);
                int j = i - 1;
                while (j >= lo && v.get(j) > key) {
                    v.set(j + 1, v.get(j));
                    --j;
                }
                v.set(j + 1, key);
            }
            continue;
        }
        int mid = lo + (hi - lo) / 2;
        if (v.get(mid) < v.get(lo)) v.swapAt(mid, lo);
        if (v.get(hi) < v.get(lo)) v.swapAt(hi, lo);
        if (v.get(hi) < v.get(mid)) v.swapAt(hi, mid);
        int pivot = v.get(mid);
        int lt = lo;
        int i = lo;
        int gt = hi;
        while (i <= gt) {
            v.check();
            int x = v.get(i);
            if (x < pivot) v.swapAt(lt++, i++);
            else if (x > pivot) v.swapAt(i, gt--);
            else ++i;
        }
        if (lt - lo > hi - gt) {
            if (lo < lt - 1) stack.push_back({lo, lt - 1});
            if (gt + 1 < hi) stack.push_back({gt + 1, hi});
        } else {
            if (gt + 1 < hi) stack.push_back({gt + 1, hi});
            if (lo < lt - 1) stack.push_back({lo, lt - 1});
        }
    }
}

static void heapify(VisualArray& v, int n, int i) {
    v.check();
    int largest = i;
    int l = 2 * i + 1;
    int r = 2 * i + 2;
    if (l < n && v.get(l) > v.get(largest)) largest = l;
    if (r < n && v.get(r) > v.get(largest)) largest = r;
    if (largest != i) {
        v.swapAt(i, largest);
        heapify(v, n, largest);
    }
}

static void heapSort(VisualArray& v) {
    int n = v.size();
    for (int i = n / 2 - 1; i >= 0; --i) heapify(v, n, i);
    for (int i = n - 1; i > 0; --i) {
        v.swapAt(0, i);
        heapify(v, i, 0);
    }
}

static void stdIntroSort(VisualArray& v) {
    vector<int> a = v.data();
    sort(a.begin(), a.end());
    for (int i = 0; i < static_cast<int>(a.size()); ++i) v.set(i, a[i]);
}

static void stdStableSort(VisualArray& v) {
    vector<int> a = v.data();
    stable_sort(a.begin(), a.end());
    for (int i = 0; i < static_cast<int>(a.size()); ++i) v.set(i, a[i]);
}

static void countingSort(VisualArray& v) {
    int n = v.size();
    int mn = v.get(0), mx = v.get(0);
    for (int i = 1; i < n; ++i) {
        mn = min(mn, v.get(i));
        mx = max(mx, v.get(i));
    }
    vector<int> count(mx - mn + 1, 0);
    for (int i = 0; i < n; ++i) ++count[v.get(i) - mn];
    int k = 0;
    for (int value = mn; value <= mx; ++value) {
        while (count[value - mn]--) v.set(k++, value);
    }
}

static void radixSort(VisualArray& v) {
    int n = v.size();
    int mx = 0;
    for (int i = 0; i < n; ++i) mx = max(mx, v.get(i));
    for (int exp = 1; mx / exp > 0; exp *= 10) {
        vector<int> output(n);
        int count[10] = {0};
        for (int i = 0; i < n; ++i) ++count[(v.get(i) / exp) % 10];
        for (int i = 1; i < 10; ++i) count[i] += count[i - 1];
        for (int i = n - 1; i >= 0; --i) {
            int x = v.get(i);
            output[--count[(x / exp) % 10]] = x;
        }
        for (int i = 0; i < n; ++i) v.set(i, output[i]);
    }
}

static void bucketSort(VisualArray& v) {
    int n = v.size();
    int mn = v.get(0), mx = v.get(0);
    for (int i = 1; i < n; ++i) {
        mn = min(mn, v.get(i));
        mx = max(mx, v.get(i));
    }
    int bucketCount = max(1, static_cast<int>(sqrt(n)));
    vector<vector<int>> buckets(bucketCount);
    int range = max(1, mx - mn + 1);
    for (int i = 0; i < n; ++i) {
        int idx = min(bucketCount - 1, ((v.get(i) - mn) * bucketCount) / range);
        buckets[idx].push_back(v.get(i));
    }
    int k = 0;
    for (auto& bucket : buckets) {
        sort(bucket.begin(), bucket.end());
        for (int x : bucket) v.set(k++, x);
    }
}

static void pigeonholeSort(VisualArray& v) {
    countingSort(v);
}

static void cycleSort(VisualArray& v) {
    int n = v.size();
    for (int cycleStart = 0; cycleStart <= n - 2; ++cycleStart) {
        int item = v.get(cycleStart);
        int pos = cycleStart;
        for (int i = cycleStart + 1; i < n; ++i) {
            if (v.get(i) < item) ++pos;
        }
        if (pos == cycleStart) continue;
        while (pos < n && item == v.get(pos)) ++pos;
        if (pos >= n) continue;
        int temp = v.get(pos);
        v.set(pos, item);
        item = temp;
        while (pos != cycleStart) {
            pos = cycleStart;
            for (int i = cycleStart + 1; i < n; ++i) {
                if (v.get(i) < item) ++pos;
            }
            while (pos < n && item == v.get(pos)) ++pos;
            if (pos >= n) break;
            temp = v.get(pos);
            v.set(pos, item);
            item = temp;
        }
    }
}

static void pancakeSort(VisualArray& v) {
    auto flip = [&](int k) {
        int i = 0;
        while (i < k) v.swapAt(i++, k--);
    };
    for (int curr = v.size(); curr > 1; --curr) {
        int maxI = 0;
        for (int i = 1; i < curr; ++i) {
            if (v.get(i) > v.get(maxI)) maxI = i;
        }
        if (maxI == curr - 1) continue;
        flip(maxI);
        flip(curr - 1);
    }
}

static void strandSort(VisualArray& v) {
    deque<int> input;
    for (int i = 0; i < v.size(); ++i) input.push_back(v.get(i));
    vector<int> output;
    while (!input.empty()) {
        v.check();
        vector<int> strand;
        strand.push_back(input.front());
        input.pop_front();
        for (auto it = input.begin(); it != input.end();) {
            v.check();
            if (*it >= strand.back()) {
                strand.push_back(*it);
                it = input.erase(it);
            } else {
                ++it;
            }
        }
        vector<int> merged;
        merge(output.begin(), output.end(), strand.begin(), strand.end(), back_inserter(merged));
        output.swap(merged);
        for (int i = 0; i < static_cast<int>(output.size()); ++i) v.set(i, output[i]);
    }
}

static void treeSort(VisualArray& v) {
    multiset<int> tree;
    int n = v.size();
    for (int i = 0; i < n; ++i) {
        v.check();
        tree.insert(v.get(i));
    }
    int k = 0;
    for (int x : tree) v.set(k++, x);
}

static void bitonicMerge(VisualArray& v, int low, int count, bool up) {
    v.check();
    if (count <= 1) return;
    int k = count / 2;
    for (int i = low; i < low + k; ++i) {
        if ((v.get(i) > v.get(i + k)) == up) v.swapAt(i, i + k);
    }
    bitonicMerge(v, low, k, up);
    bitonicMerge(v, low + k, k, up);
}

static void bitonicSortRec(VisualArray& v, int low, int count, bool up) {
    v.check();
    if (count <= 1) return;
    int k = count / 2;
    bitonicSortRec(v, low, k, true);
    bitonicSortRec(v, low + k, k, false);
    bitonicMerge(v, low, count, up);
}

static void bitonicSort(VisualArray& v) {
    int n = v.size();
    int power = 1;
    while (power < n) power <<= 1;
    vector<int> a = v.data();
    int sentinel = a.empty() ? 0 : *max_element(a.begin(), a.end()) + 1;
    while (static_cast<int>(a.size()) < power) a.push_back(sentinel++);
    auto state = make_shared<VisualState>();
    SortContext ctx{nullptr};
    VisualArray tmp(a, state, ctx);
    bitonicSortRec(tmp, 0, power, true);
    vector<int> out = tmp.data();
    for (int i = 0; i < n; ++i) v.set(i, out[i]);
}

static void stoogeSmallRec(VisualArray& v, int l, int h) {
    v.check();
    if (l >= h) return;
    if (v.get(l) > v.get(h)) v.swapAt(l, h);
    if (h - l + 1 > 2) {
        int t = (h - l + 1) / 3;
        stoogeSmallRec(v, l, h - t);
        stoogeSmallRec(v, l + t, h);
        stoogeSmallRec(v, l, h - t);
    }
}

static void stoogeSort(VisualArray& v) {
    int n = v.size();
    if (n <= 64) {
        stoogeSmallRec(v, 0, n - 1);
        return;
    }
    for (int pass = 0; pass < n; ++pass) {
        v.check();
        int step = max(1, n / 3);
        bool changed = false;
        for (int i = pass % step; i + step < n; i += step) {
            if (v.get(i) > v.get(i + step)) {
                v.swapAt(i, i + step);
                changed = true;
            }
        }
        if (!changed && pass > step) return;
    }
}

static void slowSmallRec(VisualArray& v, int i, int j) {
    v.check();
    if (i >= j) return;
    int m = (i + j) / 2;
    slowSmallRec(v, i, m);
    slowSmallRec(v, m + 1, j);
    if (v.get(j) < v.get(m)) v.swapAt(j, m);
    slowSmallRec(v, i, j - 1);
}

static void slowSort(VisualArray& v) {
    int n = v.size();
    if (n <= 32) {
        slowSmallRec(v, 0, n - 1);
        return;
    }
    for (int window = 2; window <= n; window = min(n, window + max(1, window / 8))) {
        v.check();
        for (int i = 0; i + window <= n; i += max(1, window / 2)) {
            int m = i + window / 2;
            int r = i + window - 1;
            if (v.get(m) > v.get(r)) v.swapAt(m, r);
        }
        if (window == n) break;
    }
    for (int i = 1; i < n; ++i) {
        v.check();
        if (v.get(i - 1) > v.get(i)) v.swapAt(i - 1, i);
    }
}

static bool visualIsSorted(VisualArray& v) {
    for (int i = 1; i < v.size(); ++i) {
        if (v.get(i - 1) > v.get(i)) return false;
    }
    return true;
}

static void bogoSort(VisualArray& v) {
    mt19937 rng(1234567);
    int n = v.size();
    while (!visualIsSorted(v)) {
        for (int i = n - 1; i > 0; --i) {
            uniform_int_distribution<int> dist(0, i);
            v.swapAt(i, dist(rng));
        }
    }
}

static void bozoSort(VisualArray& v) {
    mt19937 rng(7654321);
    uniform_int_distribution<int> dist(0, max(0, v.size() - 1));
    while (!visualIsSorted(v)) {
        int i = dist(rng);
        int j = dist(rng);
        v.swapAt(i, j);
    }
}

static void tournamentSort(VisualArray& v) {
    vector<int> a = v.data();
    vector<int> out;
    out.reserve(a.size());
    while (!a.empty()) {
        v.check();
        int minI = 0;
        for (int i = 1; i < static_cast<int>(a.size()); ++i) {
            if (a[i] < a[minI]) minI = i;
        }
        out.push_back(a[minI]);
        a.erase(a.begin() + minI);
        for (int i = 0; i < static_cast<int>(out.size()); ++i) v.set(i, out[i]);
    }
}

static void beadSort(VisualArray& v) {
    int n = v.size();
    int mx = 0;
    for (int i = 0; i < n; ++i) mx = max(mx, v.get(i));
    vector<int> beads(mx, 0);
    for (int i = 0; i < n; ++i) {
        int x = v.get(i);
        for (int j = 0; j < x; ++j) {
            v.check();
            ++beads[j];
        }
    }
    vector<int> out(n, 0);
    for (int j = 0; j < mx; ++j) {
        for (int i = n - beads[j]; i < n; ++i) ++out[i];
    }
    for (int i = 0; i < n; ++i) v.set(i, out[i]);
}

static vector<Algorithm> makeAlgorithms() {
    return {
        {"IntroSort", stdIntroSort},
        {"Stable Sort", stdStableSort},
        {"Merge Sort", mergeSort},
        {"Quick Sort", quickSort},
        {"3-Way Quick Sort", quick3Sort},
        {"Heap Sort", heapSort},
        {"Shell Sort", shellSort},
        {"Tim/Natural Merge", naturalMergeSort},
        {"Counting Sort", countingSort},
        {"Radix Sort", radixSort},
        {"Bucket Sort", bucketSort},
        {"Pigeonhole Sort", pigeonholeSort},
        {"Tree Sort", treeSort},
        {"Tournament Sort", tournamentSort},
        {"Strand Sort", strandSort},
        {"Bitonic Sort", bitonicSort},
        {"Insertion Sort", insertionSort},
        {"Binary Insertion", binaryInsertionSort},
        {"Selection Sort", selectionSort},
        {"Exchange Sort", exchangeSort},
        {"Cycle Sort", cycleSort},
        {"Pancake Sort", pancakeSort},
        {"Comb Sort", combSort},
        {"Gnome Sort", gnomeSort},
        {"Bubble Sort", bubbleSort},
        {"Cocktail Shaker", cocktailSort},
        {"Odd-Even Sort", oddEvenSort},
        {"Bead Sort", beadSort},
        {"Stooge Sort", stoogeSort},
        {"Slow Sort", slowSort},
        {"Bogo Sort", bogoSort},
        {"Bozo Sort", bozoSort},
    };
}

enum class Scenario {
    Sorted,
    Randomized,
    Reversed,
    OneNumberUnsorted,
    RandomizedDuplicates
};

static string scenarioName(Scenario s) {
    switch (s) {
        case Scenario::Sorted: return "Sorted Array";
        case Scenario::Randomized: return "Unsorted Array - Randomized";
        case Scenario::Reversed: return "Unsorted Array - Reversed";
        case Scenario::OneNumberUnsorted: return "Unsorted Array - one number unsorted";
        case Scenario::RandomizedDuplicates: return "Unsorted Array - randomized duplicates";
    }
    return "Unknown";
}

static string scenarioDescription(Scenario s) {
    switch (s) {
        case Scenario::Sorted:
            return "A trap round: already sorted input punishes bad pivot choices and rewards best-case detection.";
        case Scenario::Randomized:
            return "The classic benchmark: 100,000 values shuffled into a clean random battlefield.";
        case Scenario::Reversed:
            return "Worst-case pressure for many simple sorts: every value starts in the opposite direction.";
        case Scenario::OneNumberUnsorted:
            return "Almost perfect order with one value displaced; adaptive algorithms get a real chance here.";
        case Scenario::RandomizedDuplicates:
            return "Many repeated values: partitioning, stability, and counting-style approaches can shine.";
    }
    return "";
}

static vector<int> baseValues(int n) {
    vector<int> a(n);
    iota(a.begin(), a.end(), 1);
    return a;
}

static vector<int> makeInput(Scenario s, int n, mt19937& rng) {
    vector<int> a = baseValues(n);
    if (s == Scenario::Sorted) return a;
    if (s == Scenario::Randomized) {
        shuffle(a.begin(), a.end(), rng);
        return a;
    }
    if (s == Scenario::Reversed) {
        reverse(a.begin(), a.end());
        return a;
    }
    if (s == Scenario::OneNumberUnsorted) {
        int from = (n * 3) / 4;
        int to = n / 4;
        int x = a[from];
        a.erase(a.begin() + from);
        a.insert(a.begin() + to, x);
        return a;
    }
    uniform_int_distribution<int> dist(0, 7);
    for (int& x : a) x = 5 + dist(rng) * 11;
    shuffle(a.begin(), a.end(), rng);
    return a;
}

struct RaceResult {
    int winnerSlot = 0;
    bool tie = false;
    long long nsA = 0;
    long long nsB = 0;
    bool sortedA = false;
    bool sortedB = false;
    bool cancelledA = false;
    bool cancelledB = false;
};

enum class MatchMode {
    Group,
    Knockout
};

static void runSorter(const Algorithm& algo,
                      const vector<int>& input,
                      const shared_ptr<VisualState>& state,
                      atomic<bool>& cancel,
                      atomic<bool>& pause,
                      atomic<long long>& pausedNs) {
    SortContext ctx{&cancel, &pause, &pausedNs};
    VisualArray array(input, state, ctx);
    auto start = Clock::now();
    try {
        algo.sort(array);
        auto end = Clock::now();
        long long raceNs = max(0LL, chrono::duration_cast<Ns>(end - start).count() - pausedNs.load(memory_order_relaxed));
        vector<int> finalValues = array.snapshot();
        bool sorted = is_sorted(finalValues.begin(), finalValues.end());
        {
            lock_guard<mutex> lock(state->m);
            state->sorted = sorted;
            state->cancelled = false;
            state->ns = raceNs;
            state->elapsedMs = raceNs / 1000000;
            state->finalValues = std::move(finalValues);
            state->hotA = -1;
            state->hotB = -1;
            state->done = true;
        }
    } catch (const Cancelled&) {
        auto end = Clock::now();
        long long raceNs = max(0LL, chrono::duration_cast<Ns>(end - start).count() - pausedNs.load(memory_order_relaxed));
        vector<int> finalValues = array.snapshot();
        {
            lock_guard<mutex> lock(state->m);
            state->sorted = false;
            state->cancelled = true;
            state->ns = raceNs;
            state->elapsedMs = raceNs / 1000000;
            state->finalValues = std::move(finalValues);
            state->hotA = -1;
            state->hotB = -1;
            state->done = true;
        }
    }
}

static RaceResult race(const Algorithm& a,
                       const Algorithm& b,
                       const vector<int>& input,
                       const string& title,
                       Scenario scenario,
                       int round,
                       MatchMode mode) {
    auto stateA = make_shared<VisualState>();
    auto stateB = make_shared<VisualState>();
    stateA->name = a.name;
    stateB->name = b.name;

    atomic<bool> cancelA(false), cancelB(false);
    atomic<bool> pauseA(false), pauseB(false);
    atomic<long long> pausedNsA(0), pausedNsB(0);
    thread threadA(runSorter, cref(a), cref(input), stateA, ref(cancelA), ref(pauseA), ref(pausedNsA));
    thread threadB(runSorter, cref(b), cref(input), stateB, ref(cancelB), ref(pauseB), ref(pausedNsB));

    auto start = Clock::now();
    chrono::milliseconds pausedUi(0);
    optional<Clock::time_point> graceEnd;
    const auto grace = chrono::seconds(1);
    const auto groupTieCap = chrono::seconds(5);
    bool forcedTie = false;
    bool renderedOnce = false;

    while (true) {
        bool doneA, doneB;
        bool sortedA, sortedB;
        {
            lock_guard<mutex> lock(stateA->m);
            doneA = stateA->done;
            sortedA = stateA->sorted;
        }
        {
            lock_guard<mutex> lock(stateB->m);
            doneB = stateB->done;
            sortedB = stateB->sorted;
        }

        auto now = Clock::now();
        auto activeElapsed = now - start - pausedUi;
        long long elapsedMs = max(0LL, chrono::duration_cast<chrono::milliseconds>(activeElapsed).count());
        {
            lock_guard<mutex> lock(stateA->m);
            if (!stateA->done) stateA->elapsedMs = elapsedMs;
        }
        {
            lock_guard<mutex> lock(stateB->m);
            if (!stateB->done) stateB->elapsedMs = elapsedMs;
        }
        if (mode == MatchMode::Knockout) {
            if (doneA && sortedA && !doneB) cancelB.store(true, memory_order_relaxed);
            if (doneB && sortedB && !doneA) cancelA.store(true, memory_order_relaxed);
        } else {
            if (doneA && sortedA && !doneB && !graceEnd) graceEnd = now + grace;
            if (doneB && sortedB && !doneA && !graceEnd) graceEnd = now + grace;
            if (graceEnd && now > *graceEnd) {
                if (!doneA) cancelA.store(true, memory_order_relaxed);
                if (!doneB) cancelB.store(true, memory_order_relaxed);
            }
            if (!sortedA && !sortedB && activeElapsed > groupTieCap) {
                forcedTie = true;
                cancelA.store(true, memory_order_relaxed);
                cancelB.store(true, memory_order_relaxed);
            }
        }

        if (!renderedOnce) {
            renderRaceHeader(title, scenarioName(scenario), scenarioDescription(scenario), round);
            renderedOnce = true;
        }
        renderRaceStatus(stateA, stateB);
        if (doneA && doneB) break;
        sleepMs(100);
    }

    if (threadA.joinable()) threadA.join();
    if (threadB.joinable()) threadB.join();

    if (renderedOnce) {
        renderRaceStatus(stateA, stateB);
        finishRaceStatus();
    }

    RaceResult result;
    vector<int> finalA, finalB;
    {
        lock_guard<mutex> lock(stateA->m);
        result.nsA = stateA->ns;
        result.sortedA = stateA->sorted;
        result.cancelledA = stateA->cancelled;
        finalA = stateA->finalValues;
    }
    {
        lock_guard<mutex> lock(stateB->m);
        result.nsB = stateB->ns;
        result.sortedB = stateB->sorted;
        result.cancelledB = stateB->cancelled;
        finalB = stateB->finalValues;
    }

    if (forcedTie && mode == MatchMode::Group) {
        result.tie = true;
        result.winnerSlot = -1;
    } else if (result.sortedA != result.sortedB) {
        result.winnerSlot = result.sortedA ? 0 : 1;
    } else if (result.sortedA && result.sortedB) {
        result.winnerSlot = result.nsA <= result.nsB ? 0 : 1;
    } else {
        int badA = adjacentDisorder(finalA);
        int badB = adjacentDisorder(finalB);
        if (badA != badB) result.winnerSlot = badA < badB ? 0 : 1;
        else result.winnerSlot = result.nsA <= result.nsB ? 0 : 1;
    }
    return result;
}

struct MatchResult {
    int winner = -1;
    int loser = -1;
    bool tie = false;
    int winsA = 0;
    int winsB = 0;
    int ties = 0;
    long long nsA = 0;
    long long nsB = 0;
};

static void renderRoundIntro(const Algorithm& a,
                             const Algorithm& b,
                             const string& stage,
                             Scenario scenario,
                             int round,
                             int winsA,
                             int winsB,
                             int ties) {
    cout << "\n";
    trophyHeader("ROUND " + to_string(round));
    cout << "\n";
    cout << "+=================================================================+\n";
    cout << "| " << left << setw(63) << stage.substr(0, 63) << " |\n";
    cout << "| " << left << setw(25) << a.name.substr(0, 25)
         << "  " << winsA << " - " << winsB << "  "
         << right << setw(25) << b.name.substr(0, 25) << " |\n";
    cout << "| Round ties in match: " << left << setw(41) << ties << " |\n";
    cout << "+=================================================================+\n\n";
    cout << "ROUND " << round << " / 5\n";
    cout << scenarioName(scenario) << "\n";
    cout << scenarioDescription(scenario) << "\n\n";
    cout << "Array size: " << fmtCount(ARRAY_SIZE) << "\n";
    cout << "Win condition: fastest verified sorted finish, measured in nanoseconds.\n";
    cout << "Group timeout: 5s no sorter = tied round. Sorted finisher gives opponent 1s.\n";
}

static void renderRoundResult(const Algorithm& a,
                              const Algorithm& b,
                              const string& stage,
                              const RaceResult& rr,
                              int winsA,
                              int winsB,
                              int ties,
                              bool matchOver) {
    trophyHeader(matchOver ? "MATCH DECIDED" : "ROUND RESULT");
    cout << "\n";
    string winner = rr.tie ? "TIED ROUND" : (rr.winnerSlot == 0 ? a.name : b.name);
    cout << "+=================================================================+\n";
    cout << "| " << left << setw(63) << stage.substr(0, 63) << " |\n";
    cout << "| Round result: " << left << setw(49) << winner.substr(0, 49) << " |\n";
    cout << "| Match score: " << left << setw(51)
         << (a.name + " " + to_string(winsA) + " - " + to_string(winsB) + " " + b.name + " | ties " + to_string(ties)).substr(0, 51)
         << " |\n";
    cout << "+=================================================================+\n\n";
    cout << left << setw(24) << a.name << " " << setw(18) << fmtNs(rr.nsA)
         << (rr.sortedA ? " sorted" : " not sorted") << (rr.cancelledA ? " terminated" : "") << "\n";
    cout << left << setw(24) << b.name << " " << setw(18) << fmtNs(rr.nsB)
         << (rr.sortedB ? " sorted" : " not sorted") << (rr.cancelledB ? " terminated" : "") << "\n";
    cout << "\n";
}

static MatchResult playMatch(const vector<Algorithm>& algorithms,
                             int idA,
                             int idB,
                             const string& stage,
                             mt19937& rng,
                             MatchMode mode) {
    vector<Scenario> scenarios = {
        Scenario::Sorted,
        Scenario::Randomized,
        Scenario::Reversed,
        Scenario::OneNumberUnsorted,
        Scenario::RandomizedDuplicates
    };
    MatchResult match;
    int winsA = 0, winsB = 0;
    int ties = 0;
    long long nsA = 0, nsB = 0;
    for (int round = 1; round <= 5; ++round) {
        stringstream title;
        title << stage << " | " << algorithms[idA].name << " vs " << algorithms[idB].name
              << " | score " << winsA << "-" << winsB;
        renderRoundIntro(algorithms[idA], algorithms[idB], stage, scenarios[round - 1], round, winsA, winsB, ties);
        sleepMs(450);
        vector<int> input = makeInput(scenarios[round - 1], ARRAY_SIZE, rng);
        RaceResult rr = race(algorithms[idA], algorithms[idB], input, title.str(), scenarios[round - 1], round, mode);
        nsA += rr.nsA;
        nsB += rr.nsB;
        if (rr.tie) ++ties;
        else if (rr.winnerSlot == 0) ++winsA;
        else ++winsB;

        bool matchOver = winsA == 3 || winsB == 3 || (round == 5 && mode == MatchMode::Group);
        renderRoundResult(algorithms[idA], algorithms[idB], title.str(), rr, winsA, winsB, ties, matchOver);
        sleepMs(matchOver ? 800 : 500);
        if (matchOver) {
            break;
        }
    }
    match.winsA = winsA;
    match.winsB = winsB;
    match.ties = ties;
    match.nsA = nsA;
    match.nsB = nsB;
    if (winsA == winsB && mode == MatchMode::Group) {
        match.tie = true;
        match.winner = -1;
        match.loser = -1;
    } else {
        match.winner = winsA > winsB ? idA : idB;
        match.loser = winsA > winsB ? idB : idA;
    }
    return match;
}

struct Standing {
    int algo = -1;
    int played = 0;
    int points = 0;
    int matchWins = 0;
    int matchDraws = 0;
    int matchLosses = 0;
    int roundWins = 0;
    int roundLosses = 0;
    long long ns = 0;
};

struct Fixture {
    int group = -1;
    int a = -1;
    int b = -1;
};

class Tournament {
public:
    explicit Tournament(vector<Algorithm> algos)
        : algorithms(std::move(algos)), rng(random_device{}()) {
        drawGroups(false);
        buildSchedule();
    }

    void drawGroups(bool animated = true) {
        vector<int> ids(algorithms.size());
        iota(ids.begin(), ids.end(), 0);
        shuffle(ids.begin(), ids.end(), rng);
        groups.assign(8, {});
        if (animated) {
            clearScreen();
            trophyHeader("GROUP DRAW");
            cout << "\nThe balls are in the bowls. Eight groups. Four algorithms each.\n";
            sleepMs(650);
        }
        for (int pot = 0; pot < 4; ++pot) {
            if (animated) {
                clearScreen();
                trophyHeader("POT " + to_string(pot + 1));
                cout << "\n";
                renderDrawBoard();
                cout << "\nOpening Pot " << pot + 1 << "...\n";
                sleepMs(450);
            }
            for (int g = 0; g < 8; ++g) {
                int id = ids[pot * 8 + g];
                groups[g].push_back(id);
                if (animated) {
                    clearScreen();
                    trophyHeader("GROUP DRAW");
                    cout << "\n";
                    cout << "Ball drawn: " << algorithms[id].name
                         << "  ->  Group " << char('A' + g) << "\n\n";
                    renderDrawBoard(g);
                    sleepMs(220);
                }
            }
        }
        initStandings();
        buildSchedule();
        if (animated) {
            clearScreen();
            trophyHeader("FINAL GROUPS");
            cout << "\n";
            renderDrawBoard();
        }
    }

    void buildSchedule() {
        fixtures.clear();
        int pairs[6][2] = {{0, 1}, {2, 3}, {0, 2}, {1, 3}, {0, 3}, {1, 2}};
        for (int round = 0; round < 6; ++round) {
            for (int g = 0; g < 8; ++g) {
                fixtures.push_back({g, groups[g][pairs[round][0]], groups[g][pairs[round][1]]});
            }
        }
    }

    void showGroups() const {
        clearScreen();
        trophyHeader("GROUPS");
        cout << "\n";
        renderDrawBoard();
    }

    void showSchedule() const {
        clearScreen();
        trophyHeader("GROUP STAGE FIXTURES");
        cout << "\n";
        for (int g = 0; g < 8; ++g) {
            cout << "+=========================== GROUP " << char('A' + g)
                 << " ===========================+\n";
            int local = 1;
            for (int i = 0; i < static_cast<int>(fixtures.size()); ++i) {
                const auto& f = fixtures[i];
                if (f.group != g) continue;
                cout << "| " << setw(2) << local++ << "  "
                     << left << setw(23) << algorithms[f.a].name
                     << " vs "
                     << left << setw(23) << algorithms[f.b].name << " |\n";
            }
            cout << "+=================================================================+\n\n";
        }
    }

    void showStandings(bool clear = true) const {
        if (clear) clearScreen();
        trophyHeader("GROUP TABLES");
        cout << "\n";
        for (int g = 0; g < 8; ++g) {
            auto table = sortedGroup(g);
            cout << "+=========================== GROUP " << char('A' + g)
                 << " ===========================+\n";
            cout << "| " << left << setw(22) << "Algorithm" << right << setw(4) << "P"
                 << setw(5) << "Pts" << setw(5) << "W" << setw(5) << "D" << setw(6) << "RW"
                 << setw(6) << "RD" << " |\n";
            for (const auto& s : table) {
                cout << "| " << left << setw(22) << algorithms[s.algo].name << right
                     << setw(4) << s.played << setw(5) << s.points
                     << setw(5) << s.matchWins << setw(5) << s.matchDraws << setw(6) << s.roundWins
                     << setw(6) << (s.roundWins - s.roundLosses) << " |\n";
            }
            cout << "+=================================================================+\n\n";
        }
    }

    void play() {
        playGroupStage();
        playKnockouts();
    }

private:
    vector<Algorithm> algorithms;
    vector<vector<int>> groups;
    vector<Fixture> fixtures;
    vector<Standing> standings;
    vector<int> currentBracket;
    string currentStage = "Group Stage";
    mt19937 rng;

    void renderDrawBoard(int highlightedGroup = -1) const {
        for (int row = 0; row < 4; row += 2) {
            for (int g = row; g < row + 2; ++g) {
                bool hot = g == highlightedGroup;
                if (hot) cout << "\033[36m";
                cout << "+-----------------------------+  ";
                if (hot) cout << "\033[0m";
            }
            cout << "\n";
            for (int g = row; g < row + 2; ++g) {
                bool hot = g == highlightedGroup;
                if (hot) cout << "\033[36m";
                cout << "| GROUP " << char('A' + g) << "                     |  ";
                if (hot) cout << "\033[0m";
            }
            cout << "\n";
            for (int slot = 0; slot < 4; ++slot) {
                for (int g = row; g < row + 2; ++g) {
                    bool hot = g == highlightedGroup;
                    string name = slot < static_cast<int>(groups[g].size())
                                      ? algorithms[groups[g][slot]].name
                                      : ".....................";
                    if (hot) cout << "\033[36m";
                    cout << "| " << left << setw(27) << name.substr(0, 27) << " |  ";
                    if (hot) cout << "\033[0m";
                }
                cout << "\n";
            }
            for (int g = row; g < row + 2; ++g) {
                bool hot = g == highlightedGroup;
                if (hot) cout << "\033[36m";
                cout << "+-----------------------------+  ";
                if (hot) cout << "\033[0m";
            }
            cout << "\n\n";
        }
        for (int row = 4; row < 8; row += 2) {
            for (int g = row; g < row + 2; ++g) {
                bool hot = g == highlightedGroup;
                if (hot) cout << "\033[36m";
                cout << "+-----------------------------+  ";
                if (hot) cout << "\033[0m";
            }
            cout << "\n";
            for (int g = row; g < row + 2; ++g) {
                bool hot = g == highlightedGroup;
                if (hot) cout << "\033[36m";
                cout << "| GROUP " << char('A' + g) << "                     |  ";
                if (hot) cout << "\033[0m";
            }
            cout << "\n";
            for (int slot = 0; slot < 4; ++slot) {
                for (int g = row; g < row + 2; ++g) {
                    bool hot = g == highlightedGroup;
                    string name = slot < static_cast<int>(groups[g].size())
                                      ? algorithms[groups[g][slot]].name
                                      : ".....................";
                    if (hot) cout << "\033[36m";
                    cout << "| " << left << setw(27) << name.substr(0, 27) << " |  ";
                    if (hot) cout << "\033[0m";
                }
                cout << "\n";
            }
            for (int g = row; g < row + 2; ++g) {
                bool hot = g == highlightedGroup;
                if (hot) cout << "\033[36m";
                cout << "+-----------------------------+  ";
                if (hot) cout << "\033[0m";
            }
            cout << "\n\n";
        }
    }

    void initStandings() {
        standings.assign(algorithms.size(), {});
        for (int i = 0; i < static_cast<int>(algorithms.size()); ++i) standings[i].algo = i;
    }

    vector<Standing> sortedGroup(int g) const {
        vector<Standing> table;
        for (int id : groups[g]) table.push_back(standings[id]);
        sort(table.begin(), table.end(), [](const Standing& x, const Standing& y) {
            int dx = x.roundWins - x.roundLosses;
            int dy = y.roundWins - y.roundLosses;
            if (x.points != y.points) return x.points > y.points;
            if (x.matchWins != y.matchWins) return x.matchWins > y.matchWins;
            if (dx != dy) return dx > dy;
            if (x.roundWins != y.roundWins) return x.roundWins > y.roundWins;
            if (x.ns != y.ns) return x.ns < y.ns;
            return x.algo < y.algo;
        });
        return table;
    }

    void recordGroupResult(const MatchResult& result, int a, int b) {
        Standing& sa = standings[a];
        Standing& sb = standings[b];
        ++sa.played;
        ++sb.played;
        sa.roundWins += result.winsA;
        sa.roundLosses += result.winsB;
        sb.roundWins += result.winsB;
        sb.roundLosses += result.winsA;
        sa.ns += result.nsA;
        sb.ns += result.nsB;
        if (result.tie) {
            sa.points += 1;
            sb.points += 1;
            ++sa.matchDraws;
            ++sb.matchDraws;
        } else if (result.winner == a) {
            sa.points += 3;
            ++sa.matchWins;
            ++sb.matchLosses;
        } else {
            sb.points += 3;
            ++sb.matchWins;
            ++sa.matchLosses;
        }
    }

    void playGroupStage() {
        clearScreen();
        trophyHeader("GROUP STAGE LIVE");
        cout << "\n";
        for (int i = 0; i < static_cast<int>(fixtures.size()); ++i) {
            const Fixture& f = fixtures[i];
            trophyHeader("MATCH DAY");
            cout << "\n";
            cout << "+-----------------------------+\n";
            cout << "| GROUP STAGE MATCH " << setw(2) << i + 1 << " / " << setw(2) << fixtures.size() << " |\n";
            cout << "+-----------------------------+\n\n";
            cout << "           .-------------------------------.\n";
            cout << "           | Group " << char('A' + f.group) << "                       |\n";
            cout << "           | " << left << setw(29) << algorithms[f.a].name.substr(0, 29) << " |\n";
            cout << "           |              VS               |\n";
            cout << "           | " << left << setw(29) << algorithms[f.b].name.substr(0, 29) << " |\n";
            cout << "           '-------------------------------'\n";
            sleepMs(500);
            MatchResult result = playMatch(
                algorithms,
                f.a,
                f.b,
                "Group " + string(1, char('A' + f.group)),
                rng,
                MatchMode::Group);
            recordGroupResult(result, f.a, f.b);
            trophyHeader("RESULT");
            cout << "\n";
            cout << algorithms[f.a].name << " " << result.winsA << " - " << result.winsB
                 << " " << algorithms[f.b].name << "  | round ties " << result.ties << "\n";
            cout << "Result: " << (result.tie ? "Match draw" : ("Winner: " + algorithms[result.winner].name)) << "\n\n";
            sleepMs(900);
        }
        showStandings(false);
        sleepMs(1500);
    }

    vector<int> qualified() const {
        vector<int> q;
        auto push = [&](int group, int pos) {
            auto table = sortedGroup(group);
            q.push_back(table[pos].algo);
        };
        push(0, 0); push(1, 1);
        push(2, 0); push(3, 1);
        push(4, 0); push(5, 1);
        push(6, 0); push(7, 1);
        push(1, 0); push(0, 1);
        push(3, 0); push(2, 1);
        push(5, 0); push(4, 1);
        push(7, 0); push(6, 1);
        return q;
    }

    void renderBracket(const vector<int>& current, const string& stage) const {
        trophyHeader(stage);
        cout << "\n";
        cout << "KNOCKOUT BRACKET\n\n";
        for (int i = 0; i < static_cast<int>(current.size()); i += 2) {
            cout << "      +------------------------+\n";
            cout << setw(2) << (i / 2 + 1) << "    | "
                 << left << setw(22) << algorithms[current[i]].name.substr(0, 22) << " |\n";
            cout << "      |           VS           |\n";
            cout << "      | "
                 << left << setw(22) << algorithms[current[i + 1]].name.substr(0, 22) << " |\n";
            cout << "      +------------------------+\n\n";
        }
    }

    void showCurrentBracket() const {
        clearScreen();
        trophyHeader("BRACKET VIEW");
        cout << "\n";
        if (currentBracket.empty()) {
            cout << "Knockout bracket is not available yet.\n";
            cout << "Finish the group stage first; top two from each group advance.\n";
            return;
        }
        cout << "Current stage: " << currentStage << "\n\n";
        for (int i = 0; i < static_cast<int>(currentBracket.size()); i += 2) {
            cout << "      +------------------------+\n";
            cout << setw(2) << (i / 2 + 1) << "    | "
                 << left << setw(22) << algorithms[currentBracket[i]].name.substr(0, 22) << " |\n";
            if (i + 1 < static_cast<int>(currentBracket.size())) {
                cout << "      |           VS           |\n";
                cout << "      | "
                     << left << setw(22) << algorithms[currentBracket[i + 1]].name.substr(0, 22) << " |\n";
            } else {
                cout << "      |       CHAMPION         |\n";
            }
            cout << "      +------------------------+\n\n";
        }
    }

    vector<int> playStage(vector<int> entrants, const string& stage) {
        currentStage = stage;
        currentBracket = entrants;
        renderBracket(entrants, stage);
        sleepMs(900);
        vector<int> winners;
        for (int i = 0; i < static_cast<int>(entrants.size()); i += 2) {
            int a = entrants[i];
            int b = entrants[i + 1];
            trophyHeader(stage + " MATCH");
            cout << "\n";
            cout << "      +------------------------+\n";
            cout << "      | " << left << setw(22) << algorithms[a].name.substr(0, 22) << " |\n";
            cout << "      |           VS           |\n";
            cout << "      | " << left << setw(22) << algorithms[b].name.substr(0, 22) << " |\n";
            cout << "      +------------------------+\n";
            sleepMs(500);
            MatchResult result = playMatch(algorithms, a, b, stage, rng, MatchMode::Knockout);
            winners.push_back(result.winner);
            trophyHeader(stage + " RESULT");
            cout << "\n";
            cout << algorithms[a].name << " " << result.winsA << " - " << result.winsB
                 << " " << algorithms[b].name << "\n";
            cout << "Advances: " << algorithms[result.winner].name << "\n";
            sleepMs(1100);
        }
        return winners;
    }

    void championAnimation(const string& champion) const {
        vector<string> cup = {
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
        };
        cout << "\n\n";
        cout << "========================================================================\n";
        cout << "                         WORLD CUP CHAMPION\n";
        cout << "========================================================================\n";
        for (const string& line : cup) cout << line << "\n";
        cout << "\nCHAMPION: " << champion << "\n";
        cout << "========================================================================\n";
    }

    void playKnockouts() {
        vector<int> r16 = qualified();
        vector<int> qf = playStage(r16, "ROUND OF 16");
        vector<int> sf = playStage(qf, "QUARTER FINALS");
        vector<int> finalTwo = playStage(sf, "SEMI FINALS");
        vector<int> champion = playStage(finalTwo, "FINAL");
        championAnimation(algorithms[champion.front()].name);
        waitEnter("Press Enter to exit...");
    }
};

static void titleScreen() {
    clearScreen();
    trophyHeader("MAIN MENU");
    cout << "\n";
    cout << "        .------------------------------------------------.\n";
    cout << "        |  32 algorithms enter.  One champion leaves.    |\n";
    cout << "        |  Array size: " << left << setw(34) << fmtCount(ARRAY_SIZE) << " |\n";
    cout << "        |  Match format: best of five live races.        |\n";
    cout << "        '------------------------------------------------'\n\n";
}

static int selfTest() {
    vector<Algorithm> algorithms = makeAlgorithms();
    vector<Scenario> scenarios = {
        Scenario::Sorted,
        Scenario::Randomized,
        Scenario::Reversed,
        Scenario::OneNumberUnsorted,
        Scenario::RandomizedDuplicates
    };
    mt19937 rng(20260531);
    int failures = 0;

    for (const auto& algorithm : algorithms) {
        for (Scenario scenario : scenarios) {
            vector<int> input = makeInput(scenario, 6, rng);
            auto state = make_shared<VisualState>();
            state->name = algorithm.name;
            atomic<bool> cancel(false);
            atomic<bool> pause(false);
            atomic<long long> pausedNs(0);
            thread worker(runSorter, cref(algorithm), cref(input), state, ref(cancel), ref(pause), ref(pausedNs));
            auto deadline = Clock::now() + chrono::seconds(2);
            while (Clock::now() < deadline) {
                bool done;
                {
                    lock_guard<mutex> lock(state->m);
                    done = state->done;
                }
                if (done) break;
                sleepMs(5);
            }
            {
                lock_guard<mutex> lock(state->m);
                if (!state->done) cancel.store(true, memory_order_relaxed);
            }
            if (worker.joinable()) worker.join();

            bool ok;
            bool cancelled;
            {
                lock_guard<mutex> lock(state->m);
                ok = state->sorted;
                cancelled = state->cancelled;
            }
            if (!ok) {
                ++failures;
                cout << "FAIL: " << algorithm.name << " on " << scenarioName(scenario)
                     << (cancelled ? " (timeout)" : "") << "\n";
            }
        }
    }

    for (const string& quickName : {"Quick Sort", "3-Way Quick Sort"}) {
        auto quickIt = find_if(algorithms.begin(), algorithms.end(), [&](const Algorithm& algorithm) {
            return algorithm.name == quickName;
        });
        if (quickIt == algorithms.end()) continue;
        vector<int> input = makeInput(Scenario::Sorted, ARRAY_SIZE, rng);
        auto state = make_shared<VisualState>();
        state->name = quickIt->name;
        atomic<bool> cancel(false);
        atomic<bool> pause(false);
        atomic<long long> pausedNs(0);
        thread worker(runSorter, cref(*quickIt), cref(input), state, ref(cancel), ref(pause), ref(pausedNs));
        auto deadline = Clock::now() + chrono::seconds(5);
        while (Clock::now() < deadline) {
            bool done;
            {
                lock_guard<mutex> lock(state->m);
                done = state->done;
            }
            if (done) break;
            sleepMs(5);
        }
        {
            lock_guard<mutex> lock(state->m);
            if (!state->done) cancel.store(true, memory_order_relaxed);
        }
        if (worker.joinable()) worker.join();
        bool ok;
        {
            lock_guard<mutex> lock(state->m);
            ok = state->sorted && !state->cancelled;
        }
        if (!ok) {
            ++failures;
            cout << "FAIL: " << quickIt->name << " on 100,000 sorted values\n";
        }
    }

    if (failures == 0) {
        cout << "Self-test passed: 32 algorithms x 5 scenarios + 100,000-item quicksort smoke tests.\n";
        return 0;
    }
    cout << "Self-test failed: " << failures << " case(s).\n";
    return 1;
}

int runApp(int argc, char** argv) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    if (argc > 1 && string(argv[1]) == "--self-test") {
        return selfTest();
    }

    vector<Algorithm> algorithms = makeAlgorithms();
    Tournament tournament(algorithms);

    while (true) {
        titleScreen();
        cout << "1. Tournament Initialization / Group Draw\n";
        cout << "2. Scheduling of Matches\n";
        cout << "3. Play Tournament\n";
        cout << "4. Points Table\n";
        cout << "5. Exit\n\n";
        cout << "Choose: ";
        string choice;
        getline(cin, choice);
        if (choice == "1") {
            tournament.drawGroups();
            waitEnter();
        } else if (choice == "2") {
            tournament.showSchedule();
            waitEnter();
        } else if (choice == "3") {
            tournament.play();
            break;
        } else if (choice == "4") {
            tournament.showStandings();
            waitEnter();
        } else if (choice == "5") {
            break;
        }
    }
    return 0;
}
