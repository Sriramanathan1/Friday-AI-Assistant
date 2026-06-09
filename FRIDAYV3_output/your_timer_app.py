import tkinter as tk
import time
from playsound import playsound
import threading
import speech_recognition as sr
import re

class StandbyApp:
    def __init__(self, root):
        self.root = root
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black")
        threading.Thread(target=self.voice_listener, daemon=True).start()
        

        # ================= STATE =================
        self.mode = "Clock"
        self.running = False
        self.alarm_playing = False
        self.root.bind("<Button-1>", self.stop_alarm)

        self.hours = 0
        self.minutes = 1
        self.total_seconds = 60

        # ================= MAIN TIME =================
        self.time_label = tk.Label(
            root,
            text="00:00",
            fg="white",
            bg="black",
            font=("Orbitron", 270, "bold")
        )
        self.time_label.place(relx=0.5, rely=0.45, anchor="center")

        # ================= SUBSCRIPT SECONDS =================
        self.sec_label = tk.Label(
            root,
            text="00",
            fg="white",
            bg="black",
            font=("Orbitron", 20)  # smaller
        )
        # moved slightly right + lower (subscript feel)
        self.sec_label.place(relx=0.80, rely=0.60, anchor="center")

        # click time → toggle sliders
        self.time_label.bind("<Button-1>", self.toggle_slider)

        # ================= MENU =================
        self.menu_btn = tk.Button(
            root,
            text="☰",
            fg="white",
            bg="black",
            bd=0,
            font=("Orbitron", 24),
            command=self.toggle_sidebar
        )
        self.menu_btn.place(x=10, y=10)

        # ================= SIDEBAR =================
        self.sidebar = tk.Frame(root, bg="#111")
        self.sidebar_open = False
        self.build_sidebar()
        self.sidebar_y = 70

        # ================= SLIDERS =================
        self.hour_slider = tk.Scale(
            root, from_=0, to=11,
            orient="vertical",
            bg="black", fg="white",
            command=self.update_from_slider
        )

        self.min_slider = tk.Scale(
            root, from_=0, to=59,
            orient="vertical",
            bg="black", fg="white",
            command=self.update_from_slider
        )

        self.slider_visible = False

        # ================= BUTTONS =================
        self.start_btn = tk.Label(
            root,
            text="START",
            fg="white",
            bg="black",
            font=("Orbitron", 28, "bold"),
            padx=25,
            pady=10
        )
        self.start_btn.place(relx=0.45, rely=0.82, anchor="center")

        self.reset_btn = tk.Label(
            root,
            text="RESET",
            fg="white",
            bg="black",
            font=("Orbitron", 28, "bold"),
            padx=25,
            pady=10
        )
        self.reset_btn.place(relx=0.58, rely=0.82, anchor="center")

        # actions
        self.start_btn.bind("<Button-1>", lambda e: self.toggle_start())
        self.reset_btn.bind("<Button-1>", lambda e: self.reset_timer())

        # hover effect
        for b in [self.start_btn, self.reset_btn]:
            b.bind("<Enter>", lambda e, btn=b: btn.config(fg="cyan"))
            b.bind("<Leave>", lambda e, btn=b: btn.config(fg="white"))

        self.root.bind("<Escape>", lambda e: root.destroy())

        # start loop
        self.tick()

    # ================= BEEP ========================#
    def play_alarm(self):
        self.alarm_playing = True

        def run():
            playsound(r"C:\Users\mural\Timer\timer_sound.mp3")
            self.alarm_playing = False

        threading.Thread(target=run, daemon=True).start()
    # ================= ALARM OFF =================   
    def stop_alarm(self, event=None):
        self.alarm_playing = False
    # ================= MODE SWITCH =================
    def set_mode(self, mode):
        self.mode = mode
        self.update_display()  # IMPORTANT FIX

    # ================= SIDEBAR =================
    def toggle_sidebar(self):
        if self.sidebar_open:
            self.sidebar.place_forget()
        else:
            self.sidebar.place(x=10, y=self.sidebar_y, width=160, height=160)
        self.sidebar_open = not self.sidebar_open

    def build_sidebar(self):
        tk.Button(
            self.sidebar,
            text="Clock",
            bg="#111",
            fg="white",
            bd=0,
            command=lambda: self.set_mode("Clock")
        ).pack(fill="x", pady=10)

        tk.Button(
            self.sidebar,
            text="Timer",
            bg="#111",
            fg="white",
            bd=0,
            command=lambda: self.set_mode("Timer")
        ).pack(fill="x", pady=10)

    # ================= SLIDERS =================
    def toggle_slider(self, e=None):
        if self.slider_visible:
            self.hour_slider.place_forget()
            self.min_slider.place_forget()
        else:
            self.hour_slider.place(relx=0.05, rely=0.5, anchor="center")
            self.min_slider.place(relx=0.95, rely=0.5, anchor="center")

            self.hour_slider.set(self.hours)
            self.min_slider.set(self.minutes)

        self.slider_visible = not self.slider_visible

    def update_from_slider(self, val=None):
        self.hours = self.hour_slider.get()
        self.minutes = self.min_slider.get()

        self.total_seconds = (self.hours * 3600) + (self.minutes * 60)
        self.update_display()

    # ================= CONTROLS =================
    def toggle_start(self):
        self.running = not self.running
        self.start_btn.config(text="STOP" if self.running else "START")

    def reset_timer(self):
        self.running = False
        self.hours = 0
        self.minutes = 1
        self.total_seconds = 60
        self.start_btn.config(text="START")
        self.update_display()

    # ================= NLP =================
    def process_voice_command(self, command):
        print("Heard:", command)

        if "timer" in command and ("set" in command or "for" in command):
            hours = 0
            minutes = 0

            # extract numbers
            h_match = re.search(r'(\d+)\s*hour', command)
            m_match = re.search(r'(\d+)\s*minute', command)

            if h_match:
                hours = int(h_match.group(1))

            if m_match:
                minutes = int(m_match.group(1))

            # apply
            self.hours = hours
            self.minutes = minutes
            self.total_seconds = hours * 3600 + minutes * 60

            self.update_display()
            print(f"Timer set to {hours}h {minutes}m")

        # ===== BASIC COMMANDS =====
        elif "start" in command or "begin" in command:
            self.running = True
            self.start_btn.config(text="STOP")

        elif "stop" in command:
            self.running = False
            self.start_btn.config(text="START")

        elif "reset" in command:
            self.reset_timer()

        elif "clock" in command:
            self.set_mode("Clock")

        elif "timer" in command:
            self.set_mode("Timer")

    # ================= BGLISTENER =================
    def voice_listener(self):
        r = sr.Recognizer()
        mic = sr.Microphone()

        with mic as source:
            r.adjust_for_ambient_noise(source)

        while True:
            try:
                with mic as source:
                    audio = r.listen(source, phrase_time_limit=4)

                command = r.recognize_google(audio).lower()

                # run safely in main thread
                self.root.after(0, self.process_voice_command, command)

            except:
                pass

    # ================= DISPLAY =================
    def update_display(self):
        if self.mode == "Clock":
            h = time.strftime("%H")
            m = time.strftime("%M")
            s = time.strftime("%S")
            main_text = f"{h}:{m}"
        else:
            h = self.total_seconds // 3600
            m = (self.total_seconds % 3600) // 60
            s = self.total_seconds % 60
            main_text = f"{h:02}:{m:02}"

        # update main text
        self.time_label.config(text=main_text)

        # update seconds text
        self.sec_label.config(text=f"{s:02}")

        # force geometry update so we can measure size
        self.root.update_idletasks()

        # get width of main label (for alignment calculation)
        w = self.time_label.winfo_width()

        # center position (same as main text)
        center_x = 0.5

        # convert pixel width to approximate rel offset (stable trick)
        offset = (w / self.root.winfo_screenwidth()) / 2

        # place seconds slightly right of center + subscript drop
        self.sec_label.place(
            relx=center_x + offset + 0.02,
            rely=0.60        
        )

    # ================= LOOP =================
    def tick(self):
        if self.mode == "Timer" and self.running:
            if self.total_seconds > 0:
                self.total_seconds -= 1
            else:
                self.running = False
                self.start_btn.config(text="START")
                self.play_alarm()

        self.update_display()
        self.root.after(1000, self.tick)


# ================= RUN =================
root = tk.Tk()
app = StandbyApp(root)
root.mainloop()