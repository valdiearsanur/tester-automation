#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for downloading files from an FTP/FTPS server.
"""

from ansible.module_utils.basic import AnsibleModule
import ftplib
import os
import yaml

def load_config(config_file):
    """Load configuration from YAML file"""
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

def get_ftp_config(config_name, config_file):
    """Get FTP config from config file"""
    config = load_config(config_file)
    
    # Support both old and new config formats
    if 'environments' in config:
        env_config = config['environments'].get('test', {})
        ftp_config = env_config.get('ftp', {}).get(config_name)
    else:
        ftp_config = config.get('ftp', {}).get(config_name)
        
    if not ftp_config:
        raise ValueError(f"FTP config '{config_name}' not found in config")
        
    return ftp_config

def main():
    module = AnsibleModule(
        argument_spec=dict(
            config_name=dict(type='str', required=False),
            config_file=dict(type='str', required=False),
            host=dict(type='str', required=False),
            port=dict(type='int', required=False),
            user=dict(type='str', required=False),
            password=dict(type='str', required=False, no_log=True),
            remote_path=dict(type='str', required=True),
            local_path=dict(type='str', required=True),
            secure=dict(type='bool', required=False, default=False),
        ),
        supports_check_mode=False
    )

    config_name = module.params.get('config_name')
    config_file = module.params.get('config_file')
    
    host = module.params.get('host')
    port = module.params.get('port') or 21
    user = module.params.get('user')
    password = module.params.get('password')
    remote_path = module.params.get('remote_path')
    local_path = module.params.get('local_path')
    secure = module.params.get('secure')

    if config_name and config_file:
        try:
            ftp_cfg = get_ftp_config(config_name, config_file)
            host = ftp_cfg.get('host', host)
            port = ftp_cfg.get('port', port)
            user = ftp_cfg.get('user', user)
            password = ftp_cfg.get('password', password)
            secure = ftp_cfg.get('secure', secure)
        except Exception as e:
            module.fail_json(msg=f"Failed to load config: {str(e)}")

    if not host or not user or not password:
        module.fail_json(msg="host, user, and password are required either directly or via config")

    try:
        if secure:
            ftp = ftplib.FTP_TLS()
            ftp.connect(host, port)
            ftp.login(user, password)
            ftp.prot_p()
        else:
            ftp = ftplib.FTP()
            ftp.connect(host, port)
            ftp.login(user, password)
            
        # Ensure local directory exists
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        
        with open(local_path, 'wb') as f:
            ftp.retrbinary(f'RETR {remote_path}', f.write)
            
        ftp.quit()
        
        size = os.path.getsize(local_path)
        module.exit_json(changed=True, downloaded=True, local_path=local_path, remote_path=remote_path, size=size)
        
    except Exception as e:
        module.fail_json(msg=f"FTP download failed: {str(e)}")

if __name__ == '__main__':
    main()
