"""
Multi-format extractors for parsing different content types from files.
"""
import json
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO

def extract_json_fragments(text: str) -> List[Dict[str, Any]]:
    """Extract JSON objects and arrays from text."""
    fragments = []
    # Try to find JSON objects
    json_object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_array_pattern = r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]'
    
    # Find JSON objects
    for match in re.finditer(json_object_pattern, text, re.DOTALL):
        try:
            parsed = json.loads(match.group())
            fragments.append({
                "type": "json_object",
                "content": parsed,
                "offset": match.start(),
                "length": len(match.group())
            })
        except json.JSONDecodeError:
            continue
    
    # Find JSON arrays
    for match in re.finditer(json_array_pattern, text, re.DOTALL):
        try:
            parsed = json.loads(match.group())
            fragments.append({
                "type": "json_array",
                "content": parsed,
                "offset": match.start(),
                "length": len(match.group())
            })
        except json.JSONDecodeError:
            continue
    
    return fragments

def extract_html_tables(html_content: str) -> List[Dict[str, Any]]:
    """Extract HTML tables and convert to structured data."""
    tables = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for idx, table in enumerate(soup.find_all('table')):
            rows = []
            headers = []
            
            # Extract headers
            header_row = table.find('tr')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # Extract data rows
            for tr in table.find_all('tr')[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if cells:
                    if headers:
                        row_dict = dict(zip(headers, cells))
                    else:
                        row_dict = {f"col_{i}": cell for i, cell in enumerate(cells)}
                    rows.append(row_dict)
            
            if rows:
                tables.append({
                    "type": "html_table",
                    "content": rows,
                    "table_index": idx,
                    "headers": headers
                })
    except Exception as e:
        print(f"Error extracting HTML tables: {e}")
    
    return tables

def extract_csv_sections(text: str) -> List[Dict[str, Any]]:
    """Extract CSV-like sections from text."""
    csv_sections = []
    # Look for lines that look like CSV (comma-separated, multiple columns)
    lines = text.split('\n')
    current_section = []
    in_csv_section = False
    
    for i, line in enumerate(lines):
        # Check if line looks like CSV (has commas and multiple fields)
        if ',' in line and len(line.split(',')) >= 2:
            current_section.append(line)
            in_csv_section = True
        else:
            if in_csv_section and len(current_section) >= 2:
                # Try to parse as CSV
                try:
                    csv_text = '\n'.join(current_section)
                    df = pd.read_csv(StringIO(csv_text))
                    csv_sections.append({
                        "type": "csv",
                        "content": df.to_dict('records'),
                        "start_line": i - len(current_section),
                        "end_line": i - 1
                    })
                except Exception:
                    pass
                current_section = []
                in_csv_section = False
            else:
                current_section = []
                in_csv_section = False
    
    # Handle CSV section at end of file
    if in_csv_section and len(current_section) >= 2:
        try:
            csv_text = '\n'.join(current_section)
            df = pd.read_csv(StringIO(csv_text))
            csv_sections.append({
                "type": "csv",
                "content": df.to_dict('records'),
                "start_line": len(lines) - len(current_section),
                "end_line": len(lines) - 1
            })
        except Exception:
            pass
    
    return csv_sections

def extract_key_value_pairs(text: str) -> List[Dict[str, Any]]:
    """Extract key-value pairs from text (various formats)."""
    kv_pairs = []
    
    # Pattern 1: key: value
    pattern1 = r'([^\s:]+)\s*:\s*([^\n]+)'
    for match in re.finditer(pattern1, text):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key and value:
            kv_pairs.append({
                "type": "key_value",
                "key": key,
                "value": value,
                "offset": match.start()
            })
    
    # Pattern 2: key=value
    pattern2 = r'([^\s=]+)\s*=\s*([^\n]+)'
    for match in re.finditer(pattern2, text):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key and value and key not in [kv["key"] for kv in kv_pairs]:
            kv_pairs.append({
                "type": "key_value",
                "key": key,
                "value": value,
                "offset": match.start()
            })
    
    return kv_pairs

def extract_raw_text_segments(text: str, min_length: int = 50) -> List[Dict[str, Any]]:
    """Extract raw text segments (paragraphs, sentences)."""
    segments = []
    # Split by double newlines (paragraphs)
    paragraphs = text.split('\n\n')
    
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if len(para) >= min_length:
            # Skip if it looks like structured data
            if not (',' in para and len(para.split(',')) > 3):
                segments.append({
                    "type": "raw_text",
                    "content": para,
                    "segment_index": i,
                    "length": len(para)
                })
    
    return segments

def extract_all_fragments(text: str) -> Dict[str, Any]:
    """Extract all fragment types from text and return summary."""
    json_frags = extract_json_fragments(text)
    html_tables = extract_html_tables(text)
    csv_sections = extract_csv_sections(text)
    kv_pairs = extract_key_value_pairs(text)
    text_segments = extract_raw_text_segments(text)
    
    # Flatten all extracted data into documents
    documents = []
    
    # Add JSON fragments as documents
    for frag in json_frags:
        if isinstance(frag["content"], list):
            documents.extend(frag["content"])
        else:
            documents.append(frag["content"])
    
    # Add HTML table rows as documents
    for table in html_tables:
        documents.extend(table["content"])
    
    # Add CSV rows as documents
    for csv_section in csv_sections:
        documents.extend(csv_section["content"])
    
    # Add key-value pairs as documents
    for kv in kv_pairs:
        documents.append({kv["key"]: kv["value"]})
    
    # Add text segments as documents (with metadata)
    for seg in text_segments:
        documents.append({
            "_text_segment": seg["content"],
            "_segment_index": seg["segment_index"]
        })
    
    return {
        "parsed_fragments_summary": {
            "json_fragments": len(json_frags),
            "html_tables": len(html_tables),
            "csv_sections": len(csv_sections),
            "kv_pairs": len(kv_pairs),
            "text_segments": len(text_segments)
        },
        "fragments": {
            "json": json_frags,
            "html_tables": html_tables,
            "csv": csv_sections,
            "kv_pairs": kv_pairs,
            "text_segments": text_segments
        },
        "documents": documents
    }

