#!/usr/bin/env python3
"""Bounty Hunter ship monitor — local HTTP server + NMEA/demo feed."""
from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
CFG_PATH = ROOT / "config.json"

state_lock = threading.Lock()
state = {
    "ok": True,
    "mode": "demo",
    "source": "demo",
    "ts": 0,
    "running": False,
    "port": {},
    "stbd": {},
    "fuel_pct": None,
    "fuel_gal": None,
    "water_pct": None,
    "water_gal": None,
    "holding_pct": None,
    "holding_gal": None,
    "house_v": None,
    "seakeeper": {},
    "gen": {},
}

reader_proc = None
stop_flag = False


def load_cfg():
    with CFG_PATH.open() as f:
        return json.load(f)


def now_ms():
    return int(time.time() * 1000)


def empty_engine():
    return {
        "rpm": None,
        "coolant_f": None,
        "oil_temp_f": None,
        "oil_psi": None,
        "boost_psi": None,
        "volts": None,
        "fuel_rate_gph": None,
        "load_pct": None,
        "hours": None,
    }


def empty_gen():
    return {
        "rpm": None,
        "coolant_f": None,
        "oil_psi": None,
        "oil_temp_f": None,
        "volts": None,
        "hours": None,
        "running": False,
        "ac_v": None,
        "ac_hz": None,
        "ac_a": None,
        "ac_kw": None,
        "load_pct": None,
        "name": "Phasor K4-12",
        "serial": "8098",
    }


def demo_loop(cfg):
    t0 = time.time()
    while not stop_flag:
        t = time.time() - t0
        port = empty_engine()
        stbd = empty_engine()
        port.update(
            {
                "rpm": 2140 + 40 * math.sin(t / 7),
                "coolant_f": 186 + 3 * math.sin(t / 11),
                "oil_temp_f": 198 + 2 * math.sin(t / 13),
                "oil_psi": 52 + 3 * math.sin(t / 5),
                "boost_psi": 12.4 + 0.6 * math.sin(t / 6),
                "volts": 27.6 + 0.15 * math.sin(t / 9),
                "fuel_rate_gph": 16.8 + 0.8 * math.sin(t / 8),
                "load_pct": 62 + 4 * math.sin(t / 10),
                "hours": 1248.2,
            }
        )
        stbd.update(
            {
                "rpm": 2155 + 35 * math.sin(t / 7 + 0.4),
                "coolant_f": 189 + 3 * math.sin(t / 12),
                "oil_temp_f": 201 + 2 * math.sin(t / 14),
                "oil_psi": 50 + 3 * math.sin(t / 5.5),
                "boost_psi": 12.1 + 0.5 * math.sin(t / 6.2),
                "volts": 27.5 + 0.12 * math.sin(t / 9.5),
                "fuel_rate_gph": 17.1 + 0.7 * math.sin(t / 8.2),
                "load_pct": 64 + 3 * math.sin(t / 10.5),
                "hours": 1247.8,
            }
        )
        fuel_pct = 68 + 0.4 * math.sin(t / 40)
        water_pct = 54 + 0.3 * math.sin(t / 50)
        holding_pct = 38 + 0.2 * math.sin(t / 70)
        cap_f = cfg["tanks"]["fuel_capacity_gal"]
        cap_w = cfg["tanks"]["freshwater_capacity_gal"]
        cap_h = cfg["tanks"].get("holding_capacity_gal", 30)
        gen_on = (int(t) % 90) < 70
        gen = empty_gen()
        gen.update(
            {
                "running": gen_on,
                "rpm": 1802 + 4 * math.sin(t / 5) if gen_on else 0,
                "coolant_f": 182 + 2 * math.sin(t / 14) if gen_on else 92,
                "oil_psi": 48 + 2 * math.sin(t / 6) if gen_on else 0,
                "oil_temp_f": 196 + 2 * math.sin(t / 16) if gen_on else 78,
                "volts": 27.7 + 0.1 * math.sin(t / 9) if gen_on else 26.4,
                "hours": 612.4,
                "ac_v": 241 + 1.2 * math.sin(t / 8) if gen_on else 0,
                "ac_hz": 60.05 + 0.08 * math.sin(t / 7) if gen_on else 0,
                "ac_a": 28 + 4 * math.sin(t / 11) if gen_on else 0,
                "ac_kw": 6.4 + 0.8 * math.sin(t / 11) if gen_on else 0,
                "load_pct": 51 + 6 * math.sin(t / 11) if gen_on else 0,
            }
        )
        with state_lock:
            state.update(
                {
                    "ok": True,
                    "mode": "demo",
                    "source": "demo",
                    "ts": now_ms(),
                    "running": True,
                    "port": port,
                    "stbd": stbd,
                    "fuel_pct": fuel_pct,
                    "fuel_gal": fuel_pct / 100.0 * cap_f,
                    "water_pct": water_pct,
                    "water_gal": water_pct / 100.0 * cap_w,
                    "holding_pct": holding_pct,
                    "holding_gal": holding_pct / 100.0 * cap_h,
                    "house_v": 27.4 + 0.1 * math.sin(t / 20),
                    "seakeeper": {"rpm": 8900, "temp_f": 104, "run": True},
                    "gen": gen,
                }
            )
        time.sleep(0.4)


