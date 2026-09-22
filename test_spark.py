import tkinter as tk
class Sparkline(tk.Canvas):
    def __init__(self, parent, width=520, height=52, maxpoints=90, **kwargs):
        super().__init__(parent, width=width, height=height, bg='black', highlightthickness=0, **kwargs)
        self.delete('all')
root = tk.Tk()
spark_f = tk.Frame(root)
s = Sparkline(spark_f, width=534, height=50)
print('Success!')
