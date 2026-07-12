#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for cache operations (Redis)
"""

from ansible.module_utils.basic import AnsibleModule
import yaml
import json

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


def load_config(config_file):
    """Load cache configuration from YAML file"""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config


def get_cache_connection(cache_name, config_file):
    """Get cache connection config from config file"""
    config = load_config(config_file)
    
    # Support both old and new config formats
    if 'environments' in config:
        env_config = config['environments'].get('test', {})
        cache_config = env_config.get('cache', {}).get(cache_name)
    else:
        cache_config = config.get('cache', {}).get(cache_name)
    
    if not cache_config:
        raise ValueError(f"Cache '{cache_name}' not found in config")
    
    return cache_config


def cache_get(cache_config, key):
    """Get value from cache"""
    if not HAS_REDIS:
        raise ImportError("redis library not available")
    
    r = redis.Redis(
        host=cache_config.get('host', 'localhost'),
        port=cache_config.get('port', 6379),
        db=cache_config.get('db', 0),
        decode_responses=True
    )
    
    value = r.get(key)
    exists = value is not None
    
    # Try to parse as JSON
    if value:
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass  # Keep as string
    
    return {
        'value': value,
        'exists': exists
    }


def cache_set(cache_config, key, value):
    """Set value in cache"""
    if not HAS_REDIS:
        raise ImportError("redis library not available")
    
    r = redis.Redis(
        host=cache_config.get('host', 'localhost'),
        port=cache_config.get('port', 6379),
        db=cache_config.get('db', 0),
        decode_responses=True
    )
    
    # Convert value to JSON string if it's a dict/list
    if isinstance(value, (dict, list)):
        value_str = json.dumps(value)
    else:
        value_str = str(value)
    
    r.set(key, value_str)
    
    return {'success': True}


def cache_flush(cache_config):
    """
    Flush all keys in the cache.
    Uses FLUSHALL ASYNC because managed Redis (e.g. Elastic Redis) often disables
    FLUSHDB. FLUSHALL ASYNC is the supported variant for clearing cache.
    """
    if not HAS_REDIS:
        raise ImportError("redis library not available")

    r = redis.Redis(
        host=cache_config.get('host', 'localhost'),
        port=cache_config.get('port', 6379),
        db=cache_config.get('db', 0),
        decode_responses=True
    )

    # FLUSHALL ASYNC - works on managed Redis where FLUSHDB is disabled
    r.flushall(asynchronous=True)

    return {'success': True}


def main():
    module = AnsibleModule(
        argument_spec=dict(
            operation=dict(type='str', required=True, choices=['get', 'set', 'flush']),
            cache_name=dict(type='str', required=True),
            key=dict(type='str', required=False, default=None),
            value=dict(type='raw', required=False, default=None),
            config_file=dict(type='str', required=True),
        ),
        supports_check_mode=False
    )
    
    operation = module.params['operation']
    cache_name = module.params['cache_name']
    key = module.params['key']
    value = module.params['value']
    config_file = module.params['config_file']
    
    try:
        cache_config = get_cache_connection(cache_name, config_file)
        
        if operation == 'get':
            if key is None:
                module.fail_json(msg="key is required for get operation")
            result = cache_get(cache_config, key)
            module.exit_json(changed=False, **result)
        elif operation == 'set':
            if key is None:
                module.fail_json(msg="key is required for set operation")
            if value is None:
                module.fail_json(msg="value is required for set operation")
            result = cache_set(cache_config, key, value)
            module.exit_json(changed=True, **result)
        elif operation == 'flush':
            result = cache_flush(cache_config)
            module.exit_json(changed=True, **result)
    except Exception as e:
        module.fail_json(msg=str(e))


if __name__ == '__main__':
    main()
