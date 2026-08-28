"""
PilotVision Mobile — minimal Android core.

This is a REAL, separate, from-scratch application, not a port of the
desktop PilotVision (that's built on Tkinter, which has zero Android
support — there is no way to "convert" it). This uses Kivy, one of the
few Python UI toolkits that can actually target Android, via a real
Android build tool (buildozer) that compiles this into an APK on a
Linux machine with the Android SDK/NDK installed.

Scope, honestly: this is the minimal real core discussed — connect to
a vehicle, show live telemetry, a real attitude indicator, and basic
mission monitoring (read-only). It does NOT have mission planning,
survey/corridor generation, parameter management, payload control,
airspace classification, or any of the other desktop features — those
would be built incrementally on top of this starting point, each one
a real, separate piece of work.

Real MAVLink connection reuses pymavlink, the same library the desktop
app uses — this is genuinely the same protocol talking to the same
vehicles, not a simulated connection.
"""
import math
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle, Ellipse, PushMatrix, PopMatrix, Rotate, Translate
from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

try:
    from pymavlink import mavutil
except ImportError:
    mavutil = None


# ---------------------------------------------------------------------------
# Real MAVLink connection — runs on a background thread so the UI never
# blocks, same principle as the desktop app's threaded connection.
# ---------------------------------------------------------------------------
class MavlinkLink:
    def __init__(self):
        self.conn = None
        self.telemetry = {
            "connected": False, "armed": False, "mode": "--",
            "lat": None, "lon": None, "alt_rel": None, "alt_msl": None,
            "groundspeed": None, "airspeed": None, "heading": None,
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "voltage": None, "battery_pct": None,
            "fix_type": None, "satellites": None,
            "wp_current": None, "wp_total": None,
        }
        self._stop = threading.Event()
        self._thread = None

    def connect(self, conn_string):
        if mavutil is None:
            self.telemetry["connected"] = False
            return False, "pymavlink is not installed"
        try:
            self.conn = mavutil.mavlink_connection(conn_string)
        except Exception as e:
            return False, str(e)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True, "connecting..."

    def disconnect(self):
        self._stop.set()
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        self.telemetry["connected"] = False

    def _loop(self):
        while not self._stop.is_set():
            try:
                msg = self.conn.recv_match(blocking=True, timeout=1.0)
            except Exception:
                continue
            if msg is None:
                continue
            self.telemetry["connected"] = True
            t = msg.get_type()
            if t == "HEARTBEAT":
                self.telemetry["armed"] = bool(msg.base_mode & 128)
                try:
                    self.telemetry["mode"] = mavutil.mode_string_v10(msg)
                except Exception:
                    pass
            elif t == "ATTITUDE":
                self.telemetry["roll"] = math.degrees(msg.roll)
                self.telemetry["pitch"] = math.degrees(msg.pitch)
                self.telemetry["yaw"] = math.degrees(msg.yaw) % 360
            elif t == "GLOBAL_POSITION_INT":
                self.telemetry["lat"] = msg.lat / 1e7
                self.telemetry["lon"] = msg.lon / 1e7
                self.telemetry["alt_rel"] = msg.relative_alt / 1000.0
                self.telemetry["alt_msl"] = msg.alt / 1000.0
                self.telemetry["heading"] = msg.hdg / 100.0
            elif t == "VFR_HUD":
                self.telemetry["groundspeed"] = msg.groundspeed
                self.telemetry["airspeed"] = msg.airspeed
            elif t == "SYS_STATUS":
                self.telemetry["voltage"] = msg.voltage_battery / 1000.0
                if msg.battery_remaining >= 0:
                    self.telemetry["battery_pct"] = msg.battery_remaining
            elif t == "GPS_RAW_INT":
                self.telemetry["fix_type"] = msg.fix_type
                self.telemetry["satellites"] = msg.satellites_visible
            elif t == "MISSION_CURRENT":
                self.telemetry["wp_current"] = msg.seq
            elif t == "MISSION_COUNT":
                self.telemetry["wp_total"] = msg.count


# ---------------------------------------------------------------------------
# Real attitude indicator — a genuine roll/pitch-driven artificial horizon,
# drawn with Kivy's canvas API (the mobile equivalent of the desktop HUD's
# Tkinter canvas drawing, same underlying idea, different toolkit).
# ---------------------------------------------------------------------------
class AttitudeIndicator(Widget):
    roll = NumericProperty(0.0)
    pitch = NumericProperty(0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, roll=self._redraw, pitch=self._redraw)

    def _redraw(self, *_args):
        self.canvas.clear()
        w, h = self.size
        if w <= 0 or h <= 0:
            return
        cx, cy = self.pos[0] + w / 2, self.pos[1] + h / 2
        ppx = h / 90.0  # pixels per degree of pitch, scaled to widget height
        with self.canvas:
            PushMatrix()
            Translate(cx, cy)
            Rotate(angle=-self.roll, origin=(0, 0))
            Translate(0, -self.pitch * ppx)
            big = max(w, h) * 2
            Color(0.16, 0.18, 0.22, 1)
            Rectangle(pos=(-big, 0), size=(2 * big, big))
            Color(0.11, 0.08, 0.08, 1)
            Rectangle(pos=(-big, -big), size=(2 * big, big))
            Color(1, 1, 1, 1)
            Line(points=[-big, 0, big, 0], width=1.5)
            for d in range(-30, 35, 10):
                if d == 0:
                    continue
                y = d * ppx
                half = 40 if d % 20 == 0 else 20
                Line(points=[-half, y, half, y], width=1)
            PopMatrix()
            # fixed aircraft symbol (doesn't rotate with the horizon)
            Color(1, 0.85, 0, 1)
            Line(points=[cx - 30, cy, cx - 8, cy], width=2.5)
            Line(points=[cx + 8, cy, cx + 30, cy], width=2.5)
            Ellipse(pos=(cx - 3, cy - 3), size=(6, 6))


