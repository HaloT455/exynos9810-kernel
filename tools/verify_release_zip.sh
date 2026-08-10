#!/bin/bash

set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ZIP_PATH=${1:-}

if [ -z "$ZIP_PATH" ] || [ ! -f "$ZIP_PATH" ]; then
    echo "Usage: $0 <DS-ACK release zip>" >&2
    exit 2
fi

for tool in unzip bspatch python3; do
    command -v "$tool" >/dev/null || {
        echo "Missing required tool: $tool" >&2
        exit 1
    }
done

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/ds-ack-verify.XXXXXX")
trap 'rm -rf -- "$TMP_DIR"' EXIT

unzip -tq "$ZIP_PATH" >/dev/null
unzip -q "$ZIP_PATH" -d "$TMP_DIR/package"

BASE_KERNEL="$TMP_DIR/package/floyd/G960F-kernel"
BASE_DTB="$TMP_DIR/package/floyd/G960F-dtb"
[ -s "$BASE_KERNEL" ] && [ -s "$BASE_DTB" ] || {
    echo "Release lacks the G960F base kernel/DTB" >&2
    exit 1
}

case "$(basename "$ZIP_PATH")" in
    *Permissive*) EXPECT_PERMISSIVE=y ;;
    *) EXPECT_PERMISSIVE=n ;;
esac
case "$(basename "$ZIP_PATH")" in
    *KernelSU*) EXPECT_KSU=y ;;
    *) EXPECT_KSU=n ;;
esac

for variant in G960F G965F N960F G960N G965N N960N; do
    kernel="$TMP_DIR/$variant-kernel"
    dtb="$TMP_DIR/$variant-dtb"
    if [ "$variant" = G960F ]; then
        cp "$BASE_KERNEL" "$kernel"
        cp "$BASE_DTB" "$dtb"
    else
        kernel_patch="$TMP_DIR/package/floyd/$variant-kernel"
        dtb_patch="$TMP_DIR/package/floyd/$variant-dtb"
        [ -s "$kernel_patch" ] && [ -s "$dtb_patch" ] || {
            echo "Release lacks the $variant kernel/DTB patch" >&2
            exit 1
        }
        bspatch "$BASE_KERNEL" "$kernel" "$kernel_patch"
        bspatch "$BASE_DTB" "$dtb" "$dtb_patch"
    fi

    python3 "$ROOT_DIR/tools/validate_dtb.py" "$dtb" "$variant"
    "$ROOT_DIR/scripts/extract-ikconfig" "$kernel" > "$TMP_DIR/$variant.config"
    config="$TMP_DIR/$variant.config"

    grep -q '^CONFIG_EROFS_FS=y$' "$config"
    grep -q '^CONFIG_EROFS_FS_ZIP=y$' "$config"
    grep -q '^CONFIG_DEVTMPFS=y$' "$config"
    if [ "$EXPECT_KSU" = y ]; then
        grep -q '^CONFIG_KSU=y$' "$config"
    else
        grep -q '^# CONFIG_KSU is not set$' "$config"
    fi
    if [ "$EXPECT_PERMISSIVE" = y ]; then
        grep -q '^CONFIG_ALWAYS_PERMISSIVE=y$' "$config"
    else
        grep -q '^# CONFIG_ALWAYS_PERMISSIVE is not set$' "$config"
    fi

    echo "OK $variant: kernel config EROFS/KSU/SELinux profile"
done

UPDATE_BINARY="$TMP_DIR/package/META-INF/com/google/android/update-binary"
[ -s "$UPDATE_BINARY" ] || {
    echo "Release lacks update-binary" >&2
    exit 1
}
if grep -q 'fkv' "$UPDATE_BINARY"; then
    echo "Release update-binary still contains the unresolved fkv placeholder" >&2
    exit 1
fi

sha256sum "$ZIP_PATH"
echo "OK release: $(basename "$ZIP_PATH")"
