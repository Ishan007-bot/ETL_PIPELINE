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
    try:
        if not text or not isinstance(text, str):
            return fragments
        
        # Try to find JSON objects
        json_object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_array_pattern = r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]'
        
        # Find JSON objects
        for match in re.finditer(json_object_pattern, text, re.DOTALL):
            try:
                json_str = match.group()
                # Strip single-line comments (// ...) from JSON before parsing
                # This handles JSON with comments that are common in scraped data
                json_str_cleaned = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
                # Also strip multi-line comments (/* ... */)
                json_str_cleaned = re.sub(r'/\*.*?\*/', '', json_str_cleaned, flags=re.DOTALL)
                # Remove trailing commas before closing braces/brackets (invalid JSON but common in scraped data)
                json_str_cleaned = re.sub(r',\s*}', '}', json_str_cleaned)
                json_str_cleaned = re.sub(r',\s*]', ']', json_str_cleaned)
                parsed = json.loads(json_str_cleaned)
                fragments.append({
                    "type": "json_object",
                    "content": parsed,
                    "offset": match.start(),
                    "length": len(match.group())
                })
            except (json.JSONDecodeError, ValueError, TypeError):
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
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    except Exception as e:
        # Log but don't fail - return empty list
        print(f"Error extracting JSON fragments: {e}")
    
    return fragments

def extract_html_tables(html_content: str) -> List[Dict[str, Any]]:
    """Extract HTML tables and convert to structured data."""
    tables = []
    try:
        if not html_content or not isinstance(html_content, str):
            return tables
        
        soup = BeautifulSoup(html_content, 'html.parser')
        for idx, table in enumerate(soup.find_all('table')):
            try:
                rows = []
                headers = []
                
                # Extract headers
                header_row = table.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
                # Extract data rows
                for tr in table.find_all('tr')[1:]:
                    try:
                        cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                        if cells:
                            if headers:
                                row_dict = dict(zip(headers, cells))
                            else:
                                row_dict = {f"col_{i}": cell for i, cell in enumerate(cells)}
                            rows.append(row_dict)
                    except Exception:
                        continue
                
                if rows:
                    tables.append({
                        "type": "html_table",
                        "content": rows,
                        "table_index": idx,
                        "headers": headers
                    })
            except Exception:
                continue
    except Exception as e:
        # Log but don't fail - return empty list
        print(f"Error extracting HTML tables: {e}")
    
    return tables

def extract_csv_sections(text: str) -> List[Dict[str, Any]]:
    """Extract CSV-like sections from text."""
    csv_sections = []
    try:
        if not text or not isinstance(text, str):
            return csv_sections
        
        # Look for lines that look like CSV (comma-separated, multiple columns)
        lines = text.split('\n')
        current_section = []
        in_csv_section = False
        
        for i, line in enumerate(lines):
            try:
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
            except Exception:
                continue
        
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
    except Exception as e:
        # Log but don't fail - return empty list
        print(f"Error extracting CSV sections: {e}")
    
    return csv_sections

