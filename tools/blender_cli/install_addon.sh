#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ADDON_SOURCE="$SCRIPT_DIR/blender_toolkit_addon"
ADDON_PARENT="$HOME/Library/Application Support/Blender/5.2/scripts/addons"
ADDON_TARGET="$ADDON_PARENT/hannibal_blender_toolkit"
BLENDER_BIN=${BLENDER_BIN:-/opt/homebrew/bin/blender}
CONFIG_DIR="$HOME/Library/Application Support/Blender/5.2/config"
STARTUP="$CONFIG_DIR/startup.blend"

if [ ! -f "$BLENDER_BIN" ]; then
  printf 'Blender executable not found: %s\n' "$BLENDER_BIN" >&2
  exit 1
fi
mkdir -p "$ADDON_PARENT"
if [ -L "$ADDON_TARGET" ]; then
  if [ "$(readlink "$ADDON_TARGET")" != "$ADDON_SOURCE" ]; then
    printf 'Refusing to replace unrelated add-on path: %s\n' "$ADDON_TARGET" >&2
    exit 1
  fi
elif [ -e "$ADDON_TARGET" ]; then
  printf 'Refusing to replace existing add-on path: %s\n' "$ADDON_TARGET" >&2
  exit 1
fi
if [ -e "$STARTUP" ]; then
  printf 'Refusing to replace existing startup file: %s\n' "$STARTUP" >&2
  exit 1
fi
if [ ! -L "$ADDON_TARGET" ]; then
  ln -s "$ADDON_SOURCE" "$ADDON_TARGET"
fi
"$BLENDER_BIN" -P "$SCRIPT_DIR/install_addon.py"
printf 'SETUP_COMPLETE addon=%s startup=%s\n' "$ADDON_TARGET" "$STARTUP"
