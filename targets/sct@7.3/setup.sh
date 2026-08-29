#!/usr/bin/env bash
# Install SCT from its git tag, which is what SCT's own CI does. The native lane provides
# no toolchain: install_sct bundles its own Miniforge and pins its whole environment.
set -euo pipefail

# CLONE PATH LENGTH IS LOAD-BEARING. `-i` (in place) is the default when installing from a
# git checkout, so SCT_DIR *is* this clone directory -- and install_sct hard-refuses a
# non-interactive install when that path exceeds 107 characters (a conda long-path limit,
# spinalcordtoolbox#4813). It fails with "Default installation directory must be valid when
# running in non-interactive mode", which does not obviously name the length as the cause.
# $GITHUB_WORKSPACE on a hosted runner is short enough; a nested per-job workdir might not
# be, so this clones to a fixed shallow path rather than wherever the job happens to be.
SCT_HOME="${QMRLAB_CI_SCT_HOME:-$HOME/sct}"

# NOT piped. A clone into a non-empty directory fails, and through a pipe that failure
# exits 0 -- after which install_sct stops seeing a git checkout, falls back to
# $HOME/sct_<version>, and silently installs a DIFFERENT VERSION than the one pinned here.
# Observed during the spike: it began installing 7.4.dev0 while asking for 7.3.
rm -rf "$SCT_HOME"
git clone --depth 1 --branch "${QMRLAB_CI_SOURCE_REF:-7.3}" \
    "https://github.com/${QMRLAB_CI_SOURCE_REPO:-spinalcordtoolbox/spinalcordtoolbox}.git" \
    "$SCT_HOME"

cd "$SCT_HOME"
# -i in place, -y non-interactive, -c skip the dependency check. Measured 5m55s on darwin
# and 124s on GitHub-hosted runners in SCT's own nightly. -d/-b would cut most of the 4 GB
# footprint and both commands used here are pure elementwise numpy with no model or binary
# dependency -- but that is UNVERIFIED, so it is not done here.
./install_sct -iyc

# Assert the version from version.txt, NOT from `sct_version`: that prints
# "git-HEAD-33feed47..." and contains no "7.3" at all, so a grep for the tag would fail on
# a correct install.
installed="$(cat spinalcordtoolbox/version.txt)"
if [ "$installed" != "${QMRLAB_CI_SOURCE_REF:-7.3}" ]; then
  echo "setup.sh: installed SCT $installed, expected ${QMRLAB_CI_SOURCE_REF:-7.3}" >&2
  exit 1
fi
echo "sct installed: $installed"
echo "$SCT_HOME/bin" >> "${GITHUB_PATH:-/dev/null}"
