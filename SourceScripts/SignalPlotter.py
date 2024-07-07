import pandas as pd
import matplotlib.pyplot as plt

class SignalPlotter:
    def __init__(self, csv_file):
        self.data = pd.read_csv(csv_file)
        self.plots = []
        self.plot_params = {
            "color": "blue",
            "text_size": 12,
            "font": "Arial",
            "background_color": "white",
            "axis": True
        }
        self.data.index = pd.RangeIndex(start=0, stop=len(self.data), step=1)

    def set_plot_params(self, **kwargs):
        for key, value in kwargs.items():
            if key in self.plot_params:
                self.plot_params[key] = value

    def add_signal_plot(self, signal_name):
        if signal_name in self.data.columns:
            self.plots.append(signal_name)
        else:
            print(f"Signal '{signal_name}' not found in CSV columns.")

    def generate_plots(self):
        num_plots = len(self.plots)
        fig, axes = plt.subplots(num_plots, 1, figsize=(10, 2*num_plots))

        if num_plots == 1:
            axes = [axes]  # Ensure axes is iterable if only one plot

        fig.patch.set_facecolor(self.plot_params["background_color"])

        for i, signal in enumerate(self.plots):
            axes[i].plot(self.data.index, self.data[signal], color=self.plot_params["color"])
            axes[i].set_title(signal, fontsize=self.plot_params["text_size"], fontname=self.plot_params["font"])
            axes[i].set_facecolor(self.plot_params["background_color"])

            if not self.plot_params["axis"]:
                axes[i].axis('off')

        plt.tight_layout()
        plt.show()

# Usage Example
plotter = SignalPlotter('SourceScripts/data.csv')
plotter.set_plot_params(color='green', text_size=10, font='Times New Roman', background_color='lightgrey', axis=True)
plotter.add_signal_plot('VREAD Set V')
plotter.add_signal_plot('VREAD I')
plotter.add_signal_plot('VREAD V')
plotter.generate_plots()
