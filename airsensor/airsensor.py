#!/usr/bin/env python3
"""
airsensor.py

Python-Implementierung des AirSensor C-Programms.
Originalquelle: Rodric Yates, modifiziert von Sebastian Sjoholm
Python-Version erstellt für den Einsatz mit pyusb

Voraussetzung:
    pyusb, libusb-1.0-0, scrollphathd (optional)

Installation:
    pip install pyusb
    pip install scrollphathd  # Für Display-Unterstutzung
    apt-get install libusb-1.0-0  # Debian/Ubuntu

Verwendung:
    python3 airsensor.py [Optionen]
    python3 airsensor.py -d        # Debug-Ausgabe
    python3 airsensor.py -v        # Nur VOC-Wert ausgeben
    python3 airsensor.py -o        # Ein Wert und dann beenden
    python3 airsensor.py -s        # Auf Scroll pHAT HD anzeigen
    python3 airsensor.py -r        # Display um 180 Grad drehen
    python3 airsensor.py -h        # Hilfe
"""

import argparse
import signal
import sys
import time
from datetime import datetime

import usb.core
import usb.util
from usb.core import USBError

# Scroll pHAT HD optional importieren
try:
    import scrollphathd
    SCROLLPHAT_AVAILABLE = True
except ImportError:
    SCROLLPHAT_AVAILABLE = False
    scrollphathd = None


