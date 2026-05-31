# Sorting Algorithm World Cup

A terminal tournament simulator for 32 C++ sorting algorithms.

## Build

```sh
make
```

## Run

```sh
make run
```

## Verify

```sh
./sorting-world-cup --self-test
```

## Format

- 32 algorithms are randomly drawn into 8 groups of 4.
- Group stage is round robin.
- Top 2 from each group advance.
- Knockout bracket runs Round of 16, Quarter Finals, Semi Finals, and Final.
- Every match is best of 5.
- Every race uses an array size of 100,000.
- Rounds use:
  - Sorted Array
  - Unsorted Array - Randomized
  - Unsorted Array - Reversed
  - Unsorted Array - one number unsorted
  - Unsorted Array - randomized duplicates
- Faster successful sort wins the round, measured in nanoseconds.
- In group-stage rounds, if nobody sorts within 5 seconds, the round is a tie.
- In group-stage rounds, if one algorithm sorts first, the opponent gets only 1 second before termination.
- In knockout rounds, ties are disabled: the first verified sorted finish wins and the other side is cancelled.

The live race UI shows timers, operation counts, read/write counts, and a sortedness meter. The meter uses fixed probes across the 100,000-item array, because printing the full array would make the UI dominate the race.

Tournament play advances automatically through rounds and matches. Finished round and match summaries remain in the terminal history; only the live race panel updates in place while a race is running.
