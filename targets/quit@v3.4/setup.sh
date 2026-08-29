#!/usr/bin/env bash
# Install QUIT from its release asset. The native lane provides no toolchain and this
# needs none: the binary is a single statically-linked ELF whose only dynamic dependencies
# are libc, libm and the loader, with a GLIBC_2.34 floor -- fine on ubuntu-22.04 and 24.04.
set -euo pipefail

REF="${QMRLAB_CI_SOURCE_REF:-v3.4}"
REPO="${QMRLAB_CI_SOURCE_REPO:-spinicist/QUIT}"
URL="https://github.com/${REPO}/releases/download/${REF}/qi-linux.tar.gz"

# Checksum asserted, not merely downloaded. GitHub release assets are MUTABLE -- QUIT's
# release workflow runs ncipollo/release-action with allowUpdates: true -- so the tag alone
# does not pin the bytes. This is the same reasoning data/sources.yml applies to OSF.
EXPECTED_SHA="${QMRLAB_CI_QUIT_SHA:-}"

curl -fsSL -o qi.tar.gz "$URL"
if [ -n "$EXPECTED_SHA" ]; then
  echo "${EXPECTED_SHA}  qi.tar.gz" | sha256sum -c - || {
    echo "setup.sh: qi-linux.tar.gz does not match the pinned checksum" >&2; exit 1; }
fi
tar -xzf qi.tar.gz
chmod +x qi
./qi --version | grep -q "${REF#v}" || {
  echo "setup.sh: qi reports $(./qi --version), expected ${REF}" >&2; exit 1; }
echo "quit installed: $(./qi --version)"
