#!/usr/bin/env python3
"""Render actual expanded URDF geometry and check opposed gripper pad travel."""
import argparse
import itertools
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def transform(xyz='0 0 0', rpy='0 0 0'):
    r, p, y = map(float, rpy.split())
    rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    t = np.eye(4)
    t[:3, :3] = rz.dot(ry).dot(rx)
    t[:3, 3] = list(map(float, xyz.split()))
    return t


def origin(element):
    e = element.find('origin')
    return transform(**e.attrib) if e is not None else np.eye(4)


def box_vertices(size):
    return np.array(list(itertools.product(*[(-v / 2, v / 2) for v in size])))


def faces(geometry):
    box = geometry.find('box')
    if box is not None:
        v = box_vertices(list(map(float, box.get('size').split())))
        return [v[idx] for idx in ([0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
                                  [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3])]
    cylinder = geometry.find('cylinder')
    if cylinder is None:
        raise ValueError('Unsupported geometry')
    a = np.linspace(0, 2 * math.pi, 33)[:-1]
    r, h = float(cylinder.get('radius')), float(cylinder.get('length'))
    low = np.column_stack((r * np.cos(a), r * np.sin(a), np.full(32, -h / 2)))
    high = low.copy()
    high[:, 2] = h / 2
    return [low, high] + [np.array([low[i], low[(i+1) % 32], high[(i+1) % 32], high[i]])
                          for i in range(32)]


def points(t, vertices):
    return vertices.dot(t[:3, :3].T) + t[:3, 3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urdf')
    parser.add_argument('output')
    args = parser.parse_args()
    root = ET.parse(args.urdf).getroot()
    materials = {e.get('name'): list(map(float, e.find('color').get('rgba').split()))
                 for e in root.findall('material')}
    fixed = root.find("link[@name='marm_z1_gripper_stator']")
    mover = root.find("link[@name='marm_z1_gripper_mover']")
    hinge = root.find("joint[@name='marm_z1_gripper_joint']")
    mount = root.find("joint[@name='marm_z1_gripper_stator_joint']")
    assert hinge.get('type') == 'revolute'
    assert hinge.find('axis').get('xyz') == '0 1 0'
    assert abs(float(hinge.find('limit').get('lower')) + math.pi/2) < 1e-9
    assert float(hinge.find('limit').get('upper')) == 0
    pad_f = next(v for v in fixed.findall('visual') if v.find('material').get('name') == 'RubberBlack')
    pad_m = next(v for v in mover.findall('visual') if v.find('material').get('name') == 'RubberBlack')
    fv = box_vertices(list(map(float, pad_f.find('geometry/box').get('size').split())))
    mv = box_vertices(list(map(float, pad_m.find('geometry/box').get('size').split())))
    fixed_points = points(origin(pad_f), fv)
    gaps = []
    for q in np.linspace(0, -math.pi/2, 181):
        motion = transform(rpy='0 %s 0' % q)
        moving_points = points(origin(hinge).dot(motion).dot(origin(pad_m)), mv)
        gap = moving_points[:, 2].min() - fixed_points[:, 2].max()
        assert gap >= -1e-10, 'Pad penetrates fixed pad'
        gaps.append(gap)
    closed = points(origin(hinge).dot(origin(pad_m)), mv)
    assert abs(gaps[0]) < 1e-10
    assert np.allclose(closed[:, :2].min(0), fixed_points[:, :2].min(0))
    assert np.allclose(closed[:, :2].max(0), fixed_points[:, :2].max(0))
    print('PASS: 181 poses; pads contact at q=0 with matching footprint; no pad penetration.')
    print('PASS: local Y joint axis becomes tool Z after 90-degree mounting roll.')
    fig = plt.figure(figsize=(15, 5))
    for i, q in enumerate((0, -math.pi/4, -math.pi/2)):
        ax = fig.add_subplot(1, 3, i+1, projection='3d')
        # Frame is tool flange: local opening direction becomes lateral Y.
        base = origin(mount)
        for link, t in ((fixed, base), (mover, base.dot(origin(hinge)).dot(transform(rpy='0 %s 0' % q)))):
            for visual in link.findall('visual'):
                polygons = [points(t.dot(origin(visual)), face) for face in faces(visual.find('geometry'))]
                rgba = materials[visual.find('material').get('name')]
                ax.add_collection3d(Poly3DCollection(polygons, facecolor=rgba,
                                                     edgecolor=(0.1, 0.1, 0.1, .22), linewidth=.25))
        ax.set_xlim(.015, .215)
        ax.set_ylim(-.1, .1)
        ax.set_zlim(-.1, .1)
        ax.view_init(elev=68, azim=-76)
        ax.set_title('%s (%d deg)' % (('Closed', 'Half open', 'Fully open')[i], round(math.degrees(q))))
        ax.set_xlabel('Tool X (m)')
        ax.set_ylabel('Tool Y (m)')
        ax.set_zlabel('Tool Z (m)')
    fig.suptitle('Actual URDF geometry / lateral opening / offline preview (not RViz)')
    fig.tight_layout(rect=(0, 0, 1, .94))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    main()
