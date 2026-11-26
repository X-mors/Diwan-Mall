import sys, pickle, glob
sys.path.insert(0, '/home/user/Diwan-Mall/tools')
import snap
from snap import ar, figure, arch_draw, str_draw
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
OUT = '/mnt/project-files/diwan-questions/'

def box(ax, b, col='#ff00ff', lab=None, lw=2.2, fill=False):
    ax.add_patch(Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1], fill=fill, ec=col, fc=col if fill else 'none',
                           alpha=0.25 if fill else 1, lw=lw, zorder=20))
    if lab:
        ax.text(b[0], b[3]+0.15, ar(lab), color=col, fontsize=10, fontweight='bold', zorder=21)

def save(fig, name):
    fig.savefig(OUT + name, dpi=120, bbox_inches='tight'); plt.close(fig); print(name)

which = sys.argv[1:] or ['1','2','3','4','5','6','7','8']

if '1' in which:
    z = (-1, 26, 18, 40.5)
    fig, ax = figure(2, z); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax: box(a, (0.4, 30.6, 16.76, 34.9), '#ffb000', fill=True); box(a, (0.4, 30.6, 16.76, 34.9), '#e08000', 'Q1: no thickness number here')
    save(fig, 'Q1_north_strip.png')
if '2' in which:
    z = (3.5, 0.5, 15.8, 5.0)
    fig, ax = figure(2, z, k=1.4); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax:
        a.axhline(2.8, color='#e08000', lw=2, ls='--', zorder=19)
        a.text(4.0, 2.55, '35 / 20 edge', color='#e08000', fontsize=11, fontweight='bold', zorder=21)
        for b in [(4.84, 2.9, 6.7, 3.12), (9.07, 2.8, 9.54, 2.94), (13.4, 2.81, 14.98, 3.06)]: box(a, b, '#ff00ff')
    save(fig, 'Q2_wall_on_zone_edge.png')
if '3' in which:
    z = (0, 17.5, 8, 23.2)
    fig, ax = figure(2, z, k=1.3); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax: box(a, (1.32, 21.8, 5.22, 22.2), '#ff00ff', 'SW05'); box(a, (3.15, 18.65, 7.05, 19.05), '#ff00ff', 'SW06')
    save(fig, 'Q3a_shear_wall_thickness.png')
    z = (9.5, 24.3, 19.5, 30.2)
    fig, ax = figure(2, z, k=1.3); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax: box(a, (14.4, 28.6, 18.5, 29.0), '#ff00ff', 'SW02'); box(a, (10.55, 25.5, 14.65, 25.9), '#ff00ff', 'SW04')
    save(fig, 'Q3b_SW02_SW04.png')
if '4' in which:
    z = (-1, 33.5, 18, 40.5)
    fig, ax = figure(2, z); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax:
        for b, l in [((5.29, 35.54, 5.74, 37.94), 'C01'), ((16.31, 35.32, 16.76, 37.62), 'SW01'), ((1.5, 35.52, 2.4, 36.02), 'C02'), ((12.9, 35.33, 14.1, 35.93), 'C03')]:
            box(a, b, '#ff00ff', l)
    save(fig, 'Q4a_tr_elements_north.png')
    z = (-1, -2.2, 15, 4)
    fig, ax = figure(2, z); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax:
        for b, l in [((0.45, 1.8, 1.65, 2.4), 'C09'), ((4.97, 0.0, 5.47, 1.2), 'C10')]: box(a, b, '#ff00ff', l)
    save(fig, 'Q4b_tr_elements_south.png')
    z = (5.5, 10.8, 19, 19.5)
    fig, ax = figure(2, z); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    for a in ax:
        for b, l in [((17.34, 17.31, 17.82, 18.35), 'A'), ((8.96, 12.28, 9.46, 13.48), 'B'), ((6.44, 12.28, 7.04, 12.58), 'C')]: box(a, b, '#ff00ff', l)
    save(fig, 'Q4c_columns_only_in_structural.png')
if '5' in which:
    z = (8.5, 3, 16, 12.5)
    fig, ax = figure(1, z, k=1.4); arch_draw(ax[0], 6, z)
    save(fig, 'Q5_doors_windows.png')
