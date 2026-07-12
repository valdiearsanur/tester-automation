#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for comparing JSON outputs
"""

from ansible.module_utils.basic import AnsibleModule
import json
from deepdiff import DeepDiff

J2_OPEN_PLACEHOLDER = '<<<J2OPEN>>>'
J2_CLOSE_PLACEHOLDER = '<<<J2CLOSE>>>'


def unescape_jinja_in_value(obj):
    """Restore {{ and }} that were escaped to avoid Ansible template recursion."""
    if isinstance(obj, dict):
        return {k: unescape_jinja_in_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [unescape_jinja_in_value(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace(J2_OPEN_PLACEHOLDER, '{{').replace(J2_CLOSE_PLACEHOLDER, '}}')
    return obj


def normalize_value(value):
    """Normalize value for comparison (handle type conversions)"""
    if value is None:
        return None
    
    # Convert numeric strings to numbers if possible
    if isinstance(value, str):
        # Try int first
        try:
            if '.' not in value:
                return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
    
    return value


def match_partial(expected, actual):
    """Check if expected dict is a subset of actual dict (partial matching)"""
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    
    for key, expected_value in expected.items():
        if key not in actual:
            return False
        
        actual_value = actual[key]
        
        # Normalize values for comparison
        expected_norm = normalize_value(expected_value)
        actual_norm = normalize_value(actual_value)
        
        # Handle None/null comparison
        if expected_norm is None and actual_norm is None:
            continue
        
        # Handle nested dicts
        if isinstance(expected_norm, dict) and isinstance(actual_norm, dict):
            if not match_partial(expected_norm, actual_norm):
                return False
        elif expected_norm != actual_norm:
            return False
    
    return True


def match_json(expected, actual, match_mode='partial'):
    """Match JSON values with full or partial matching"""
    actual_norm = normalize_value(actual)

    # Allow list of acceptable values (e.g. expected: [0, 190000012])
    if isinstance(expected, list) and not isinstance(actual, (list, dict)):
        expected_norm_list = [normalize_value(v) for v in expected]
        if actual_norm in expected_norm_list:
            return True, None
        return False, f"Actual {actual_norm} not in allowed values {expected_norm_list}"

    expected_norm = normalize_value(expected)

    # Handle None/null comparison
    if expected_norm is None and actual_norm is None:
        return True, None

    # Full match
    if match_mode == 'full':
        diff = DeepDiff(expected_norm, actual_norm, ignore_order=False)
        if diff:
            return False, str(diff)
        return True, None
    
    # Partial match
    if match_mode == 'partial':
        # Handle single object (partial matching)
        if isinstance(expected_norm, dict) and isinstance(actual_norm, dict):
            if match_partial(expected_norm, actual_norm):
                return True, None
            else:
                diff = DeepDiff(expected_norm, actual_norm, ignore_order=False)
                return False, f"Partial match failed: {str(diff)}"
        
        # Handle array comparison (order-insensitive)
        if isinstance(expected_norm, list) and isinstance(actual_norm, list):
            if len(expected_norm) != len(actual_norm):
                return False, f"Array length mismatch: expected {len(expected_norm)}, got {len(actual_norm)}"
            
            # Order-insensitive matching: for each expected row, find a matching actual row
            actual_matched = [False] * len(actual_norm)
            for i, expected_row in enumerate(expected_norm):
                matched = False
                for j, actual_row in enumerate(actual_norm):
                    if not actual_matched[j]:
                        if isinstance(expected_row, dict) and isinstance(actual_row, dict):
                            if match_partial(expected_row, actual_row):
                                actual_matched[j] = True
                                matched = True
                                break
                        elif expected_row == actual_row:
                            actual_matched[j] = True
                            matched = True
                            break
                
                if not matched:
                    return False, f"Row {i} mismatch: expected {expected_row} but no matching row found"
            
            return True, None
        
        # Fallback: exact comparison
        if expected_norm == actual_norm:
            return True, None
        else:
            diff = DeepDiff(expected_norm, actual_norm, ignore_order=False)
            return False, f"Match failed: {str(diff)}"
    
    return False, f"Unknown match_mode: {match_mode}"


def main():
    module = AnsibleModule(
        argument_spec=dict(
            source_task=dict(type='str', required=True),
            source_output_file=dict(type='path', required=False, default=None),
            task_outputs=dict(type='dict', required=False, default=None),
            task_outputs_json=dict(type='str', required=False, default=None),
            field=dict(type='str', required=False, default=None),
            expected=dict(type='raw', required=False, default=None),
            expected_output_file=dict(type='path', required=False, default=None),
            match_mode=dict(type='str', required=False, default='partial', choices=['full', 'partial']),
        ),
        supports_check_mode=False
    )
    
    source_task = module.params['source_task']
    source_output_file = module.params['source_output_file']
    task_outputs = module.params['task_outputs']
    task_outputs_json = module.params['task_outputs_json']
    field = module.params['field']
    expected = module.params['expected']
    expected_output_file = module.params['expected_output_file']
    match_mode = module.params['match_mode']
    
    # Load expected from reference task output file when expected_task/expected_output_file is set
    if expected_output_file:
        try:
            with open(expected_output_file, 'r') as f:
                expected = json.load(f)
        except FileNotFoundError:
            module.fail_json(msg=f"Expected task output file not found: {expected_output_file}")
        except json.JSONDecodeError as e:
            module.fail_json(msg=f"Invalid JSON in expected output: {e}")
    elif expected is None:
        module.fail_json(msg="Either expected or expected_output_file (for expected_task) is required")
    
    # Prefer file-based input to avoid Ansible template recursion
    if source_output_file:
        with open(source_output_file, 'r') as f:
            source_output = json.load(f)
    elif task_outputs is not None:
        if source_task not in task_outputs:
            module.fail_json(msg=f"Source task '{source_task}' not found in task_outputs")
        source_output = task_outputs[source_task]
    elif task_outputs_json:
        cleaned = task_outputs_json.replace('<<<J2OPEN>>>', '{{').replace('<<<J2CLOSE>>>', '}}')
        task_outputs = json.loads(cleaned)
        if source_task not in task_outputs:
            module.fail_json(msg=f"Source task '{source_task}' not found in task_outputs")
        source_output = task_outputs[source_task]
    else:
        module.fail_json(msg="One of source_output_file, task_outputs, or task_outputs_json is required")
    
    # Get specific field if requested (supports dotted path e.g. headers.X-Sp-Error)
    def normalize_header_key(k):
        """Normalize for comparison: lowercase, treat underscore same as hyphen."""
        return k.lower().replace('_', '-')

    def get_nested(obj, path):
        parts = path.split('.')
        for i, part in enumerate(parts):
            if not isinstance(obj, dict):
                return None
            # Case-insensitive key lookup when inside headers (HTTP header names vary; uri uses underscores)
            if i > 0 and parts[0].lower() == 'headers':
                part_norm = normalize_header_key(part)
                key = next((k for k in obj if normalize_header_key(k) == part_norm), None)
            else:
                key = part if part in obj else None
            if key is None:
                return None
            obj = obj[key]
        return obj

    if field:
        actual = get_nested(source_output, field)
        if actual is None:
            module.fail_json(msg=f"Field '{field}' not found in task '{source_task}' output")
    else:
        actual = source_output

    # Restore escaped {{/}} for accurate comparison
    actual = unescape_jinja_in_value(actual)
    
    # Handle JSON string expected values
    if isinstance(expected, str):
        try:
            # Handle CSV double-quote escaping
            expected_clean = expected.replace('""', '"')
            expected = json.loads(expected_clean)
        except json.JSONDecodeError:
            pass  # Keep as string if not JSON
    
    # Compare
    match, diff = match_json(expected, actual, match_mode)
    
    result = {
        'match': match,
        'match_mode': match_mode,
        'expected': expected,
        'actual': actual,
        'diff': diff if not match else None
    }
    
    if match:
        module.exit_json(changed=False, **result)
    else:
        module.fail_json(msg=f"JSON comparison failed: {diff}", **result)


if __name__ == '__main__':
    main()
