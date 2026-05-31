"""
scripts/generate_evolution_graph.py
Generates a stunning visualization of MACCREv2's development timeline.
Maps 'Complexity' and 'Operational Accuracy' over distinct epochs.
"""
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import make_interp_spline

# Output path
out_path = r"C:\Users\wilke\.gemini\antigravity\brain\d5db0fd2-5561-4d9e-93e4-f55a19512691\maccre_evolution.png"

# Epochs (X-axis)
epochs = [
    "I. GUI Era\n(Mid March)", 
    "II. Decapitation\n(Early April)", 
    "III. Telemetry Injection\n(April 4)", 
    "IV. Modular Arc\n(April 5-7)", 
    "V. Failsafe Hardening\n(Mid April)", 
    "VI. Phase 0 Victory\n(Current)"
]
x = np.arange(len(epochs))

# Complexity Data points (Conceptual)
# GUI -> high initially, Headless sever -> spikes as we rewrite, Telemetry -> huge bell curve, Modular -> levels off, Current -> structured but high
complexity = np.array([40, 60, 95, 75, 80, 85])

# Operational Accuracy Data points (Conceptual)
# Starts okay, Plunges during decapitation, Crashy during telemetry, Recovers during Modular, Shoots to double positive expansion now
accuracy = np.array([10, -50, -80, -10, 40, 95])

# Smooth interpolation
x_smooth = np.linspace(x.min(), x.max(), 300)
spl_c = make_interp_spline(x, complexity, k=3)
y_comp_smooth = spl_c(x_smooth)

spl_a = make_interp_spline(x, accuracy, k=3)
y_acc_smooth = spl_a(x_smooth)

# Plot Styling
plt.style.use('dark_background')
fig, ax1 = plt.subplots(figsize=(12, 7), dpi=150)
fig.patch.set_facecolor('#0d1117')
ax1.set_facecolor('#0d1117')

# Title
plt.title("MACCREv2 Architectural Evolution\nComplexity vs. Operational Accuracy", fontsize=18, fontweight='bold', color='#e6edf3', pad=20)

# X-Axis
ax1.set_xticks(x)
ax1.set_xticklabels(epochs, fontsize=10, color='#8b949e', fontweight='bold')
ax1.tick_params(axis='x', colors='#8b949e')

# Y-Axis 1 (Accuracy - Neon Cyan)
color1 = '#00f2fe'
ax1.set_ylabel('Operational Accuracy', color=color1, fontsize=12, fontweight='bold')
ax1.plot(x_smooth, y_acc_smooth, color=color1, linewidth=3, label='Operational Accuracy')
ax1.fill_between(x_smooth, y_acc_smooth, 0, where=(y_acc_smooth>=0), color=color1, alpha=0.15)
ax1.fill_between(x_smooth, y_acc_smooth, 0, where=(y_acc_smooth<0), color='#ff4b4b', alpha=0.1) # Red tint for negative territory
ax1.tick_params(axis='y', colors=color1)
ax1.set_ylim(-100, 110)

# Add Zero Line
ax1.axhline(0, color='#8b949e', linestyle='--', linewidth=1, alpha=0.5, label='Zero Line')

# Y-Axis 2 (Complexity - Neon Crimson/Magenta)
color2 = '#ff0a78'
ax1.plot(x_smooth, y_comp_smooth, color=color2, linewidth=3, linestyle='-', label='System Complexity')

# Markers for actual data points
ax1.scatter(x, accuracy, color=color1, s=80, zorder=5, edgecolor='#0d1117', linewidth=1.5)
ax1.scatter(x, complexity, color=color2, s=80, zorder=5, edgecolor='#0d1117', linewidth=1.5)

# Legends
ax1.legend(loc='upper left', frameon=True, facecolor='#161b22', edgecolor='#30363d', fontsize=10)


# Annotations showing the "Double Positive Expansion"
ax1.annotate('Double Positive Expansion', 
             xy=(5, 95), xytext=(4, 60),
             arrowprops=dict(facecolor='#00f2fe', shrink=0.05, width=2, headwidth=8),
             fontsize=12, fontweight='bold', color='#00f2fe')

ax1.annotate('Decapitation & Crash Void', 
             xy=(2, -80), xytext=(1.5, -40),
             arrowprops=dict(facecolor='#ff4b4b', shrink=0.05, width=1, headwidth=5),
             fontsize=10, color='#ff4b4b')

plt.tight_layout()
plt.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
print(f"Saved graph to {out_path}")
