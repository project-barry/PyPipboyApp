#!/bin/sh
# Compile the app's shaders (barry/shaders/*.frag) into the .qsb files Qt
# Quick loads. Needs Qt 6's qsb (qt6-shadertools); the .qsb files are kept
# in the repository, so only a changed shader needs this.
set -e
QSB=${QSB:-$(command -v qsb || echo /usr/lib/qt6/bin/qsb)}
cd "$(dirname "$0")/../barry/shaders"
for f in *.frag; do
    "$QSB" --glsl "100 es,120,150" --hlsl 50 --msl 12 -o "$f.qsb" "$f"
    echo "built $f.qsb"
done
