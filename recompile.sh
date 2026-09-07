#!/bin/bash
set -e

chmod 755 *.sh

# Ensures 'make' works properly:
rm -f ".depend" "main.o"
make clean

# Ensures compilation will fail unless rule2asm succeeds:
rm -f "includes/params.h"

rulearg=$(echo "$@" | grep -o -- '--rule [^ ]*' | sed 's/--rule //')
symmarg=$(echo "$@" | grep -o -- '--symmetry [^ ]*' | sed 's/--symmetry //')
profilearg=$(echo "$@" | grep -o -- '--profile' | sed 's/--profile/u/')
mingwarg=$(echo "$@" | grep -o -- '--mingw' | sed 's/--mingw/u/')
gpuarg=$(echo "$@" | grep -o -- '--cuda' | sed 's/--cuda/u/')
immarg=$(echo "$@" | grep -o -- '--immediate' | sed 's/--immediate/u/')

if [ "${#symmarg}" -ne 0 ]; then
if [ "${symmarg:0:1}" = "G" ]; then
gpuarg="true"
elif [ "${symmarg:0:1}" = "H" ]; then
gpuarg="true"
fi
fi

if [ "${#mingwarg}" -ne 0 ]; then
export USE_MINGW=1
fi

if [ "${#profilearg}" -ne 0 ]; then
if [ "${#gpuarg}" -ne 0 ]; then
printf "\033[31;1mWarning: --cuda and --profile are incompatible; omitting the latter.\033[0m\n"
else
export PROFILE_APGLUXE=1
fi
fi

# Ensure lifelib matches the version in the repository:
bash update-lifelib.sh
rm -rf "lifelib/avxlife/lifelogic" | true

if [ "${#rulearg}" -eq 0 ]; then
rulearg="b3s23"
echo "Rule unspecified; assuming b3s23."
fi

if [ "${#symmarg}" -eq 0 ]; then
symmarg="C1"
echo "Symmetry unspecified; assuming C1."
fi

gpuarg2="false"

if [ "${#gpuarg}" -ne 0 ]; then
export USE_GPU=1
gpuarg2="true"
if ! command -v nvcc &>/dev/null; then
    for cuda_dir in /usr/local/cuda/bin /usr/local/cuda-*/bin; do
        if [ -x "$cuda_dir/nvcc" ]; then
            export PATH="$cuda_dir:$PATH"
            break
        fi
    done
fi
fi

echo "Configuring rule $rulearg; symmetry $symmarg"

if command -v "python3" &>/dev/null; then
    echo "Using $(which python3) to configure lifelib..."
    python3 mkparams.py $rulearg $symmarg $gpuarg2
else
    echo "Using $(which python) to configure lifelib..."
    python mkparams.py $rulearg $symmarg $gpuarg2
fi

make
if [ "${#mingwarg}" -ne 0 ]; then
exit 0
fi

symmarg="$( grep 'SYMMETRY'   'includes/params.h' | grep -o '".*"' | tr '\n' '"' | sed 's/"//g' )"
rulearg="$( grep 'RULESTRING' 'includes/params.h' | grep -o '".*"' | tr '\n' '"' | sed 's/"//g' )"

if [ "${#immarg}" -ne 0 ]; then
    ./apgluxe --rule $rulearg --symmetry $symmarg "$@"
else
    ./apgluxe --rule $rulearg --symmetry $symmarg
fi

exit 0
