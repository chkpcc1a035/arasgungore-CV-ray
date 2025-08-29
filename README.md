# arasgungore-CV

My curriculum vitae (CV) written using LaTeX. In my CV, you may find my contact information, websites, education, experience, achievements, projects, and skills.

Please find attached my [CV](https://drive.google.com/file/d/1TGwMpZl6FDeQk1w_-EetbspCuzu16kCF/view?usp=sharing). 😜



## Build Instructions

### Generate PDF
```sh
# Using LaTeX directly
pdflatex main.tex

# Using Makefile
make pdf
```

### Generate DOCX
```sh
# Using the conversion script (recommended)
./convert_to_docx.sh

# Using Makefile
make docx

# Direct pandoc conversion (after installing: brew install pandoc)
pandoc main.tex -o main.docx --from latex --to docx --standalone
```

### Generate Both PDF and DOCX
```sh
make all
```

### Requirements
- **For PDF generation**: LaTeX distribution (e.g., MacTeX on macOS)
- **For DOCX generation**: [Pandoc](https://pandoc.org/) - Install with `brew install pandoc`



## Screenshots

<p align="center">
    <img alt="Screenshot" src="https://raw.githubusercontent.com/arasgungore/arasgungore-CV/main/jpg/CV_page_1.jpg" width="400">
    <img alt="Screenshot" src="https://raw.githubusercontent.com/arasgungore/arasgungore-CV/main/jpg/CV_page_2.jpg" width="400">
</p>



## Author

👤 **Aras Güngöre**

* LinkedIn: [@arasgungore](https://www.linkedin.com/in/arasgungore)
* GitHub: [@arasgungore](https://github.com/arasgungore)