if '6' in which:
    z = (-1.5, -2.5, 20.5, 40.5)
    fig, ax = figure(1, z, k=0.55); arch_draw(ax[0], 6, z, texts=False)
    save(fig, 'Q6_facade.png')
if '7' in which:
    b = pickle.load(open(glob.glob('/home/user/Diwan-Mall/output/plan/_cache/F09_*.pkl')[0], 'rb'))
    z = (-1.5, -3, 20.5, 40.5)
    fig, ax = figure(1, z, k=0.6); arch_draw(ax[0], 9, z)
    for p in b['walls']['planter_parapets']:
        ax[0].plot([p['x1'], p['x2']], [p['y1'], p['y2']], color='#ff00ff', lw=4, alpha=0.6, zorder=19)
    ax[0].text(-1, -2.6, 'magenta = planter parapets (MASS lines)', color='#ff00ff', fontsize=11, fontweight='bold')
    save(fig, 'Q7_planters_F09.png')

if '8' in which:
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.set_xlim(-1.2, 6.5); ax.set_ylim(-0.45, 3.75); ax.set_aspect('equal'); ax.axis('off')
    def slab(y0, t, lab):
        ax.add_patch(Rectangle((0, y0 - t), 6, t, fc='#bdbdbd', ec='k', hatch='//'))
        ax.add_patch(Rectangle((0, y0), 6, 0.10, fc='#fee391', ec='#b08000'))
        ax.text(6.1, y0 - t/2, lab, va='center', fontsize=9)
        ax.text(6.1, y0 + 0.05, 'finish 10 cm', va='center', fontsize=9, color='#b08000')
    slab(0.0, 0.20, 'slab 20 cm')
    slab(3.20, 0.20, 'slab 20 cm (ceiling)')
    ax.add_patch(Rectangle((1.5, 0.0), 0.25, 3.0, fc='#fdae61', ec='#d94801', alpha=0.8))
    ax.add_patch(Rectangle((3.8, 0.10), 0.25, 2.90, fc='#a1d99b', ec='#238b45', alpha=0.8))
    ax.annotate('', (1.0, 0.0), (1.0, 3.0), arrowprops=dict(arrowstyle='<->', color='#d94801'))
    ax.text(0.95, 1.5, '(A) from slab top = 3.00', rotation=90, va='center', ha='right', color='#d94801', fontsize=11)
    ax.annotate('', (4.4, 0.10), (4.4, 3.0), arrowprops=dict(arrowstyle='<->', color='#238b45'))
    ax.text(4.5, 1.5, '(B) from finish top = 2.90', rotation=90, va='center', color='#238b45', fontsize=11)
    ax.annotate('', (-0.5, 0.0), (-0.5, 3.2), arrowprops=dict(arrowstyle='<->'))
    ax.text(-0.55, 1.6, 'storey 3.20 slab top to slab top', rotation=90, va='center', ha='right', fontsize=10)
    ax.set_title('Q8: masonry height starts from where? (under a 20 cm slab)', fontsize=12)
    save(fig, 'Q8_masonry_start_level.png')

# ---- batch 2 (remaining questions, 2026-11-26 noon)
if '9' in which:      # lift front wall 0.30 + shaft plaster
    z = (9.3, 17.6, 15.5, 24.2)
    fig, ax = figure(2, z, k=1.4); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    save(fig, 'Q9_lift_front_wall.png')
if '10' in which:     # F02 'Waiting For The Update' area + terraces / MASS
    z = (-3, -4, 22, 42)
    fig, ax = figure(1, z, k=0.5); arch_draw(ax[0], 2, z)
    save(fig, 'Q10_F02_waiting_terraces.png')
if '11' in which:     # 0.40 drawn vs 0.30 built: what fills the 10 cm
    z = (0.5, 21.2, 6, 22.8)
    fig, ax = figure(2, z, k=2.6); arch_draw(ax[0], 6, z); str_draw(ax[1], 6, z)
    save(fig, 'Q11_shear_wall_gap.png')
