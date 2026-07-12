#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for generating test reports
"""

from ansible.module_utils.basic import AnsibleModule
import json
import csv
from datetime import datetime
from pathlib import Path


def generate_csv_report(test_results, output_path):
    """Generate CSV report with comparison columns"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        headers = [
            'Case',
            'Description',
            'Precondition Expected',
            'Precondition Actual',
            'Precondition Comparison',
            'Trigger Response',
            'Expected Status',
            'Actual Status',
            'Status Comparison',
            'Expected Response Body',
            'Actual Response Body',
            'Response Comparison',
            'Postcondition Result',
            'Postcondition Expected',
            'Postcondition Comparison',
            'Overall Result',
            'Remarks'
        ]
        writer.writerow(headers)
        
        # Write data rows
        for result in test_results:
            row = generate_csv_row(result)
            writer.writerow(row)


def generate_csv_row(result):
    """Generate a CSV row for a test result"""
    case_name = result.get('case', 'Unknown')
    description = result.get('description', '')
    task_outputs = result.get('task_outputs', {})
    task_results = result.get('task_results', {})
    
    # Find precondition tasks dynamically
    pre_check_tasks = [k for k in task_outputs.keys() if k.startswith('pre_') and 'check' in k.lower()]
    pre_verify_tasks = [k for k in task_outputs.keys() if k.startswith('pre_') and 'verify' in k.lower()]
    pre_check = task_outputs.get(pre_check_tasks[0] if pre_check_tasks else '', {})
    pre_verify = task_outputs.get(pre_verify_tasks[0] if pre_verify_tasks else '', {})
    
    precondition_expected = json.dumps(pre_verify.get('expected', '')) if pre_verify else ''
    precondition_actual = json.dumps(pre_check) if pre_check else ''
    precondition_comparison = 'OK' if pre_verify.get('match', False) else 'Mismatch' if pre_verify else ''
    
    # Find trigger task
    trigger_tasks = [k for k in task_outputs.keys() if k.startswith('trigger_')]
    trigger_output = task_outputs.get(trigger_tasks[0] if trigger_tasks else '', {})
    trigger_response = json.dumps(trigger_output.get('body', '')) if trigger_output else ''
    
    # Find postcondition verification tasks
    status_verify_tasks = [k for k in task_outputs.keys() if 'status' in k.lower() and 'verify' in k.lower()]
    body_verify_tasks = [k for k in task_outputs.keys() if 'body' in k.lower() and 'verify' in k.lower()]
    status_verify = task_outputs.get(status_verify_tasks[0] if status_verify_tasks else '', {})
    body_verify = task_outputs.get(body_verify_tasks[0] if body_verify_tasks else '', {})
    
    expected_status = status_verify.get('expected', '')
    actual_status = trigger_output.get('status_code', '')
    status_comparison = 'OK' if status_verify.get('match', False) else 'Mismatch' if status_verify else ''
    expected_body = json.dumps(body_verify.get('expected', '')) if body_verify else ''
    actual_body = json.dumps(trigger_output.get('body', '')) if trigger_output else ''
    response_comparison = 'OK' if body_verify.get('match', False) else 'Mismatch' if body_verify else ''
    
    # Find postcondition tasks
    post_check_tasks = [k for k in task_outputs.keys() if k.startswith('post_') and 'check' in k.lower()]
    post_verify_tasks = [k for k in task_outputs.keys() if k.startswith('post_') and 'verify' in k.lower()]
    post_check = task_outputs.get(post_check_tasks[0] if post_check_tasks else '', {})
    post_verify = task_outputs.get(post_verify_tasks[0] if post_verify_tasks else '', {})
    
    postcondition_result = json.dumps(post_check) if post_check else ''
    postcondition_expected = json.dumps(post_verify.get('expected', '')) if post_verify else ''
    postcondition_comparison = 'OK' if post_verify.get('match', False) else 'Mismatch' if post_verify else ''
    
    # Overall result
    overall_success = result.get('success', False)
    overall_result = 'PASS' if overall_success else 'FAIL'
    
    # Remarks
    errors = result.get('errors', [])
    if overall_success:
        remarks = 'All checks passed'
    elif errors:
        remarks = '; '.join(str(e) for e in errors[:3])  # Limit to first 3 errors
    else:
        remarks = 'Unknown error'
    
    return [
        case_name,
        description,
        precondition_expected,
        precondition_actual,
        precondition_comparison,
        trigger_response,
        str(expected_status),
        str(actual_status),
        status_comparison,
        expected_body,
        actual_body,
        response_comparison,
        postcondition_result,
        postcondition_expected,
        postcondition_comparison,
        overall_result,
        remarks
    ]


def main():
    module = AnsibleModule(
        argument_spec=dict(
            test_results=dict(type='list', required=True),
            output_path=dict(type='str', required=True),
        ),
        supports_check_mode=False
    )
    
    test_results = module.params['test_results']
    output_path = module.params['output_path']
    
    try:
        generate_csv_report(test_results, output_path)
        module.exit_json(changed=True, msg=f"CSV report generated at {output_path}")
    except Exception as e:
        module.fail_json(msg=f"Failed to generate report: {str(e)}")


if __name__ == '__main__':
    main()
