#!/usr/bin/env bash
# First-time setup: run this script with Bash; do not source it.
# The existing installer owns the pinned revisions and compilation steps.
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
    echo 'Run ./scripts/setup-first-time.sh, then source the printed activation file.' >&2
    return 2
fi
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

# Task 1: choose installation settings before changing anything.
prefix="$HOME/OpenFOAM-bioTank"
jobs=4
protocol=ssh
deps=true
usage() {
    cat <<'EOF'
Usage: ./scripts/setup-first-time.sh [options]

Install dependencies, build pinned OpenFOAM Foundation 13 and this project,
then create an environment activation file. Target: Ubuntu 24.04 with Bash.
Run as your normal user; only apt package installation uses sudo.

  --prefix DIR         Installation directory (default: ~/OpenFOAM-bioTank)
  --jobs N             Parallel compiler jobs (default: 4; reduce if RAM is low)
  --git-protocol NAME  ssh (default, needs GitHub SSH access) or https
  --skip-deps          Dependencies already installed; do not run apt/sudo
  --help              Show this help without installing anything

After success, source the printed activation file in each new Bash terminal.
This script does not edit your shell startup files or start a simulation.
EOF
}
while (($#)); do
    case $1 in
        --prefix|--jobs|--git-protocol)
            [[ $# -ge 2 && -n $2 && $2 != --* ]] || { echo "Missing value for $1" >&2; exit 2; }
            case $1 in
                --prefix) prefix=$2 ;;
                --jobs) jobs=$2 ;;
                --git-protocol) protocol=$2 ;;
            esac
            shift 2 ;;
        --skip-deps) deps=false; shift ;;
        --help) usage; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
done
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo '--jobs must be a positive integer.' >&2; exit 2; }
[[ $protocol == ssh || $protocol == https ]] || { echo '--git-protocol must be ssh or https.' >&2; exit 2; }
[[ $prefix != *[[:space:]]* && $repo != *[[:space:]]* ]] || { echo 'Use paths without whitespace.' >&2; exit 2; }
if $deps; then
    command -v apt-get >/dev/null || { echo 'apt-get is required; install dependencies manually and use --skip-deps.' >&2; exit 1; }
    if ((EUID != 0)); then
        command -v sudo >/dev/null || { echo 'sudo is required for dependencies; ask your administrator or use --skip-deps.' >&2; exit 1; }
    fi
fi

# Task 2: install dependencies and compile the pinned upstream sources, then
# the solver module and student controller. Failure stops setup immediately.
args=(--prefix "$prefix" --jobs "$jobs" --git-protocol "$protocol")
if $deps; then args+=(--install-deps); fi
echo 'Building OpenFOAM 13 and bioTankControlFoam. The first full build can take hours.'
bash "$repo/scripts/install-openfoam13.sh" "${args[@]}"

# Task 3: explain activation. A child script cannot change its parent terminal.
echo 'Use the source command printed above in this terminal and in each new terminal.'
echo 'Then check: echo "$WM_PROJECT_VERSION" (should print 13), and command -v foamRun'
