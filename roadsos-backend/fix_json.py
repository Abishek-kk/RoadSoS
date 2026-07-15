import os
import re
import json

folder = r"f:\team_accalerate\roadsos-backend\data\hospitals"
for filename in os.listdir(folder):
    if filename.endswith('.json'):
        filepath = os.path.join(folder, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = re.sub(r'\]\s*\[', ',', content)
        
        try:
            data = json.loads(new_content)
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                print(f"Fixed and reformatted {filename}")
        except json.JSONDecodeError as e:
            print(f"Error parsing {filename}: {e}")