def extract_key_value_pairs(text: str) -> List[Dict[str, Any]]:
    """Extract key-value pairs from text (various formats)."""
    kv_pairs = []
    try:
        if not text or not isinstance(text, str):
            return kv_pairs
        
        # Pattern 1: key: value
        pattern1 = r'([^\s:]+)\s*:\s*([^\n]+)'
        for match in re.finditer(pattern1, text):
            try:
                key = match.group(1).strip()
                value = match.group(2).strip()
                if key and value:
                    kv_pairs.append({
                        "type": "key_value",
                        "key": key,
                        "value": value,
                        "offset": match.start()
                    })
            except Exception:
                continue
        
        # Pattern 2: key=value
        pattern2 = r'([^\s=]+)\s*=\s*([^\n]+)'
        for match in re.finditer(pattern2, text):
            try:
                key = match.group(1).strip()
                value = match.group(2).strip()
                if key and value and key not in [kv["key"] for kv in kv_pairs]:
                    kv_pairs.append({
                        "type": "key_value",
                        "key": key,
                        "value": value,
                        "offset": match.start()
                    })
            except Exception:
                continue
    except Exception as e:
        # Log but don't fail - return empty list
        print(f"Error extracting key-value pairs: {e}")
    
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
    """Extract all fragment types from text and return summary.
    Always returns a valid structure, even if extraction fails completely.
    """
    try:
        if not text or not isinstance(text, str):
            # Return empty but valid structure
            return {
                "parsed_fragments_summary": {
                    "json_fragments": 0,
                    "html_tables": 0,
                    "csv_sections": 0,
                    "kv_pairs": 0,
                    "text_segments": 0
                },
                "fragments": {
                    "json": [],
                    "html_tables": [],
                    "csv": [],
                    "kv_pairs": [],
                    "text_segments": []
                },
                "documents": []
            }
        
        # Extract all fragment types (each function handles its own errors)
        json_frags = extract_json_fragments(text)
        html_tables = extract_html_tables(text)
        csv_sections = extract_csv_sections(text)
        kv_pairs = extract_key_value_pairs(text)
        text_segments = extract_raw_text_segments(text)
        
        # Flatten all extracted data into documents
        documents = []
        extracted_from_nested = False  # Track if we extracted from nested arrays
        
        # First pass: Check if we have structured JSON with nested arrays
        # OR product-like JSON objects (standalone records with common product fields)
        # This helps prioritize structured data, but we still extract from all sources
        has_structured_json = False
        has_product_like_json = False
        product_like_count = 0
        
        # Common product/entity field patterns that indicate structured data
        product_like_fields = ["product_id", "id", "name", "title", "price", "base_price", "status", "sku"]
        
        for frag in json_frags:
            content = frag.get("content")
            if isinstance(content, dict):
                # Check if this JSON object has nested arrays we should extract from
                if any(field in content and isinstance(content[field], list) 
                       for field in ["documents", "items", "data", "results", "records", "products", "entities"]):
                    has_structured_json = True
                    extracted_from_nested = True
                    break
                # Check if this is a product-like JSON object (standalone record)
                # Count how many product-like fields it has
                product_field_count = sum(1 for field in product_like_fields if field in content)
                # If it has at least 2 product-like fields, consider it a product record
                if product_field_count >= 2:
                    has_product_like_json = True
                    product_like_count += 1
        
        # Add JSON fragments as documents
        # Extract from all sources - cleaning stage will filter noise and prioritize structured data
        for frag in json_frags:
            try:
                content = frag["content"]
                if isinstance(content, list):
                    # Extract all arrays - cleaning stage will filter noise
                    for item in content:
                        if isinstance(item, dict):
                            documents.append(item)
                        elif isinstance(item, str):
                            # Convert string to dict
                            documents.append({"_raw_content": item})
                elif isinstance(content, dict):
                    # Check for common nested array patterns (documents, items, data, results, records)
                    # These typically contain the actual records we want to extract
                    nested_array_fields = ["documents", "items", "data", "results", "records", "products", "entities"]
                    extracted_nested = False
                    
                    # If we detected structured JSON earlier, ONLY extract from nested arrays
                    # Skip all other JSON objects
                    if has_structured_json:
                        # Only process if this object has nested arrays
                        for field_name in nested_array_fields:
                            if field_name in content and isinstance(content[field_name], list):
                                # Extract items from nested array
                                for item in content[field_name]:
                                    if isinstance(item, dict):
                                        # Merge parent metadata (like "source") into each item if it's useful
                                        merged_item = item.copy()
                                        # Only add source if it's a meaningful field (not noise)
                                        if "source" in content and isinstance(content["source"], str):
                                            merged_item["_batch_source"] = content["source"]
                                        documents.append(merged_item)
                                        extracted_nested = True
                                        extracted_from_nested = True  # Mark that we extracted from nested
                        # NEVER add wrapper objects when we have structured JSON
                    elif has_product_like_json:
                        # If we detected product-like JSON, prioritize product-like objects
                        # But still extract other JSON - cleaning will filter noise
                        product_field_count = sum(1 for field in product_like_fields if field in content)
                        
                        # Check if this is a product-like object (has at least 2 product fields)
                        if product_field_count >= 2:
                            # Filter out wrapper objects
                            array_fields = [k for k, v in content.items() if isinstance(v, list)]
                            total_fields = len(content)
                            is_wrapper = len(array_fields) > 0 and total_fields <= 2
                            has_wrapper_field = any(field in content for field in nested_array_fields)
                            
                            if not is_wrapper and not has_wrapper_field:
                                documents.append(content)
                        else:
                            # Also extract non-product-like JSON - cleaning will filter if it's noise
                            array_fields = [k for k, v in content.items() if isinstance(v, list)]
                            total_fields = len(content)
                            is_wrapper = len(array_fields) > 0 and total_fields <= 2
                            has_wrapper_field = any(field in content for field in nested_array_fields)
                            
                            if not is_wrapper and not has_wrapper_field:
                                documents.append(content)
                    else:
                        # No structured JSON or product-like JSON found, process normally but still check for nested arrays
                        for field_name in nested_array_fields:
                            if field_name in content and isinstance(content[field_name], list):
                                # Extract items from nested array
                                for item in content[field_name]:
                                    if isinstance(item, dict):
                                        merged_item = item.copy()
                                        if "source" in content and isinstance(content["source"], str):
                                            merged_item["_batch_source"] = content["source"]
                                        documents.append(merged_item)
                                        extracted_nested = True
                                        extracted_from_nested = True
                        
                        # If we didn't extract from nested arrays, add the dict itself
                        # But filter out wrapper objects
                        if not extracted_nested:
                            array_fields = [k for k, v in content.items() if isinstance(v, list)]
                            total_fields = len(content)
                            is_wrapper = len(array_fields) > 0 and total_fields <= 2
                            has_wrapper_field = any(field in content for field in nested_array_fields)
                            
                            if not is_wrapper and not has_wrapper_field:
                                documents.append(content)
                elif isinstance(content, str):
                    # Extract string content - cleaning stage will filter noise
                    documents.append({"_raw_content": content})
            except Exception:
                continue
        
        # Add HTML table rows as documents
        # Extract from all sources - cleaning stage will filter noise
        if not extracted_from_nested:
            for table in html_tables:
                try:
                    for row in table["content"]:
                        if isinstance(row, dict):
                            documents.append(row)
                        else:
                            documents.append({"_raw_row": str(row)})
                except Exception:
                    continue
        
        # Add CSV rows as documents
        # Extract from all sources - cleaning stage will filter noise
        if not extracted_from_nested:
            for csv_section in csv_sections:
                try:
                    for row in csv_section["content"]:
                        if isinstance(row, dict):
                            documents.append(row)
                        else:
                            documents.append({"_raw_row": str(row)})
                except Exception:
                    continue
        
        # Add key-value pairs as documents
        # Extract from all sources - cleaning stage will filter noise
        if not extracted_from_nested:
            for kv in kv_pairs:
                try:
                    documents.append({kv["key"]: kv["value"]})
                except Exception:
                    continue
        
        # Add text segments as documents (only if we didn't extract from nested JSON or product-like JSON)
        if not extracted_from_nested and not has_product_like_json:
            for seg in text_segments:
                try:
                    documents.append({
                        "_text_segment": seg["content"],
                        "_segment_index": seg["segment_index"]
                    })
                except Exception:
                    continue
        
        # If no documents extracted, create at least one from raw text
        if len(documents) == 0 and text:
            documents.append({
                "_raw_text": text[:1000]  # First 1000 chars as fallback
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
    except Exception as e:
        # Ultimate fallback - return minimal valid structure
        print(f"Critical error in extract_all_fragments: {e}")
        return {
            "parsed_fragments_summary": {
                "json_fragments": 0,
                "html_tables": 0,
                "csv_sections": 0,
                "kv_pairs": 0,
                "text_segments": 0
            },
            "fragments": {
                "json": [],
                "html_tables": [],
                "csv": [],
                "kv_pairs": [],
                "text_segments": []
            },
            "documents": [{"_raw_text": str(text)[:1000] if text else "empty"}]
        }

