BIN_NAME := videocut
TARGET_BIN := $(HOME)/.local/bin/$(BIN_NAME)

.PHONY: fmt test check install-local

fmt:
	cargo fmt

test:
	cargo test

check:
	cargo clippy --all-targets --all-features -- -D warnings

install-local:
	cargo build --release
	mkdir -p "$(HOME)/.local/bin"
	cp "target/release/$(BIN_NAME)" "$(TARGET_BIN)"
	chmod +x "$(TARGET_BIN)"
