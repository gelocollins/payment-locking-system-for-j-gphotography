# // DOCUMENTATION LINK: https://github.com/gelocollins/payment-locking-system-for-j-gphotography/blob/main/README.MD
# // CREDIT: OSCAR ANGELO COLLIN RIVERA
# // GITHUB: https://github.com/gelocollins
# // FACEBOOK: https://www.facebook.com/angelo.collins.687574
# // EMAIL: angeloqq03@gmail.com / gelocollins@icloud.com
# // INSTAGRAM: https://www.instagram.com/angelocollinsrivera/
# // CONTACT NO: 0931 871 3008 / 0992 438 7967
# // PROJECT NAME: PAYMENT LOCKING SYSTEM FOR J-GPHOTOGRAPHY
# // PROJECT DESCRIPTION: This is a payment locking system for J-GPhotography. This system is used
# // to lock the system if the user has not paid for the service. The system will be unlocked
# // if the user has paid for the service. And, the system will be locked again after the photo is printed.

import serial
import time
import sys
from dataclasses import dataclass

# ======= USER CONFIG =======
COM_TP70 = "COM7"           # <-- change to your RS232-to-USB port for the TP70
COM_ESP32 = None            # e.g. "COM5" if you want to also toggle an ESP32 (optional)
TARGET_AMOUNT = 100         # amount that “unlocks” one session (change as you like)
SESSION_TIMEOUT_S = 120     # cancel session if idle this long

# Bill mapping (RS232 104U codes -> pesos). Adjust if your TP70’s bill table differs.
BILL_VALUE = {
    0x40: 100,   # first bill type
    0x41: 200,   # second bill type
    # 0x42: 500, 
    # 0x43: 1000,
    # 0x44: 0,  
}
# ===========================

# 104U protocol bytes
ACCEPT = 0x02
REJECT = 0x0F
HOLD   = 0x18   # (escrow hold, not used here)
POWER1 = 0x80   # BA -> host at power up
POWER2 = 0x8F   # BA -> host at power up
ESCROW = 0x81   # BA -> host “bill present” (will follow with 0x40..0x44)
POLL   = 0x0C   # host -> BA “status” (optional)

@dataclass
class Session:
    amount: int = 0
    last_activity: float = time.time()
    active: bool = True

def open_port(name):
    return serial.Serial(
        name,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN,   # even parity per 104U spec
        stopbits=serial.STOPBITS_ONE,
        timeout=0.2
    )

def log(s): print(time.strftime("[%H:%M:%S]"), s)

def unlock_action(esp):
    log("==> UNLOCK event (target amount reached)")
    if esp:
        try:
            esp.write(b"UNLOCK\n")
            log("Sent UNLOCK to ESP32.")
        except Exception as e:
            log(f"ESP32 write error: {e}")

def relock_action(esp):
    log("==> LOCK event (session ended)")
    if esp:
        try:
            esp.write(b"LOCK\n")
            log("Sent LOCK to ESP32.")
        except Exception as e:
            log(f"ESP32 write error: {e}")

def main():
    # Open TP70 serial
    try:
        tp = open_port(COM_TP70)
    except Exception as e:
        print(f"Cannot open TP70 port {COM_TP70}: {e}")
        sys.exit(1)

    # Open ESP32 serial (optional)
    esp = None
    if COM_ESP32:
        try:
            esp = serial.Serial(COM_ESP32, 115200, timeout=0.2)
        except Exception as e:
            log(f"Warning: cannot open ESP32 port {COM_ESP32}: {e}")
            esp = None

    log(f"Connected to TP70 on {COM_TP70} (9600 8E1). Waiting for POWER-UP...")
    sess = Session()

    # On power-up the validator sends 0x80/0x8F and expects 0x02 within 2 seconds.
    power_window = time.time() + 5
    powered = False

    while True:
        b = tp.read(1)
        if b:
            code = b[0]

            # POWER-UP handshake
            if code in (POWER1, POWER2):
                log("Power-up from validator -> replying ACCEPT (enable).")
                tp.write(bytes([ACCEPT]))
                powered = True
                continue

            if code == ESCROW:
                # Next byte should be bill type 0x40..0x44
                denom = tp.read(1)
                if not denom:
                    log("ESCROW without denomination byte — ignoring.")
                    continue

                bill_code = denom[0]
                value = BILL_VALUE.get(bill_code)
                log(f"Bill in escrow: code 0x{bill_code:02X} -> value {value if value else 'UNKNOWN'}")

                if value is None:
                    # Unknown bill type — reject
                    tp.write(bytes([REJECT]))
                    log("Rejected (unknown bill code).")
                    continue

                # Accept the bill
                tp.write(bytes([ACCEPT]))
                log("Accept command sent. Waiting for stack…")

                # The BA will send 0x10 (stacking) / 0x11 (reject) internally; we just update balance.
                sess.amount += value
                sess.last_activity = time.time()
                log(f"Accumulated amount: ₱{sess.amount}")

                # Check target
                if sess.amount >= TARGET_AMOUNT:
                    unlock_action(esp)
                continue

            # Optional: read error/status bytes when we poll (not strictly necessary)
            # If you want, you can periodically send POLL and interpret responses here.

        # Periodic tasks
        now = time.time()

        # If validator powered but no session activity and we want to keep it enabled,
        # occasionally ping with POLL (not required, but keeps link warm).
        if powered and int(now) % 3 == 0:
            try:
                tp.write(bytes([POLL]))
            except Exception as e:
                log(f"Write error: {e}")

        # Timeout auto-cancel
        if sess.active and (now - sess.last_activity) > SESSION_TIMEOUT_S and sess.amount > 0:
            log(f"Session timeout after {SESSION_TIMEOUT_S}s. Cancelling and re-locking.")
            sess = Session()  # reset
            relock_action(esp)

        # Small sleep to avoid busy loop
        time.sleep(0.02)

if __name__ == "__main__":
    main()

