import argparse
import os
import subprocess
import sys
from pathlib import Path

from self_tester import run_suite

def main():
    parser = argparse.ArgumentParser(
        description="Self Tester Automation - Run Ansible based test cases."
    )
    parser.add_argument(
        "target", 
        help="A specific .json test file to run (via ansible), or a folder containing multiple tests (via suite runner)."
    )
    parser.add_argument("--report", default=None, help="Report output path (suite only)")
    parser.add_argument("--config", default=None, help="Path to databases.yml (suite only)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (suite only)")
    
    args = parser.parse_args()
    target_path = Path(args.target).resolve()
    
    if not target_path.exists():
        print(f"Error: Target not found: {target_path}")
        sys.exit(1)
        
    if target_path.is_file() and target_path.suffix == '.json':
        # Single test case via ansible-playbook
        run_single_test(target_path)
    elif target_path.is_dir():
        # Directory of test cases via run_suite
        # We rewrite sys.argv for the run_suite module
        sys.argv = ['self-tester', str(target_path)]
        if args.report:
            sys.argv.extend(['--report', args.report])
        if args.config:
            sys.argv.extend(['--config', args.config])
        if args.quiet:
            sys.argv.append('--quiet')
            
        run_suite.main()
    else:
        print(f"Error: Target {target_path} is neither a .json file nor a directory.")
        sys.exit(1)


def run_single_test(test_case_path: Path):
    try:
        import importlib.resources
        playbook_dir = importlib.resources.files('self_tester.ansible.playbooks')
        playbook_path = playbook_dir.joinpath('run_test_case.yml')
        lib_path = importlib.resources.files('self_tester.ansible').joinpath('library')
        roles_path = importlib.resources.files('self_tester.ansible').joinpath('roles')
    except (AttributeError, ImportError):
        # Fallback for Python < 3.9
        base_dir = Path(__file__).parent / 'ansible'
        playbook_path = base_dir / 'playbooks' / 'run_test_case.yml'
        lib_path = base_dir / 'library'
        roles_path = base_dir / 'roles'
        
    env = os.environ.copy()
    
    # Prepend our library path to ANSIBLE_LIBRARY
    if 'ANSIBLE_LIBRARY' in env:
        env['ANSIBLE_LIBRARY'] = f"{lib_path}:{env['ANSIBLE_LIBRARY']}"
    else:
        env['ANSIBLE_LIBRARY'] = str(lib_path)
        
    # Prepend our roles path to ANSIBLE_ROLES_PATH
    if 'ANSIBLE_ROLES_PATH' in env:
        env['ANSIBLE_ROLES_PATH'] = f"{roles_path}:{env['ANSIBLE_ROLES_PATH']}"
    else:
        env['ANSIBLE_ROLES_PATH'] = str(roles_path)

    cmd = [
        "ansible-playbook", 
        str(playbook_path), 
        "-e", f"test_case_path={test_case_path}"
    ]
    
    # We must run it from the directory of the target or workspace so relative paths in tests work.
    # The original script ran from project root. Let's run from cwd.
    sys.exit(subprocess.call(cmd, env=env))


if __name__ == "__main__":
    main()