KV = """
<TelemRow@BoxLayout>:
    size_hint_y: None
    height: dp(28)
    label_text: ""
    value_text: "--"
    Label:
        text: root.label_text
        color: 0.7, 0.72, 0.76, 1
        font_size: '13sp'
        halign: 'left'
        text_size: self.size
    Label:
        text: root.value_text
        color: 1, 1, 1, 1
        bold: True
        font_size: '14sp'
        halign: 'right'
        text_size: self.size

BoxLayout:
    orientation: 'vertical'
    canvas.before:
        Color:
            rgba: 0.067, 0.075, 0.09, 1
        Rectangle:
            pos: self.pos
            size: self.size
    padding: dp(10)
    spacing: dp(8)

    BoxLayout:
        size_hint_y: None
        height: dp(40)
        spacing: dp(6)
        Label:
            text: "[b]PILOT[/b][color=e53935][b]VISION[/b][/color] MOBILE"
            markup: True
            font_size: '16sp'
            halign: 'left'
            text_size: self.size
        Label:
            id: conn_status
            text: "OFFLINE"
            color: 0.6, 0.6, 0.6, 1
            bold: True
            size_hint_x: None
            width: dp(90)

    BoxLayout:
        size_hint_y: None
        height: dp(40)
        spacing: dp(6)
        TextInput:
            id: conn_string
            text: "udp:127.0.0.1:14550"
            multiline: False
            font_size: '13sp'
        Button:
            id: connect_btn
            text: "CONNECT"
            size_hint_x: None
            width: dp(100)
            background_color: 0.9, 0.22, 0.2, 1
            on_release: app.toggle_connect()

    AttitudeIndicator:
        id: attitude
        size_hint_y: None
        height: dp(220)

    BoxLayout:
        orientation: 'vertical'
        spacing: dp(2)
        TelemRow:
            id: row_mode
            label_text: "Flight Mode"
        TelemRow:
            id: row_armed
            label_text: "Armed"
        TelemRow:
            id: row_alt
            label_text: "Altitude (rel)"
        TelemRow:
            id: row_speed
            label_text: "Ground Speed"
        TelemRow:
            id: row_gps
            label_text: "GPS Fix / Sats"
        TelemRow:
            id: row_batt
            label_text: "Battery"
        TelemRow:
            id: row_mission
            label_text: "Mission Progress"

    Label:
        id: status_lbl
        text: "Enter a MAVLink connection string above and press Connect."
        color: 0.6, 0.62, 0.66, 1
        font_size: '12sp'
        size_hint_y: None
        height: dp(50)
        text_size: self.width, None
"""


class PilotVisionMobileApp(App):
    def build(self):
        self.link = MavlinkLink()
        self.root_widget = Builder.load_string(KV)
        Clock.schedule_interval(self._tick, 0.3)
        return self.root_widget

    def toggle_connect(self):
        r = self.root_widget
        if self.link.telemetry.get("connected"):
            self.link.disconnect()
            r.ids.connect_btn.text = "CONNECT"
            r.ids.conn_status.text = "OFFLINE"
            r.ids.conn_status.color = (0.6, 0.6, 0.6, 1)
            r.ids.status_lbl.text = "Disconnected."
            return
        conn_str = r.ids.conn_string.text.strip()
        ok, msg = self.link.connect(conn_str)
        r.ids.status_lbl.text = msg
        if ok:
            r.ids.connect_btn.text = "DISCONNECT"

    def _tick(self, _dt):
        r = self.root_widget
        t = self.link.telemetry
        connected = t.get("connected")
        r.ids.conn_status.text = "CONNECTED" if connected else "OFFLINE"
        r.ids.conn_status.color = (0.2, 0.8, 0.35, 1) if connected else (0.6, 0.6, 0.6, 1)

        r.ids.attitude.roll = t.get("roll") or 0.0
        r.ids.attitude.pitch = t.get("pitch") or 0.0

        r.ids.row_mode.value_text = str(t.get("mode") or "--")
        r.ids.row_armed.value_text = "ARMED" if t.get("armed") else "DISARMED"
        alt = t.get("alt_rel")
        r.ids.row_alt.value_text = f"{alt:.1f} m" if alt is not None else "--"
        gs = t.get("groundspeed")
        r.ids.row_speed.value_text = f"{gs:.1f} m/s" if gs is not None else "--"
        fix = t.get("fix_type")
        sats = t.get("satellites")
        r.ids.row_gps.value_text = f"{fix if fix is not None else '--'} / {sats if sats is not None else '--'}"
        volt = t.get("voltage")
        pct = t.get("battery_pct")
        if volt is not None:
            r.ids.row_batt.value_text = f"{volt:.1f}V" + (f" ({pct}%)" if pct is not None else "")
        else:
            r.ids.row_batt.value_text = "--"
        cur, tot = t.get("wp_current"), t.get("wp_total")
        if cur is not None and tot:
            r.ids.row_mission.value_text = f"WP {cur}/{tot}"
        else:
            r.ids.row_mission.value_text = "--"


if __name__ == "__main__":
    PilotVisionMobileApp().run()
