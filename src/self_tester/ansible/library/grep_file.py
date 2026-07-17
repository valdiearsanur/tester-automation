#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for grepping lines in a specific file.
"""

from ansible.module_utils.basic import AnsibleModule
import re
import os

def main():
    module = AnsibleModule(
        argument_spec=dict(
            file_path=dict(type='str', required=True),
            search_pattern=dict(type='str', required=True),
            use_regex=dict(type='bool', required=False, default=False),
        ),
        supports_check_mode=False
    )

    file_path = module.params['file_path']
    search_pattern = module.params['search_pattern']
    use_regex = module.params['use_regex']

    if not os.path.isfile(file_path):
        module.fail_json(msg=f"File not found: {file_path}")

    matches = []
    try:
        with open(file_path, 'r', errors='replace') as f:
            for i, line in enumerate(f, 1):
                line = line.rstrip('\n\r')
                if use_regex:
                    if re.search(search_pattern, line):
                        matches.append({'line_num': i, 'line': line})
                else:
                    if search_pattern in line:
                        matches.append({'line_num': i, 'line': line})
    except Exception as e:
        module.fail_json(msg=f"Error reading {file_path}: {str(e)}")

    module.exit_json(
        changed=False,
        file_path=file_path,
        search_pattern=search_pattern,
        total_matches=len(matches),
        matches=matches
    )

if __name__ == '__main__':
    main()
