#!/usr/bin/env bash
# V1 predates qMRLab's src/ layout: everything is at the checkout root, and its
# startup.m expects an interactive session. Adding the tree to the path is the whole
# install. Kept here rather than in shared code because it is true only of this target.
set -euo pipefail
echo "qMRLab V1 needs no build; the driver adds genpath(qMRLab) itself."
