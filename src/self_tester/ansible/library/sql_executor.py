#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for executing SQL queries
"""

from ansible.module_utils.basic import AnsibleModule
import yaml
import json

J2_OPEN_PLACEHOLDER = '<<<J2OPEN>>>'
J2_CLOSE_PLACEHOLDER = '<<<J2CLOSE>>>'


def escape_jinja_in_value(obj):
    """Recursively escape {{ and }} in strings to prevent Ansible template recursion."""
    if isinstance(obj, dict):
        return {k: escape_jinja_in_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [escape_jinja_in_value(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace('{{', J2_OPEN_PLACEHOLDER).replace('}}', J2_CLOSE_PLACEHOLDER)
    return obj
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, date, timedelta
from decimal import Decimal


def load_config(config_file):
    """Load database configuration from YAML file"""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config


def get_db_connection(db_name, config_file):
    """Get database connection string from config"""
    config = load_config(config_file)
    
    # Support both old and new config formats
    if 'environments' in config:
        env_config = config['environments'].get('test', {})
        db_config = env_config.get('databases', {}).get(db_name)
    else:
        db_config = config.get('databases', {}).get(db_name)
    
    if not db_config:
        raise ValueError(f"Database '{db_name}' not found in config")
    
    if isinstance(db_config, dict):
        connection = db_config.get('connection')
    else:
        connection = db_config
    
    if not connection:
        raise ValueError(f"Connection string not found for database '{db_name}'")
    
    return connection


def execute_query(connection_string, query):
    """Execute SQL query and return results as JSON"""
    engine = create_engine(connection_string, pool_pre_ping=True)
    
    try:
        # Split by semicolon for multi-statement queries
        statements = [s.strip() for s in query.split(';') if s.strip()]
        
        with engine.connect() as conn:
            # Execute all statements except the last one (setup queries)
            for stmt in statements[:-1]:
                conn.execute(text(stmt))
            
            # Execute last statement and get result
            if statements:
                result = conn.execute(text(statements[-1]))
                
                # Check if it's a SELECT query
                if result.returns_rows:
                    rows = result.fetchall()
                    col_keys = list(result.keys())  # column names from result
                    
                    # Convert to list of dicts
                    if rows:
                        # Check if it's a COUNT query (single column, looks like count)
                        first_row = rows[0]
                        if len(first_row) == 1:
                            column_name = col_keys[0] if col_keys else 'count'
                            value = first_row[0]
                            if 'count' in column_name.lower() or isinstance(value, (int, type(None))):
                                return {column_name: int(value) if value is not None else 0}
                        
                        # Regular SELECT query - use column keys + positional index
                        def to_jsonable(val):
                            if val is None:
                                return None
                            if isinstance(val, (datetime, date)):
                                return val.isoformat()
                            if isinstance(val, timedelta):
                                return str(val)
                            if isinstance(val, Decimal):
                                return int(val) if val % 1 == 0 else float(val)
                            return val

                        result_list = []
                        for row in rows:
                            row_dict = {}
                            for i, key in enumerate(col_keys):
                                val = row[i] if i < len(row) else None
                                row_dict[key] = to_jsonable(val)
                            result_list.append(row_dict)
                        
                        return result_list
                    else:
                        return []
                else:
                    # Non-SELECT query (INSERT, UPDATE, DELETE)
                    conn.commit()
                    return {"affected_rows": result.rowcount}
            else:
                return None
    except SQLAlchemyError as e:
        raise Exception(f"SQL execution failed: {str(e)}")
    finally:
        engine.dispose()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            db_name=dict(type='str', required=True),
            query=dict(type='str', required=True),
            config_file=dict(type='str', required=True),
        ),
        supports_check_mode=False
    )
    
    db_name = module.params['db_name']
    query = module.params['query']
    config_file = module.params['config_file']
    
    try:
        connection_string = get_db_connection(db_name, config_file)
        result = execute_query(connection_string, query)
        result = escape_jinja_in_value(result) if result is not None else result
        module.exit_json(changed=False, result=result)
    except Exception as e:
        module.fail_json(msg=str(e))


if __name__ == '__main__':
    main()
