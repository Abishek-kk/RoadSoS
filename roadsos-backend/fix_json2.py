import os
import json

folder = r"f:\team_accalerate\roadsos-backend\data\hospitals"

for filename in os.listdir(folder):
    if not filename.endswith('.json'): continue
    filepath = os.path.join(folder, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try parsing normally first
    try:
        json.loads(content)
        continue
    except json.JSONDecodeError:
        pass
        
    objects = []
    parts = content.split('{"id":')
    for p in parts[1:]:
        p = '{"id":' + p
        depth = 0
        in_string = False
        escape = False
        obj_str = ""
        for char in p:
            obj_str += char
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        break
        try:
            obj = json.loads(obj_str)
            objects.append(obj)
        except json.JSONDecodeError:
            print(f"Failed to parse an object in {filename}")
            
    if objects:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(objects, f, indent=2)
        print(f"Fixed {filename} with {len(objects)} objects")
    else:
        print(f"Could not fix {filename}")
