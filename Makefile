# Makefile for LaTeX CV compilation and format conversion

# Variables
TEX_FILE = main.tex
PDF_FILE = main.pdf
DOCX_FILE = main.docx
LATEX_ENGINE = pdflatex

# Default target
all: pdf docx

# Generate PDF from LaTeX
pdf: $(PDF_FILE)

$(PDF_FILE): $(TEX_FILE)
	$(LATEX_ENGINE) $(TEX_FILE)
	$(LATEX_ENGINE) $(TEX_FILE)  # Run twice for proper references

# Quiet PDF generation for internal use
pdf-quiet: $(TEX_FILE)
	@$(LATEX_ENGINE) $(TEX_FILE) > /dev/null 2>&1
	@$(LATEX_ENGINE) $(TEX_FILE) > /dev/null 2>&1

# Generate DOCX from LaTeX using pandoc
docx: $(DOCX_FILE)

$(DOCX_FILE): $(TEX_FILE)
	@echo "Generating DOCX from LaTeX..."
	@# Create a pandoc-friendly LaTeX file by removing problematic packages and commands
	sed -e '/\\input{glyphtounicode}/d' \
		-e '/\\usepackage{fontawesome}/d' \
		-e '/\\usepackage{marvosym}/d' \
		-e '/\\usepackage{fancyhdr}/d' \
		-e '/\\usepackage{hyphenat}/d' \
		-e '/\\pdfgentounicode=1/d' \
		-e 's/\\faAt/Email:/g' \
		-e 's/\\faGithub/GitHub:/g' \
		-e 's/\\faLinkedinSquare/LinkedIn:/g' \
		$(TEX_FILE) > temp_main.tex
	pandoc temp_main.tex -o $(DOCX_FILE) \
		--from latex \
		--to docx \
		--standalone \
		--metadata title="Resume - Ray Yan" \
		--metadata author="Ray Yan (Kin Long Yan)"
	rm temp_main.tex
	@echo "DOCX generation completed!"

# Generate DOCX with better formatting (alternative method)
docx-enhanced: $(TEX_FILE)
	pandoc $(TEX_FILE) -o $(DOCX_FILE) \
		--from latex \
		--to docx \
		--standalone \
		--metadata title="Resume - Ray Yan" \
		--metadata author="Ray Yan (Kin Long Yan)" \
		--table-of-contents \
		--number-sections=false \
		--reference-doc=$(if $(wildcard reference.docx),reference.docx,)

# Clean generated files
clean:
	rm -f *.aux *.log *.out *.pdf *.docx

# Clean only auxiliary files (keep PDF and DOCX)
clean-aux:
	rm -f *.aux *.log *.out

# Force rebuild
rebuild: clean all

# Show help
help:
	@echo "Available targets:"
	@echo "  all          - Generate both PDF and DOCX (default)"
	@echo "  pdf          - Generate PDF from LaTeX"
	@echo "  docx         - Generate DOCX from LaTeX using pandoc"
	@echo "  docx-enhanced - Generate DOCX with enhanced formatting"
	@echo "  clean        - Remove all generated files"
	@echo "  clean-aux    - Remove only auxiliary files"
	@echo "  rebuild      - Clean and rebuild all files"
	@echo "  help         - Show this help message"

.PHONY: all pdf docx docx-enhanced clean clean-aux rebuild help