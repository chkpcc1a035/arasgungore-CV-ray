#!/bin/bash

# Script to convert LaTeX CV to DOCX format on macOS
# Requires pandoc to be installed (brew install pandoc)

set -e  # Exit on any error

# Configuration
LATEX_FILE="main.tex"
OUTPUT_DOCX="main.docx"
TEMP_FILE="temp_conversion.tex"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}LaTeX to DOCX Converter${NC}"
echo "==============================="

# Check if pandoc is installed
if ! command -v pandoc &> /dev/null; then
    echo -e "${RED}Error: pandoc is not installed${NC}"
    echo "Install with: brew install pandoc"
    exit 1
fi

# Check if source LaTeX file exists
if [[ ! -f "$LATEX_FILE" ]]; then
    echo -e "${RED}Error: $LATEX_FILE not found${NC}"
    exit 1
fi

echo "✓ Found $LATEX_FILE"
echo "✓ pandoc is available"

# Create pandoc-friendly version by removing problematic packages and commands
echo -e "${YELLOW}Cleaning LaTeX file for pandoc compatibility...${NC}"

sed -e '/\\input{glyphtounicode}/d' \
    -e '/\\usepackage{fontawesome}/d' \
    -e '/\\usepackage{marvosym}/d' \
    -e '/\\usepackage{fancyhdr}/d' \
    -e '/\\usepackage{hyphenat}/d' \
    -e '/\\pdfgentounicode=1/d' \
    -e 's/\\faAt/Email:/g' \
    -e 's/\\faGithub/GitHub:/g' \
    -e 's/\\faLinkedinSquare/LinkedIn:/g' \
    "$LATEX_FILE" > "$TEMP_FILE"

echo "✓ Created temporary cleaned file: $TEMP_FILE"

# Convert to DOCX
echo -e "${YELLOW}Converting to DOCX...${NC}"

pandoc "$TEMP_FILE" -o "$OUTPUT_DOCX" \
    --from latex \
    --to docx \
    --standalone \
    --metadata title="Resume - Ray Yan" \
    --metadata author="Ray Yan (Kin Long Yan)"

# Clean up temporary file
rm "$TEMP_FILE"

# Check if output was created
if [[ -f "$OUTPUT_DOCX" ]]; then
    FILE_SIZE=$(ls -lh "$OUTPUT_DOCX" | awk '{print $5}')
    echo -e "${GREEN}✓ Success! Generated $OUTPUT_DOCX (${FILE_SIZE})${NC}"
    echo ""
    echo "You can now open the DOCX file with:"
    echo "  open $OUTPUT_DOCX"
    echo ""
    echo "Or view it in the terminal with:"
    echo "  brew install doxx && doxx $OUTPUT_DOCX"
else
    echo -e "${RED}Error: Failed to generate $OUTPUT_DOCX${NC}"
    exit 1
fi