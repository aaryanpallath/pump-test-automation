CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror -D_POSIX_C_SOURCE=200809L
SAN = -std=c11 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all -D_POSIX_C_SOURCE=200809L
SRC = controller.c main.c

all: ../build/pumpctl ../build/pumpctl-san

../build/pumpctl: $(SRC) controller.h
	mkdir -p ../build && $(CC) $(CFLAGS) -o $@ $(SRC) -lm

../build/pumpctl-san: $(SRC) controller.h
	mkdir -p ../build && $(CC) $(SAN) -o $@ $(SRC) -lm

clean:
	rm -rf ../build

.PHONY: all clean
