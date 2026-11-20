import tkinter as tk
from tkinter import filedialog, messagebox

root = tk.Tk()
root.title("HADOC Sub")
root.geometry("1100x700")
root.configure(bg="#0b0f17")
tk.Label(root, text="HADOC SUB", fg="white", bg="#0b0f17").pack(pady=20)
tk.Label(root, text="English → Sinhala SRT Translator", fg="#f0526c", bg="#0b0f17").pack()
root.mainloop()
