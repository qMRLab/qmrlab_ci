#!/usr/bin/env bash
# Build the qmrust CLI. The Rust toolchain is installed by the workflow; this script
# owns only what is true of this target.
set -euo pipefail
git clone --depth 1 --branch "${QMRLAB_CI_SOURCE_REF:-main}" \
    "https://github.com/${QMRLAB_CI_SOURCE_REPO:-qMRLab/qmrust}.git" qmrust
cd qmrust
cargo build -p qmrust-cli --release
echo "qmrust built: $(./target/release/qmrust --version)"
