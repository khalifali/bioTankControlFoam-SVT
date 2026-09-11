#!/usr/bin/env bash
# Source after the selected Foundation OpenFOAM 13 environment.
if [[ ${WM_PROJECT_VERSION:-} != 13 ]]; then
    echo 'Activate OpenFOAM Foundation 13 first.' >&2
    return 1
fi
export BIOTANK_ROOT
BIOTANK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PATH="$BIOTANK_ROOT/bin:$PATH"