def _num(fields, *keys):
    for k in keys:
        if k in fields and fields[k] is not None:
            try:
                return float(fields[k])
            except (TypeError, ValueError):
                continue
    return None


def k_to_f(v):
    if v is None:
        return None
    if v > 200:
        return (v - 273.15) * 9 / 5 + 32
    return v


def pa_to_psi(v):
    if v is None:
        return None
    if v > 200:
        return v / 6894.76
    return v


def apply_engine_fields(eng, fields, pgn):
    if pgn == 127488:
        rpm = _num(fields, "Speed", "Engine Speed", "speed")
        if rpm is not None:
            eng["rpm"] = rpm
        boost = _num(fields, "Boost Pressure", "boostPressure", "Boost")
        if boost is not None:
            eng["boost_psi"] = pa_to_psi(boost) if boost > 50 else boost
    elif pgn == 127489:
        oil_p = _num(fields, "Oil Pressure", "oilPressure")
        if oil_p is not None:
            eng["oil_psi"] = pa_to_psi(oil_p) if oil_p > 50 else oil_p
        oil_t = _num(fields, "Oil Temperature", "oilTemperature")
        if oil_t is not None:
            eng["oil_temp_f"] = k_to_f(oil_t)
        cool = _num(fields, "Temperature", "Coolant Temperature", "engineCoolantTemperature")
        if cool is not None:
            eng["coolant_f"] = k_to_f(cool)
        volts = _num(fields, "Alternator Potential", "alternatorVoltage", "Voltage")
        if volts is not None:
            eng["volts"] = volts
        fr = _num(fields, "Fuel Rate", "fuelRate")
        if fr is not None:
            eng["fuel_rate_gph"] = fr * 264.172 if fr < 1 else fr
        load = _num(fields, "Percent Engine Load", "engineLoad", "Load")
        if load is not None:
            eng["load_pct"] = load
        hours = _num(fields, "Total Engine Hours", "engineHours", "Hours")
        if hours is not None:
            eng["hours"] = hours / 3600.0 if hours > 10000 else hours


def engine_instance(fields):
    inst = fields.get("Instance", fields.get("Engine Instance", fields.get("instance", 0)))
    try:
        inst = int(inst)
    except (TypeError, ValueError):
        inst = 0
    return inst


def engine_key(cfg, inst):
    mapping = cfg.get("engines") or {}
    port = int(mapping.get("port", 0))
    stbd = int(mapping.get("stbd", 1))
    gen = int(mapping.get("gen", 2))
    if inst == port:
        return "port"
    if inst == stbd:
        return "stbd"
    if inst == gen:
        return "gen"
    return None


def handle_canboat_line(cfg, line):
    line = line.strip()
    if not line or not line.startswith("{ "):
        if not line or not line.startswith("{"):
            return
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return
    pgn = msg.get("pgn") or msg.get("PGN")
    fields = msg.get("fields") or msg.get("Fields") or {}
    if not pgn:
        return
    cap_f = cfg["tanks"]["fuel_capacity_gal"]
    cap_w = cfg["tanks"]["freshwater_capacity_gal"]
    with state_lock:
        state["ts"] = now_ms()
        state["ok"] = True
        state["mode"] = "live"
        state["source"] = "nmea2000"
        if pgn in (127488, 127489):
            inst = engine_instance(fields)
            key = engine_key(cfg, inst)
            if key == "gen":
                if not state.get("gen"):
                    state["gen"] = empty_gen()
                apply_engine_fields(state["gen"], fields, pgn)
                rpm = state["gen"].get("rpm") or 0
                state["gen"]["running"] = rpm > 400
            elif key in ("port", "stbd"):
                if not state.get(key):
                    state[key] = empty_engine()
                apply_engine_fields(state[key], fields, pgn)
                rpm = state["port"].get("rpm") or 0
                rpm2 = state["stbd"].get("rpm") or 0
                state["running"] = (rpm or 0) > 400 or (rpm2 or 0) > 400
        elif pgn in (127503, 127504, 65030):
            if not state.get("gen"):
                state["gen"] = empty_gen()
            v = _num(fields, "Voltage", "Line-Neutral AC RMS Voltage", "Average Line-Neutral AC RMS Voltage", "acVoltage")
            hz = _num(fields, "Frequency", "AC Frequency", "Average AC Frequency")
            a = _num(fields, "Current", "Average AC RMS Current", "acCurrent")
            kw = _num(fields, "Real Power", "Power", "acPower")
            if v is not None:
                state["gen"]["ac_v"] = v
            if hz is not None:
                state["gen"]["ac_hz"] = hz / 100.0 if hz > 200 else hz
            if a is not None:
                state["gen"]["ac_a"] = a
            if kw is not None:
                state["gen"]["ac_kw"] = kw / 1000.0 if kw > 200 else kw
        elif pgn == 127505:
            ftype = str(fields.get("Type", fields.get("Fluid Type", ""))).lower()
            level = _num(fields, "Level", "level")
            cap = _num(fields, "Capacity", "capacity")
            if level is not None and level <= 1.5:
                level *= 100.0
            if "fuel" in ftype or ftype in ("0", "diesel", "fuel"):
                if level is not None:
                    state["fuel_pct"] = level
                    state["fuel_gal"] = level / 100.0 * (cap * 264.172 if cap and cap < 10 else cap or cap_f)
            if "water" in ftype or "fresh" in ftype or ftype in ("1",):
                if level is not None:
                    state["water_pct"] = level
                    state["water_gal"] = level / 100.0 * (cap * 264.172 if cap and cap < 10 else cap or cap_w)
            if "waste" in ftype or "black" in ftype or "hold" in ftype or ftype in ("2",):
                cap_h = cfg["tanks"].get("holding_capacity_gal", 30)
                if level is not None:
                    state["holding_pct"] = level
                    state["holding_gal"] = level / 100.0 * (cap * 264.172 if cap and cap < 10 else cap or cap_h)
        elif pgn == 127508:
            v = _num(fields, "Voltage", "voltage")
            if v is not None:
                state["house_v"] = v


