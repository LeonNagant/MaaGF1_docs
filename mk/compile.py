import os
import markdown
from weasyprint import HTML, CSS
import shutil

# Root dir
SOURCE_DIR = "."
# PDF output dir
OUTPUT_DIR = "dist"
# Ignore dir
IGNORE_DIRS = {".git", ".github", "mk", "dist"}
# Ignore File
IGNORE_FILES = {"README.md", "ref.md", "LICENSE"}

# CSS config for "compile" markdown
PDF_CSS = CSS(string="""
    @page { size: A4; margin: 2cm; }
    body { font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: 14px; line-height: 1.6; }
    h1, h2, h3 { color: #333; }
    img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
    code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 4px; font-family: monospace; }
    pre { background-color: #f4f4f4; padding: 1em; border-radius: 4px; overflow-x: auto; }
    blockquote { border-left: 4px solid #ddd; padding-left: 1em; color: #666; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background-color: #f2f2f2; }
""")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def convert_md_to_pdf(file_path, output_path, base_path):
    """
    Convert a single MD file to PDF
    file_path: Path to the MD file
    output_path: Path to the PDF output
    base_path: Base directory used to parse relative paths of images (usually the directory where the MD file is located)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        # 1. Markdown -> HTML
        html_body = markdown.markdown(text, extensions=['tables', 'fenced_code'])

        # 2. HTML Struct
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body>
        {html_body}
        </body>
        </html>
        """

        # 3. HTML -> PDF
        HTML(string=html_content, base_url=base_path).write_pdf(output_path, stylesheets=[PDF_CSS])
        
        print(f"[Success] Generated: {output_path}")
        return True
    except Exception as e:
        print(f"[Error] Failed to convert {file_path}: {e}")
        return False

def main():
    # Clean and rebuild the output directory
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    ensure_dir(OUTPUT_DIR)

    print("Starting PDF compilation...")

    # Traversing the directory
    for root, dirs, files in os.walk(SOURCE_DIR):
        # Filter out directories to ignore (modifying the dirs list will affect subsequent traversals of os.walk)
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if file.endswith(".md") and file not in IGNORE_FILES:
                
                # Full path of source file
                source_path = os.path.join(root, file)
                
                # Calculate relative paths to preserve directory structure in dist
                rel_path = os.path.relpath(root, SOURCE_DIR)
                
                # target folder path
                target_dir = os.path.join(OUTPUT_DIR, rel_path)
                ensure_dir(target_dir)
                
                # Target PDF file name
                pdf_filename = os.path.splitext(file)[0] + ".pdf"
                target_path = os.path.join(target_dir, pdf_filename)

                # Convert pic path in md file
                convert_md_to_pdf(source_path, target_path, root)

    print("Compilation finished.")

if __name__ == "__main__":
    main()