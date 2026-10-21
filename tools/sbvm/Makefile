BIN_NAME := sbvm
TARGET_BIN := $(HOME)/.local/bin/$(BIN_NAME)

.PHONY: fmt test install-local

fmt:
	cargo fmt

test:
	cargo test

install-local:
	cargo build --release
	mkdir -p "$(HOME)/.local/bin"
	cp "target/release/$(BIN_NAME)" "$(TARGET_BIN)"
	chmod +x "$(TARGET_BIN)"
