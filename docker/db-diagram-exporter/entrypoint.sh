#!/bin/sh
set -eu

OUTPUT_DIR="${OUTPUT_DIR:-/output}"
BASENAME="${BASENAME:-database_schema}"
SOURCE_DOT="${SOURCE_DOT:-/templates/database_schema.dot}"

mkdir -p "$OUTPUT_DIR"

DOT_PATH="$OUTPUT_DIR/$BASENAME.dot"
PNG_PATH="$OUTPUT_DIR/$BASENAME.png"
SVG_PATH="$OUTPUT_DIR/$BASENAME.svg"

cp "$SOURCE_DOT" "$DOT_PATH"
dot -Tpng "$DOT_PATH" -o "$PNG_PATH"
dot -Tsvg "$DOT_PATH" -o "$SVG_PATH"

printf 'Exported files:\n- %s\n- %s\n- %s\n' "$DOT_PATH" "$PNG_PATH" "$SVG_PATH"
