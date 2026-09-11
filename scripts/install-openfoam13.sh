#!/usr/bin/env bash
# Build a pinned OF13 installation OR reuse an existing Foundation OF13 installation.
# System package installation is opt-in. Existing source edits are never reset.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
prefix="$HOME/OpenFOAM-bioTank"
foam_dir=
jobs=4
deps=false
protocol=https
export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=Never
while (($#)); do
    case $1 in
        --prefix) prefix=${2:?}; shift 2 ;;
        --foam-dir) foam_dir=${2:?}; shift 2 ;;
        --jobs) jobs=${2:?}; shift 2 ;;
        --install-deps) deps=true; shift ;;
        --git-protocol) protocol=${2:?}; shift 2 ;;
        --help) echo 'Usage: install-openfoam13.sh [--foam-dir DIR] [--prefix DIR] [--jobs N] [--install-deps] [--git-protocol ssh|https]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $jobs =~ ^[1-9][0-9]*$ ]] || exit 2
[[ $protocol == ssh || $protocol == https ]] || { echo '--git-protocol must be ssh or https.' >&2; exit 2; }
[[ $prefix != *[[:space:]]* && $repo != *[[:space:]]* && $foam_dir != *[[:space:]]* ]] || { echo 'Use paths without whitespace.' >&2; exit 2; }
mkdir -p "$prefix"
prefix=$(cd "$prefix" && pwd)
if $deps; then
    privileged=(); if ((EUID!=0)); then privileged=(sudo); fi
    "${privileged[@]}" apt-get update
    "${privileged[@]}" apt-get install -y build-essential git flex bison cmake zlib1g-dev libopenmpi-dev openmpi-bin libreadline-dev libncurses-dev libxt-dev python3
fi
foam_revision=18870c24d21c6b982e2cdec27b2f59738cca5f90
thirdparty_revision=ba1e22d69da30817a29cedfde3ea276719bec4e8
checkout() {
    local name=$1 revision=$2 destination="$prefix/$1"
    if [[ ! -e $destination ]]; then
        local url="https://github.com/OpenFOAM/$name.git"
        if [[ $protocol == ssh ]]; then url="git@github.com:OpenFOAM/$name.git"; fi
        git clone "$url" "$destination"
        git -C "$destination" checkout --detach "$revision"
    fi
    [[ $(git -C "$destination" rev-parse HEAD) == "$revision" ]] || { echo "Revision mismatch: $destination" >&2; exit 1; }
    [[ -z $(git -C "$destination" status --porcelain --untracked-files=no) ]] || { echo "Tracked edits in $destination; choose another prefix." >&2; exit 1; }
}
if [[ -z $foam_dir ]]; then
    checkout OpenFOAM-13 "$foam_revision"
    checkout ThirdParty-13 "$thirdparty_revision"
    foam_dir="$prefix/OpenFOAM-13"
    build_foam=true
else
    foam_dir=$(cd "$foam_dir" && pwd)
    [[ -f "$foam_dir/etc/bashrc" ]] || { echo 'OpenFOAM etc/bashrc is missing.' >&2; exit 1; }
    existing_revision=$(git -C "$foam_dir" rev-parse HEAD 2>/dev/null || printf 'unknown')
    if [[ $existing_revision != "$foam_revision" ]]; then
        echo "Info: Using existing OpenFOAM revision $existing_revision, different from the revision tested with this solver."
        echo 'Another Foundation OpenFOAM 13 revision should normally be fine; continuing.'
    fi
    build_foam=false
fi
set +eu
source "$foam_dir/etc/bashrc" WM_COMPILER=Gcc WM_MPLIB=SYSTEMOPENMPI SCOTCH_TYPE=ThirdParty ZOLTAN_TYPE=ThirdParty
set -eu
[[ ${WM_PROJECT_VERSION:-} == 13 ]] || exit 1
if $build_foam; then
    (cd "$foam_dir" && ./Allwmake -j "$jobs") 2>&1 | tee "$prefix/log.OpenFOAM13"
fi
for program in foamRun checkMesh snappyHexMeshConfig snappyHexMesh foamDictionary; do command -v "$program" >/dev/null; done
bash "$repo/Allwmake" 2>&1 | tee "$prefix/log.bioTankControlFoam"
activate="$prefix/activate-bioTankControlFoam.sh"
{
    printf '# Source in Bash; restores caller shell flags.\nbio_saved_flags=$-\nset +eu\n'
    printf 'source %q WM_COMPILER=Gcc WM_MPLIB=SYSTEMOPENMPI SCOTCH_TYPE=ThirdParty ZOLTAN_TYPE=ThirdParty\n' "$foam_dir/etc/bashrc"
    printf 'source %q\n' "$repo/scripts/activate.sh"
    printf 'case $bio_saved_flags in *u*) set -u ;; esac\ncase $bio_saved_flags in *e*) set -e ;; esac\nunset bio_saved_flags\n'
} > "$activate"
printf 'Build complete. Activate with:\nsource %q\n' "$activate"
