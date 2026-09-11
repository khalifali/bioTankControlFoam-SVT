#!/usr/bin/env python3
"""Print exact OBJ surface bounds/groups from the installed upstream tutorial."""
import os
from pathlib import Path

root = Path(os.environ['WM_PROJECT_DIR']) / 'tutorials/multiphaseEuler/aeratedStirredTankMRF/constant/geometry'
for path in sorted(root.glob('*.obj')):
    vertices, groups = [], set()
    faces_by_group={}
    current='default'
    for line in path.read_text().splitlines():
        if line.startswith('v '):
            vertices.append(tuple(map(float, line.split()[1:4])))
        elif line.startswith(('g ', 'o ')):
            current=line[2:].strip()
            groups.add(current)
        elif line.startswith('f '):
            faces_by_group.setdefault(current,set()).update(
                int(v.split('/')[0])-1 for v in line.split()[1:])
    if vertices:
        low = tuple(min(v[i] for v in vertices) for i in range(3))
        high = tuple(max(v[i] for v in vertices) for i in range(3))
        print(path.name, 'bounds_m:', low, high, 'groups:', sorted(groups))
        for group,indices in faces_by_group.items():
            coords=[vertices[i] for i in indices]
            low=tuple(min(v[i] for v in coords) for i in range(3))
            high=tuple(max(v[i] for v in coords) for i in range(3))
            print('  group',group,'bounds_m:',low,high)
