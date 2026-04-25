import pandas as pd
import numpy as np
from pathlib import Path
from rich.console import Console
import matplotlib.pyplot as plt

console = Console()

def data(file_path: str, threshold: float = 0.5, plot: bool = False):
    file_ptr = Path(file_path)
    
    if not file_ptr.exists():
        console.print(f"[red]❌ Error: File {file_path} not found![/red]")
        return

    console.print(f"[blue]🔍 Auditing {file_ptr.name}...[/blue]")

    try:
        df = pd.read_parquet(file_ptr)
        # Assuming 'action' is the column with movement data
        actions = np.stack(df['action'].values)
        jumps = np.abs(np.diff(actions, axis=0))
        # Take the maximum jump across all dimensions (x, y, z, etc.)
        max_jumps_per_frame = jumps.max(axis=1)
        absolute_max = max_jumps_per_frame.max()

        console.print(f"✅ Loaded {len(df)} frames.")
        console.print(f"📊 Sharpest movement: [bold]{absolute_max:.2f}[/bold]")

        glitch_frame = np.argmax(max_jumps_per_frame)

        if absolute_max > threshold:
            console.print(f"[red]🚨 ALERT: Significant glitch detected at Frame {glitch_frame}![/red]")
        else:
            console.print("[green]✨ Data Quality: Smooth movement detected.[/green]")

        # --- NEW PLOTTING LOGIC ---
        if plot:
            console.print("[yellow]📈 Generating visualization...[/yellow]")
            plt.figure(figsize=(10, 5))
            plt.plot(max_jumps_per_frame, label='Inter-frame Jump Magnitude', color='royalblue')
            plt.axhline(y=threshold, color='red', linestyle='--', label='Threshold')
            
            if absolute_max > threshold:
                plt.annotate(f'GLITCH @ {glitch_frame}', 
                             xy=(glitch_frame, absolute_max), 
                             xytext=(glitch_frame + 500, absolute_max),
                             arrowprops=dict(facecolor='black', shrink=0.05))
            
            plt.title(f"Kinematic Audit: {file_ptr.name}")
            plt.xlabel("Frame Index")
            plt.ylabel("Jump Magnitude")
            plt.legend()
            plt.grid(alpha=0.3)
            plt.show()

    except Exception as e:
        console.print(f"[red]❌ Logic Error: {e}[/red]")