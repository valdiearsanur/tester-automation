#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for listing files on an FTP/FTPS server.
"""

from ansible.module_utils.basic import AnsibleModule
import ftplib
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
            path=dict(type='str', required=False, default='.'),
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
    path = module.params.get('path')
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
        
        ftp.cwd(path)
        
        # Using MLSD if supported, else fallback to NLIST/DIR
        files = []
        try:
            for name, facts in ftp.mlsd():
                file_info = {'name': name}
                file_info.update(facts)
                files.append(file_info)
        except ftplib.error_perm:
            # Fallback to simple list if MLSD is not supported
            names = ftp.nlst()
            for name in names:
                files.append({'name': name})
                
        ftp.quit()
        
        module.exit_json(changed=False, files=files, path=path)
        
    except Exception as e:
        module.fail_json(msg=f"FTP list failed: {str(e)}")

if __name__ == '__main__':
    main()
