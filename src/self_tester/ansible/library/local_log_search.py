#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for searching log files by pattern.
Supports glob file patterns (e.g. /path/to/data.log*) and plain/regex search patterns.
"""

from ansible.module_utils.basic import AnsibleModule
import glob
import re
import os


def expand_files(file_pattern):
    """Expand glob pattern to list of matching file paths (sorted)."""
    expanded = glob.glob(os.path.expanduser(file_pattern))
    return sorted(expanded)


def search_file(filepath, search_pattern, use_regex):
    """Search file for matching lines. Returns list of (line_num, line_text)."""
    matches = []
    try:
        with open(filepath, 'r', errors='replace') as f:
            for i, line in enumerate(f, 1):
                line = line.rstrip('\n\r')
                if use_regex:
                    if re.search(search_pattern, line):
                        matches.append({'line_num': i, 'line': line})
                else:
                    if search_pattern in line:
                        matches.append({'line_num': i, 'line': line})
    except (OSError, IOError) as e:
        return {'error': str(e), 'matches': []}
    return {'matches': matches}


def main():
    module = AnsibleModule(
        argument_spec=dict(
            file_pattern=dict(type='str', required=True),
            search_pattern=dict(type='str', required=True),
            use_regex=dict(type='bool', required=False, default=False),
        ),
        supports_check_mode=False
    )

    file_pattern = module.params['file_pattern']
    search_pattern = module.params['search_pattern']
    use_regex = module.params['use_regex']

    files = expand_files(file_pattern)
    if not files:
        module.fail_json(msg=f"No files match pattern: {file_pattern}")

    results = []
    total_matches = 0

    for filepath in files:
        if not os.path.isfile(filepath):
            continue
        result = search_file(filepath, search_pattern, use_regex)
        if 'error' in result:
            module.fail_json(msg=f"Error reading {filepath}: {result['error']}")
        matches = result['matches']
        total_matches += len(matches)
        results.append({
            'file': filepath,
            'match_count': len(matches),
            'matches': matches
        })

    module.exit_json(
        changed=False,
        file_pattern=file_pattern,
        search_pattern=search_pattern,
        files_searched=len(results),
        total_matches=total_matches,
        results=results
    )


if __name__ == '__main__':
    main()