class AirSensor:
    """AirSensor USB-Gerä··t-Klasse."""

    VENDOR_ID = 0x03eb
    PRODUCT_ID = 0x2013
    VOC_MIN = 450
    VOC_MAX = 2001
    MAX_RECONNECT_ATTEMPTS = 5

    def __init__(self, debug=False, use_display=False, rotate_display=False):
        """Initialisiere den AirSensor."""
        self.debug = debug
        self.use_display = use_display
        self.rotate_display = rotate_display
        self.dev = None
        self.devh = None
        self.last_valid_voc = None  # Letzter gültiger VOC-Wert
        self._setup_signal_handler()
        self._init_display()

    def _setup_signal_handler(self):
        """Signal-Handler für sauberes Beenden."""
        signal.signal(signal.SIGTERM, self._release_usb_device)
        signal.signal(signal.SIGINT, self._release_usb_device)

    def _init_display(self):
        """Scroll pHAT HD initialisieren."""
        if self.use_display:
            if not SCROLLPHAT_AVAILABLE:
                print("ERROR: scrollphathd Modul nicht installiert")
                print("Installation: pip install scrollphathd")
                sys.exit(1)

            try:
                scrollphathd.set_brightness(0.5)  # Helligkeit anpassen (0.0-1.0)
                
                # Display um 180 Grad drehen, falls gewünscht
                if self.rotate_display:
                    scrollphathd.rotate(180)
                
                scrollphathd.clear()
                self._display_message("AirSensor", scroll=True)
            except Exception as e:
                print(f"ERROR: Display-Initialisierung fehlgeschlagen: {e}")
                sys.exit(1)

            if self.debug:
                self._log("DEBUG: Display initialized")
                if self.rotate_display:
                    self._log("DEBUG: Display rotated 180 degrees", 0)

    def _scroll_text(self, text, delay=0.05):
        """Text über das Display scrollen."""
        if not self.use_display:
            return

        try:
            scrollphathd.clear()
            scrollphathd.write_string(text)
            scrollphathd.show()
            
            # Scrollen durch wiederholtes Aufrufen von scroll()
            # scrollphathd.width enthält die Breite des Displays (17)
            display_width = getattr(scrollphathd, 'width', 17)
            
            for _ in range(display_width):
                scrollphathd.scroll(1, 0)
                scrollphathd.show()
                time.sleep(delay)
                
        except Exception as e:
            if self.debug:
                print(f"DEBUG: Scroll error: {e}")

    def _display_message(self, message, scroll=False, duration=2):
        """Nachricht auf dem Display anzeigen."""
        if not self.use_display:
            return

        try:
            if scroll:
                # Scrollende Anzeige
                self._scroll_text(message)
            else:
                # Statische Anzeige
                scrollphathd.clear()
                scrollphathd.write_string(message)
                scrollphathd.show()
        except Exception as e:
            if self.debug:
                print(f"DEBUG: Display error: {e}")

    def _display_voc(self, voc):
        """VOC-Wert auf dem Display anzeigen."""
        if not self.use_display:
            return

        try:
            scrollphathd.clear()

            # VOC-Wert formatieren (max 17 Zeichen für Display)
            if voc >= 1000:
                text = f"{voc}ppm"
            else:
                text = f"{voc}"

            scrollphathd.write_string(text)
            scrollphathd.show()
        except Exception as e:
            if self.debug:
                print(f"DEBUG: Display VOC error: {e}")

    def _release_usb_device(self, signum=None, frame=None):
        """USB-Gerä··t freigeben und beenden."""
        if self.use_display:
            try:
                scrollphathd.clear()
                scrollphathd.show()
            except Exception:
                pass

        if self.devh:
            try:
                usb.util.release_interface(self.devh, 0)
            except Exception:
                pass
        if self.devh:
            try:
                self.devh.close()
            except Exception:
                pass
        sys.exit(0)

    def _log(self, message, value=None):
        """Debug- oder normale Ausgabe."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if value is None:
            print(f"{timestamp}, {message}")
        else:
            print(f"{timestamp}, {message} {value}")

    def _close_device(self):
        """USB-Gerä··t schließen."""
        if self.devh:
            try:
                usb.util.release_interface(self.devh, 0)
            except Exception:
                pass
            try:
                self.devh.close()
            except Exception:
                pass
        self.devh = None
        self.dev = None

    def _reconnect(self):
        """Versuche, das USB-Gerä··t neu zu verbinden."""
        if self.debug:
            self._log("DEBUG: Attempting to reconnect...")

        self._close_device()

        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            if self.debug:
                self._log("DEBUG: Reconnect attempt", attempt)

            try:
                self.dev = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)
                if self.dev is None:
                    if self.debug:
                        self._log("DEBUG: Device not found, waiting...")
                    time.sleep(2)
                    continue

                self.devh = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)
                
                # Kernel-Treiber trennen, falls nötig
                try:
                    if self.devh.is_kernel_driver_active(0):
                        self.devh.detach_kernel_driver(0)
                except (usb.core.USBError, NotImplementedError):
                    pass

                # Interface beanspruchen
                try:
                    self.devh.set_configuration()
                    usb.util.claim_interface(self.devh, 0)
                except usb.core.USBError as e:
                    if self.debug:
                        self._log("DEBUG: Claim failed, retrying:", str(e))
                    time.sleep(1)
                    continue

                if self.debug:
                    self._log("DEBUG: Reconnect successful")
                return True

            except Exception as e:
                if self.debug:
                    self._log("DEBUG: Reconnect error:", str(e))
                time.sleep(2)

        if self.debug:
            self._log("DEBUG: Reconnect failed after", self.MAX_RECONNECT_ATTEMPTS)
        return False

    def find_device(self):
        """Suche nach dem AirSensor USB-Gerä··t."""
        if self.debug:
            self._log("DEBUG: Init USB")

        counter = 0
        while True:
            self.dev = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)

            if self.dev is None:
                if self.debug:
                    self._log("DEBUG: No device found, wait 10sec...")
                time.sleep(10)
                counter += 1
                if counter == 10:
                    self._log("ERROR: Device not found")
                    sys.exit(1)
            else:
                break

        if self.debug:
            self._log("DEBUG: USB device found")

        return self.dev

    def open_device(self):
        """Ö·ffne das USB-Gerä··t."""
        self.devh = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)

        if self.devh is None:
            raise RuntimeError("Device not found")

        # Kernel-Treiber trennen, falls nötig
        try:
            if self.devh.is_kernel_driver_active(0):
                self.devh.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            pass

        # Interface beanspruchen
        try:
            self.devh.set_configuration()
            usb.util.claim_interface(self.devh, 0)
        except usb.core.USBError as e:
            self._log("ERROR: claim failed with error:", str(e))
            sys.exit(1)

        return self.devh

    def read_voc(self):
        """Lese VOC-Wert vom Sensor."""
        try:
            if self.debug:
                self._log("DEBUG: Read any remaining data from USB")

            # Puffer leeren
            try:
                ret = self.devh.read(0x81, 16, timeout=1000)
                if self.debug:
                    self._log("DEBUG: Return code from USB read:", len(ret) if ret else 0)
            except usb.core.USBError:
                pass

            # USB-Kommando zum Anfordern von Daten: @h*TR
            if self.debug:
                self._log("DEBUG: Write data to device")

            command = b"\x40\x68\x2a\x54\x52\x0a\x40\x40\x40\x40\x40\x40\x40\x40\x40\x40"
            ret = self.devh.write(0x02, command, timeout=1000)

            if self.debug:
                self._log("DEBUG: Return code from USB write:", ret)

            if self.debug:
                self._log("DEBUG: Read USB")

            try:
                buf = self.devh.read(0x81, 16, timeout=1000)
            except usb.core.USBError as e:
                if self.debug:
                    self._log("DEBUG: USB read error:", str(e))
                return None

            if self.debug:
                self._log("DEBUG: Return code from USB read:", len(buf) if buf else 0)

            # Wenn ret == 0, nochmal lesen
            if len(buf) == 0:
                if self.debug:
                    self._log("DEBUG: Read USB")
                time.sleep(1)
                try:
                    buf = self.devh.read(0x81, 16, timeout=1000)
                except usb.core.USBError:
                    return None

                if self.debug:
                    self._log("DEBUG: Return code from USB read:", len(buf) if buf else 0)

            # VOC-Wert aus Buffer extrahieren (Byte 2-3, Little Endian)
            if len(buf) >= 4:
                iresult = (buf[3] << 8) | buf[2]
                voc = iresult  # Bereits Little Endian auf x86/x64
            else:
                return None

            time.sleep(1)

            # Puffer leeren (flush)
            if self.debug:
                self._log("DEBUG: Read USB [flush]")

            try:
                ret = self.devh.read(0x81, 16, timeout=1000)
                if self.debug:
                    self._log("DEBUG: Return code from USB read:", len(ret) if ret else 0)
            except usb.core.USBError:
                pass

            return voc

        except USBError as e:
            # USB-Fehler abfangen und None zurückgeben
            if self.debug:
                self._log("DEBUG: USBError in read_voc:", str(e))
            return None
        except Exception as e:
            # Andere Fehler abfangen
            if self.debug:
                self._log("DEBUG: Exception in read_voc:", str(e))
            return None

    def run(self, print_voc_only=False, one_read=False):
        """Hauptschleife."""
        self.find_device()
        self.open_device()

        consecutive_errors = 0
        max_consecutive_errors = 10

        while True:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                voc = self.read_voc()

                if voc is None:
                    consecutive_errors += 1
                    
                    if print_voc_only:
                        print("0")
                    else:
                        print(f"{timestamp}, ERROR: Invalid result code")
                    
                    # Bei Fehler: Letzten gültigen Wert auf dem Display anzeigen
                    if self.use_display:
                        if self.last_valid_voc is not None:
                            self._display_voc(self.last_valid_voc)
                        # Falls noch kein gültiger Wert vorliegt, nichts anzeigen oder "Wait"
                        # (aktuell wird das Display einfach nicht aktualisiert)
                    
                    # Prüfen ob wir neu verbinden müssen
                    if consecutive_errors >= max_consecutive_errors:
                        if self.debug:
                            self._log("DEBUG: Too many errors, reconnecting...")
                        if self._reconnect():
                            consecutive_errors = 0
                        else:
                            if self.use_display:
                                self._display_message("NoDev", scroll=True)
                            time.sleep(5)
                            
                elif self.VOC_MIN <= voc <= self.VOC_MAX:
                    # Gültiger Wert: speichern und anzeigen
                    consecutive_errors = 0
                    self.last_valid_voc = voc
                    
                    if print_voc_only:
                        print(voc)
                    else:
                        print(f"{timestamp}, VOC: {voc}, RESULT: OK")
                    
                    if self.use_display:
                        self._display_voc(voc)
                        
                else:
                    # Wert außerhalb des Bereichs
                    consecutive_errors = 0
                    
                    if print_voc_only:
                        print("0")
                    else:
                        print(f"{timestamp}, VOC: {voc}, RESULT: Error value out of range")
                    
                    # Auch hier letzten gültigen Wert anzeigen
                    if self.use_display:
                        if self.last_valid_voc is not None:
                            self._display_voc(self.last_valid_voc)
                        else:
                            self._display_voc(voc)

                # Wenn nur ein Wert gelesen werden soll, beenden
                if one_read:
                    self._release_usb_device()

                # Warte auf nächste Anfrage
                time.sleep(10)

            except USBError as e:
                # USB-Fehler in der Hauptschleife abfangen
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if self.debug:
                    self._log("DEBUG: USBError in main loop:", str(e))
                
                if not print_voc_only:
                    print(f"{timestamp}, ERROR: USB error - attempting reconnect")
                
                # Letzten gültigen Wert auf dem Display anzeigen
                if self.use_display:
                    if self.last_valid_voc is not None:
                        self._display_voc(self.last_valid_voc)
                
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    if self._reconnect():
                        consecutive_errors = 0
                    else:
                        if self.use_display:
                            self._display_message("NoDev", scroll=True)
                        time.sleep(5)
                else:
                    time.sleep(2)

            except Exception as e:
                # Andere Fehler abfangen
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if self.debug:
                    self._log("DEBUG: Exception in main loop:", str(e))
                
                if not print_voc_only:
                    print(f"{timestamp}, ERROR: {e}")
                
                # Letzten gültigen Wert auf dem Display anzeigen
                if self.use_display:
                    if self.last_valid_voc is not None:
                        self._display_voc(self.last_valid_voc)
                
                time.sleep(2)


def main():
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(description="AirSensor USB-Gerä··t auslesen")
    parser.add_argument("-d", "--debug", action="store_true", help="Debug-Ausgabe aktivieren")
    parser.add_argument("-v", "--voc-only", action="store_true", help="Nur VOC-Wert ausgeben")
    parser.add_argument("-o", "--one-read", action="store_true", help="Ein Wert und dann beenden")
    parser.add_argument("-s", "--scrollphat", action="store_true",
                        help="Auf Scroll pHAT HD anzeigen")
    parser.add_argument("-r", "--rotate", action="store_true",
                        help="Display-Ausgabe um 180 Grad drehen")

    args = parser.parse_args()

    if args.debug:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp}, DEBUG: Active")

    sensor = AirSensor(debug=args.debug, use_display=args.scrollphat,
                       rotate_display=args.rotate)
    sensor.run(print_voc_only=args.voc_only, one_read=args.one_read)


if __name__ == "__main__":
    main()
