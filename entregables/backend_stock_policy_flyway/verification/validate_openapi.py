"""Controles locales de referencias, rutas y ejemplos; no sustituye un linter OAS."""
import json
import re
from pathlib import Path
import yaml
from jsonschema import Draft7Validator

root=Path(__file__).resolve().parents[1]
doc=yaml.safe_load((root/'openapi-stock-policy.yaml').read_text(encoding='utf-8'))
def resolve(ref):
    assert ref.startswith('#/')
    value=doc
    for token in ref[2:].split('/'):
        value=value[token.replace('~1','/').replace('~0','~')]
    return value
def walk(value):
    if isinstance(value,dict):
        if '$ref' in value: resolve(value['$ref'])
        for child in value.values():walk(child)
    elif isinstance(value,list):
        for child in value:walk(child)
walk(doc)
ids=[]
for path,item in doc['paths'].items():
    for method,op in item.items():
        ids.append(op['operationId'])
        params=[resolve(p['$ref']) if '$ref' in p else p for p in op['parameters']]
        assert set(re.findall(r'\{([^}]+)\}',path))=={p['name'] for p in params if p['in']=='path'}
        assert all(p.get('required') for p in params if p['in']=='path')
        assert op['responses']
assert len(ids)==len(set(ids))
validator=Draft7Validator(doc['components']['schemas']['Days'])
for v in ['0','15.0000','999999.9999']:assert validator.is_valid(v)
for v in ['-1','1.00001','NaN','1000000','1e3',15]:assert not validator.is_valid(v)
result={'yaml_loaded':True,'references_resolved':True,'path_parameters_checked':True,'unique_operation_ids':len(ids),'decimal_cases':9,'full_openapi_validator':False}
(root/'verification/openapi-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
