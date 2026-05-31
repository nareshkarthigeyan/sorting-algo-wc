CXX ?= clang++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -pedantic -pthread

TARGET := sorting-world-cup
SRC := main.cpp sorting_world_cup.cpp

.PHONY: all run clean run-py test-py

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(SRC) -o $(TARGET)

run: run-py

run-cpp: $(TARGET)
	./$(TARGET)

run-py:
	python3 main.py

test-py:
	python3 main.py --self-test

clean:
	rm -f $(TARGET)
