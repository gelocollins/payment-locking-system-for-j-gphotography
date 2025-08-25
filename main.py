# // DOCUMENTATION LINK: https://github.com/gelocollins/payment-locking-system-for-j-gphotography/blob/main/README.MD
# // CREDIT: OSCAR ANGELO COLLIN RIVERA
# // GITHUB: https://github.com/gelocollins
# // FACEBOOK: https://www.facebook.com/angelo.collins.687574
# // EMAIL: angeloqq03@gmail.com / gelocollins@icloud.com
# // INSTAGRAM: https://www.instagram.com/angelocollinsrivera/
# // CONTACT NO: 0931 871 3008 / 0992 438 7967
# // PROJECT NAME: PAYMENT LOCKING SYSTEM FOR J&G-GPHOTOGRAPHY
# // PROJECT DESCRIPTION: This is a payment locking system for J-GPhotography. This system is used
# // to lock the system if the user has not paid for the service. The system will be unlocked
# // if the user has paid for the service. And, the system will be locked again after the photo is printed.

import serial
import time
import threading
import sys
import select














# Configuration
COM_TP70 = "COM3"           # change to your TP70 port
COM_ESP32 = None            # or e.g. "COM5" if using ESP32 relay
TARGET_AMOUNT = 100         # amount to unlock
SESSION_TIMEOUT = 60        # seconds

BILL_CODES = {0x40: 100, 0x41: 200}  # TP70 bill codes

ACK = 0x02
REJECT = 0x0F
ESCROW = 0x81
POWER1 = 0x80
POWER2 = 0x8F

session = {"amount":0, "last":time.time(), "active":False}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def open_port(port, baud=9600):
    return serial.Serial(port, baudrate=baud, bytesize=8, parity=serial.PARITY_EVEN,
                         stopbits=1, timeout=0.2)

def unlock_action(esp):
    log("=== UNLOCK TRIGGERED ===")
    if esp:
        esp.write(b"UNLOCK\n")

def lock_action(esp):
    log("=== LOCK TRIGGERED ===")
    if esp:
        esp.write(b"LOCK\n")

def process_tap(tp, esp):
    b = tp.read(1)
    if not b: return
    c = b[0]
    if c in (POWER1, POWER2):
        log("TP70 power-up detected; sending ACK")
        tp.write(bytes([ACK]))
    elif c == ESCROW:
        code = tp.read(1)
        if not code: return
        val = BILL_CODES.get(code[0])
        log(f"ESCROW code 0x{code[0]:02X}, value={val}")
        if val:
            tp.write(bytes([ACK]))
            session["amount"] += val
            session["last"] = time.time()
            session["active"] = True
            log(f"Amount=₱{session['amount']}")
            if session["amount"] >= TARGET_AMOUNT:
                unlock_action(esp)
        else:
            tp.write(bytes([REJECT]))
            log("Rejected unknown bill")

def input_listener(tp, esp):
    log("Type 'reset' to restart session.")
    while True:
        ready, *_ = select.select([sys.stdin], [], [], 1)
        if ready:
            cmd = sys.stdin.readline().strip().lower()
            if cmd == 'reset':
                session["amount"] = 0
                session["active"] = False
                session["last"] = time.time()
                log("Session reset by user")
                lock_action(esp)

def main():
    try:
        tp = open_port(COM_TP70)
    except Exception as e:
        log(f"Error opening TP70 port: {e}")
        return

    esp = None
    if COM_ESP32:
        try:
            esp = open_port(COM_ESP32, baud=115200)
        except Exception as e:
            log(f"ESP32 port error: {e}")

    log("Ready. Waiting for bills...")

    threading.Thread(target=input_listener, args=(tp,esp), daemon=True).start()

    while True:
        process_tap(tp, esp)
        if session["active"] and (time.time() - session["last"] > SESSION_TIMEOUT):
            log("Session timeout. Resetting.")
            session["amount"] = 0
            session["active"] = False
            lock_action(esp)
        time.sleep(0.05)

if __name__ == "__main__":
    main()

