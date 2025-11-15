"""
File parsers for .txt, .pdf, and .md files.
"""
import os
from typing import Dict, Any, Optional
from PyPDF2 import PdfReader
import io

def parse_text_file(file_content: bytes, filename: str) -> Dict[str, Any]:
    """Parse .txt file and extract text content."""
    try:
        # Try UTF-8 first
        text = file_content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            # Fallback to latin-1
            text = file_content.decode('latin-1')
        except UnicodeDecodeError:
            # Last resort: ignore errors
            text = file_content.decode('utf-8', errors='ignore')
    
    return {
        "file_type": "text",
        "filename": filename,
        "content": text,
        "size": len(file_content)
    }

def parse_pdf_file(file_content: bytes, filename: str) -> Dict[str, Any]:
    """Parse .pdf file and extract text content."""
    try:
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        
        text_parts = []
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                text_parts.append({
                    "page": page_num + 1,
                    "text": text
                })
        
        # Combine all pages
        full_text = "\n\n".join([part["text"] for part in text_parts])
        
        return {
            "file_type": "pdf",
            "filename": filename,
            "content": full_text,
            "pages": len(reader.pages),
            "page_contents": text_parts,
            "size": len(file_content),
            "ocr_required": False  # PyPDF2 extracts text, not OCR
        }
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")

def parse_markdown_file(file_content: bytes, filename: str) -> Dict[str, Any]:
    """Parse .md file and extract content, including frontmatter and code blocks."""
    try:
        text = file_content.decode('utf-8')
    except UnicodeDecodeError:
        text = file_content.decode('utf-8', errors='ignore')
    
    # Extract frontmatter (YAML at the start)
    frontmatter = {}
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            try:
                # Simple key-value extraction for frontmatter (no yaml dependency)
                frontmatter_text = parts[1]
                for line in frontmatter_text.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
                text = parts[2]
            except:
                pass
    
    # Extract code blocks (may contain JSON, HTML, etc.)
    code_blocks = []
    import re
    code_block_pattern = r'```(\w+)?\n(.*?)```'
    for match in re.finditer(code_block_pattern, text, re.DOTALL):
        lang = match.group(1) or "unknown"
        code = match.group(2)
        code_blocks.append({
            "language": lang,
            "content": code,
            "offset": match.start()
        })
    
    return {
        "file_type": "markdown",
        "filename": filename,
        "content": text,
        "frontmatter": frontmatter,
        "code_blocks": code_blocks,
        "size": len(file_content)
    }

def parse_file(file_content: bytes, filename: str) -> Dict[str, Any]:
    """Parse file based on extension."""
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == '.txt':
        return parse_text_file(file_content, filename)
    elif ext == '.pdf':
        return parse_pdf_file(file_content, filename)
    elif ext == '.md':
        return parse_markdown_file(file_content, filename)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

