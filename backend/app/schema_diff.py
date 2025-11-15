from typing import Dict, Any
from dataclasses import dataclass

# thresholds (tuneable)
ADDED_MAJOR_PCT = 0.10         # added field >=10% of sample -> major
REMOVED_MAJOR_PRESENCE = 0.20  # field historically present >=20% -> removal considered major
TYPE_SHIFT_MAJOR_PCT = 0.50    # new dominant type >=50% of sample -> major

@dataclass
class Diff:
    added: dict
    removed: dict
    changed: dict

class _Decision:
    def __init__(self, create_new):
        self.create_new_version = create_new

class DriftDecision:
    @staticmethod
    def evaluate(diff: "Diff", sample, old_field_stats=None):
        sample_n = len(sample)
        if sample_n == 0:
            return _Decision(False)
        
        # Removed fields: major if historically common
        for f in (diff.removed or {}):
            prev_presence = old_field_stats.get(f, {}).get("present_pct", 1.0) if old_field_stats else 1.0
            if prev_presence >= REMOVED_MAJOR_PRESENCE:
                return _Decision(True)
        
        # Added fields: check present fraction if available
        for k, v in (diff.added or {}).items():
            present = v.get("present_in", v.get("count", 0))
            if present >= max(1, int(ADDED_MAJOR_PCT * sample_n)):
                return _Decision(True)
        
        # Type changes: check new dominant pct if present
        for k, v in (diff.changed or {}).items():
            new_dom_pct = v.get("new_dom_pct", 1.0)
            if new_dom_pct >= TYPE_SHIFT_MAJOR_PCT:
                return _Decision(True)
        
        return _Decision(False)

def compute_schema_diff(old_schema: Dict[str, Any], new_schema: Dict[str, Any], field_stats=None, latest_meta=None):
    if not old_schema:
        props = new_schema.get("properties", {}) if new_schema else {}
        added = {}
        for k in props:
            added[k] = {
                "new": props[k],
                "present_in": field_stats.get(k, {}).get("present", 0) if field_stats else None
            }
        return Diff(added=added, removed={}, changed={})
    
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    
    added = {}
    removed = {}
    changed = {}
    
    for k in new_props:
        if k not in old_props:
            added[k] = {
                "new": new_props[k],
                "present_in": field_stats.get(k, {}).get("present", 0) if field_stats else 0
            }
        else:
            if old_props[k] != new_props[k]:
                # compute new dominant type pct using field_stats if available
                new_dom_pct = None
                if field_stats and k in field_stats:
                    tc = field_stats[k].get("type_counts", {})
                    total = sum(tc.values())
                    if total > 0:
                        new_type = max(tc, key=lambda x: tc[x])
                        new_dom_pct = tc[new_type] / total
                
                changed[k] = {
                    "old": old_props[k],
                    "new": new_props[k],
                    "new_dom_pct": new_dom_pct
                }
    
    for k in old_props:
        if k not in new_props:
            removed[k] = {
                "old": old_props[k],
                "prev_presence": latest_meta.get("field_stats", {}).get(k, {}).get("present_pct") if latest_meta else None
            }
    
    return Diff(added=added, removed=removed, changed=changed)
