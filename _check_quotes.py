import sys
with open('src/cogcore/cfs.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines, 1):
    q = line.count('"')
    if q % 2 != 0 and not line.strip().startswith('#'):
        print(f'Line {i}: odd quotes ({q}): {line.rstrip()[:100]}')