def live_loop(cfg):
    global reader_proc
    device = cfg.get("nmea_device") or "/dev/ttyUSB0"
    cmd = (cfg.get("nmea_command") or "actisense-serial {device} | analyzer -json").format(device=device)
    with state_lock:
        state["mode"] = "live"
        state["source"] = cmd
        state["port"] = empty_engine()
        state["stbd"] = empty_engine()
    if shutil.which("actisense-serial") is None or shutil.which("analyzer") is None:
        with state_lock:
            state["ok"] = False
            state["source"] = "canboat not installed — falling back to demo"
        demo_loop(cfg)
        return
    while not stop_flag:
        try:
            reader_proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in reader_proc.stdout:
                if stop_flag:
                    break
                handle_canboat_line(cfg, line)
            reader_proc.wait()
        except Exception as exc:
            with state_lock:
                state["ok"] = False
                state["source"] = str(exc)
        if stop_flag:
            break
        time.sleep(2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/state":
            with state_lock:
                payload = json.dumps(state)
            self._send(200, payload, "application/json")
            return
        if path == "/api/config":
            self._send(200, CFG_PATH.read_text(), "application/json")
            return
        if path in ("/", "/vessel.html"):
            self._send(200, (UI / "vessel.html").read_text(), "text/html; charset=utf-8")
            return
        if path in ("/index.html", "/cards", "/cards.html"):
            self._send(200, (UI / "index.html").read_text(), "text/html; charset=utf-8")
            return
        if path == "/chooser.html":
            self._send(200, (UI / "chooser.html").read_text(), "text/html; charset=utf-8")
            return
        rel = path.lstrip("/")
        fp = (UI / rel).resolve()
        if str(fp).startswith(str(UI.resolve())) and fp.is_file():
            ctype = {
                ".css": "text/css",
                ".js": "application/javascript",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".json": "application/json",
                ".xml": "application/xml",
            }.get(fp.suffix, "application/octet-stream")
            self._send(200, fp.read_bytes(), ctype)
            return
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/switch":
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                body = {}
            target = body.get("target", "")
            script = ROOT / "bin" / ("switch-to-lookout.sh" if target == "lookout" else "switch-to-monitor.sh")
            if target not in ("lookout", "monitor") or not script.exists():
                self._send(400, json.dumps({"ok": False, "error": "bad target"}), "application/json")
                return
            subprocess.Popen(["/bin/bash", str(script)], cwd=str(ROOT))
            self._send(200, json.dumps({"ok": True, "target": target}), "application/json")
            return
        self._send(404, "not found", "text/plain")


def main():
    global stop_flag
    cfg = load_cfg()
    mode = os.environ.get("SHIP_MONITOR_MODE", cfg.get("mode", "demo")).lower()
    host = cfg.get("listen", "127.0.0.1")
    port = int(os.environ.get("SHIP_MONITOR_PORT", cfg.get("port", 8088)))

    worker = threading.Thread(
        target=demo_loop if mode != "live" else live_loop,
        args=(cfg,),
        daemon=True,
    )
    worker.start()

    httpd = ThreadingHTTPServer((host, port), Handler)

    def shutdown(*_):
        global stop_flag, reader_proc
        stop_flag = True
        if reader_proc and reader_proc.poll() is None:
            reader_proc.terminate()
        httpd.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    print("ship-monitor http://%s:%s  mode=%s" % (host, port, mode), flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
