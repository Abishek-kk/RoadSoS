import json, os, glob
files = sorted(glob.glob('data/hospitals/*.json'))
for path in files:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json.load(f)
        print('OK', os.path.basename(path))
    except Exception as e:
        print('ERR', os.path.basename(path), '->', e)
