import network
import urequests
import time
import math
import gc
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN as DISPLAY
try:
    import os
except ImportError:
    import uos as os

# Import PNG decoder
try:
    from pngdec import PNG
    PNG_AVAILABLE = True
except ImportError:
    PNG_AVAILABLE = False
    print("PNG decoder not available - PNG logos disabled; using plane symbol fallback")

# Import configuration from SECRETS.py
try:
    from SECRETS import *
except ImportError:
    print("ERROR: SECRETS.py file not found!")
    print("Please create SECRETS.py with your configuration.")
    print("See the SECRETS.py template for required variables.")
    raise

class PlaneTracker:
    def __init__(self):
        self.gu = GalacticUnicorn()
        self.graphics = PicoGraphics(DISPLAY)
        self.width, self.height = self.graphics.get_bounds()
        
        # Color definitions
        self.BLACK = self.graphics.create_pen(0, 0, 0)
        self.WHITE = self.graphics.create_pen(255, 255, 255)
        self.RED = self.graphics.create_pen(255, 0, 0)
        self.GREEN = self.graphics.create_pen(0, 255, 0)
        self.BLUE = self.graphics.create_pen(0, 0, 255)
        self.YELLOW = self.graphics.create_pen(255, 255, 0)
        self.CYAN = self.graphics.create_pen(0, 255, 255)
        self.MAGENTA = self.graphics.create_pen(255, 0, 255)
        self.ORANGE = self.graphics.create_pen(255, 128, 0)
        self.LIGHTBLUE = self.graphics.create_pen(120, 180, 255)
        # Extra hues for route rendering
        self.DARK_ORANGE = self.graphics.create_pen(200, 100, 0)
        
        # Commercial airline codes (major carriers only)
        self.commercial_airlines = {
            'BAW', 'VIR', 'EZY', 'RYR',  # UK carriers
            'UAL', 'AAL', 'DAL', 'JBU',  # US carriers  
            'AFR', 'DLH', 'KLM', 'IBE', 'SAS',  # European carriers
            'UAE', 'ETD', 'QTR', 'SVA', 'THY',  # Middle East carriers
            'SIA', 'CPA', 'JAL', 'ANA', 'QFA',  # Asia Pacific carriers
            'ACA', 'WJA',  # Canadian carriers
            'TAM', 'LAN',  # South American carriers
        }
        
        self.planes = []
        self.last_api_update = 0
        self.wifi_connected = False
        self.auth_token = None
        self.token_expires = 0
        self.display_plane_index = 0
        self.last_plane_switch = 0
        self.fetching_data = False
        self.api_success = False
        
        # Logos sync scheduling
        self.last_logos_sync = 0
        try:
            self.LOGOS_SYNC_INTERVAL = LOGOS_SYNC_INTERVAL  # seconds; optional in SECRETS
        except NameError:
            self.LOGOS_SYNC_INTERVAL = 3600  # default: 1 hour
        
        # Cache of missing logos to avoid repeated logs
        self._missing_logo_cache = set()

        # Memory controls
        try:
            self.MAX_PLANES = MAX_PLANES
        except NameError:
            self.MAX_PLANES = 24  # cap number of planes stored/displayed
        
        # Initialize PNG decoder if available
        if PNG_AVAILABLE:
            self.png = PNG(self.graphics)
        else:
            self.png = None
        
        # Error/status message (e.g., UPDATE ERROR)
        self.last_error_message = None
        
        # Display rotation: persistent queue and indices
        self.display_queue = []
        self.frame_index = 0
        self.last_frame_time = 0
        
        # Animation and UI state
        self.anim_active = False
        self.anim_start_time = 0  # ticks_ms()
        self.anim_duration = 0.5
        self.current_frame_key = None
        self.next_frame_key = None
        self.clock_only = False
        self.count_overlay_until = 0
        self.last_cycle = None
        self.fetch_due_at = 0

        # Night mode (UK time): 00:00–08:00 show clock only and dim display
        try:
            self.NIGHT_START_HOUR = NIGHT_START_HOUR  # optional override via SECRETS
        except NameError:
            self.NIGHT_START_HOUR = 0
        try:
            self.NIGHT_END_HOUR = NIGHT_END_HOUR
        except NameError:
            self.NIGHT_END_HOUR = 8
        try:
            self.NIGHT_BRIGHTNESS = NIGHT_BRIGHTNESS
        except NameError:
            self.NIGHT_BRIGHTNESS = 0.5
        try:
            self.DAY_BRIGHTNESS = DAY_BRIGHTNESS
        except NameError:
            self.DAY_BRIGHTNESS = 1.0
        self.night_mode = False

        # NTP sync configuration/state
        try:
            self.NTP_SYNC_INTERVAL = NTP_SYNC_INTERVAL
        except NameError:
            self.NTP_SYNC_INTERVAL = 24 * 60 * 60  # 24h
        try:
            self.NTP_HOST = NTP_HOST
        except NameError:
            self.NTP_HOST = None
        self.ntp_last_sync = 0
        self.ntp_ok = False

        # Logo sync preferences
        try:
            self.ALLOW_API_LOGO_LISTING = ALLOW_API_LOGO_LISTING
        except NameError:
            self.ALLOW_API_LOGO_LISTING = False  # default: avoid large JSON listings
        try:
            self.GITHUB_LOGOS_RAW_BASE = GITHUB_LOGOS_RAW_BASE
        except NameError:
            self.GITHUB_LOGOS_RAW_BASE = "https://raw.githubusercontent.com/steveberryman/galactic-flight-tracker/main/logos"

        # API interval (seconds) coerced to float/int to avoid type issues
        try:
            self.API_INTERVAL = int(self._to_float(API_UPDATE_INTERVAL, 10))
        except Exception:
            self.API_INTERVAL = 10

        # Route (ADSBdb) cache
        self.route_cache = {}
        self.callsign_iata_cache = {}
        self.route_last_fetch_times = {}
        try:
            self.ROUTE_TTL = ROUTE_TTL
        except NameError:
            self.ROUTE_TTL = 1800  # 30 minutes
        self.last_route_fetch_time = 0

        # Route (ADSBdb) cache
        self.route_cache = {}
        try:
            self.ROUTE_TTL = ROUTE_TTL
        except NameError:
            self.ROUTE_TTL = 1800  # 30 minutes
        self.last_route_fetch_time = 0

        # Tiny 3x5 font for compact text (date/time/route)
        self._tiny_font = {
            '0': [0b111, 0b101, 0b101, 0b101, 0b111],
            '1': [0b010, 0b110, 0b010, 0b010, 0b111],
            '2': [0b111, 0b001, 0b111, 0b100, 0b111],
            '3': [0b111, 0b001, 0b111, 0b001, 0b111],
            '4': [0b101, 0b101, 0b111, 0b001, 0b001],
            '5': [0b111, 0b100, 0b111, 0b001, 0b111],
            '6': [0b111, 0b100, 0b111, 0b101, 0b111],
            '7': [0b111, 0b001, 0b010, 0b100, 0b100],
            '8': [0b111, 0b101, 0b111, 0b101, 0b111],
            '9': [0b111, 0b101, 0b111, 0b001, 0b111],
            '/': [0b001, 0b001, 0b010, 0b100, 0b100],
            ':': [0b000, 0b010, 0b000, 0b010, 0b000],
            '-': [0b000, 0b000, 0b111, 0b000, 0b000],
            '>': [0b100, 0b010, 0b001, 0b010, 0b100],
            'A': [0b010, 0b101, 0b111, 0b101, 0b101],
            'B': [0b110, 0b101, 0b110, 0b101, 0b110],
            'C': [0b011, 0b100, 0b100, 0b100, 0b011],
            'D': [0b110, 0b101, 0b101, 0b101, 0b110],
            'E': [0b111, 0b100, 0b110, 0b100, 0b111],
            'F': [0b111, 0b100, 0b110, 0b100, 0b100],
            'G': [0b011, 0b100, 0b101, 0b101, 0b011],
            'H': [0b101, 0b101, 0b111, 0b101, 0b101],
            'I': [0b111, 0b010, 0b010, 0b010, 0b111],
            'J': [0b001, 0b001, 0b001, 0b101, 0b010],
            'K': [0b101, 0b110, 0b100, 0b110, 0b101],
            'L': [0b100, 0b100, 0b100, 0b100, 0b111],
            'M': [0b101, 0b111, 0b111, 0b101, 0b101],
            'N': [0b101, 0b111, 0b111, 0b111, 0b101],
            'O': [0b111, 0b101, 0b101, 0b101, 0b111],
            'P': [0b111, 0b101, 0b111, 0b100, 0b100],
            'Q': [0b111, 0b101, 0b101, 0b111, 0b001],
            'R': [0b111, 0b101, 0b111, 0b110, 0b101],
            'S': [0b011, 0b100, 0b011, 0b001, 0b110],
            'T': [0b111, 0b010, 0b010, 0b010, 0b010],
            'U': [0b101, 0b101, 0b101, 0b101, 0b111],
            'V': [0b101, 0b101, 0b101, 0b101, 0b010],
            'W': [0b101, 0b101, 0b111, 0b111, 0b101],
            'X': [0b101, 0b101, 0b010, 0b101, 0b101],
            'Y': [0b101, 0b101, 0b010, 0b010, 0b010],
            'Z': [0b111, 0b001, 0b010, 0b100, 0b111],
        }
        
    def tiny_text_width(self, s):
        n = len(s)
        if n <= 0:
            return 0
        return n * 3 + (n - 1)

    def draw_tiny_text(self, s, x, y, pen):
        self.graphics.set_pen(pen)
        cx = x
        for ch in s:
            glyph = self._tiny_font.get(ch)
            if glyph is None:
                cx += 4
                continue
            for row in range(5):
                bits = glyph[row]
                for col in range(3):
                    if (bits & (1 << (2 - col))) != 0:
                        self.graphics.pixel(cx + col, y + row)
            cx += 4

    def draw_route_tiny(self, route_str, x, y, code_pen, arrow_pen):
        """Draw route like ABC->DEF with different color for arrow."""
        if not route_str:
            return
        cx = x
        for ch in route_str:
            glyph = self._tiny_font.get(ch)
            # Choose pen: arrow chars '-' and '>'
            if ch in ('-', '>'):
                self.graphics.set_pen(arrow_pen)
            else:
                self.graphics.set_pen(code_pen)
            if glyph is None:
                cx += 4
                continue
            for row in range(5):
                bits = glyph[row]
                for col in range(3):
                    if (bits & (1 << (2 - col))) != 0:
                        self.graphics.pixel(cx + col, y + row)
            cx += 4

    def _norm_callsign(self, callsign):
        try:
            return (callsign or "").strip().upper()
        except Exception:
            return callsign or ""

    def get_cached_route(self, callsign):
        callsign = self._norm_callsign(callsign)
        if not callsign:
            return None
        item = self.route_cache.get(callsign)
        if not item:
            return None
        route_str, ts = item
        if time.time() - ts > self.ROUTE_TTL:
            return None
        return route_str

    def fetch_route(self, callsign):
        # Throttle lookups per callsign
        callsign = self._norm_callsign(callsign)
        now = time.time()
        last = self.route_last_fetch_times.get(callsign, 0)
        if now - last < 5:
            return self.route_cache.get(callsign, (None, 0))[0]
        self.route_last_fetch_times[callsign] = now
        try:
            url = f"https://api.adsbdb.com/v0/callsign/{callsign.lower()}"
            try:
                r = urequests.get(url, timeout=5)
            except TypeError:
                r = urequests.get(url)
            if r.status_code == 200:
                data = r.json()
                r.close()
                resp = data.get('response', {})
                fr = resp.get('flightroute', {})
                org = fr.get('origin', {})
                dst = fr.get('destination', {})
                o = (org.get('iata_code') or '').upper()
                d = (dst.get('iata_code') or '').upper()
                if o and d:
                    route_str = f"{o}>{d}"
                    self.route_cache[callsign] = (route_str, now)
                # Cache IATA callsign if present (inside flightroute)
                iata_cs = (fr.get('callsign_iata') or '').upper()
                if iata_cs:
                    self.callsign_iata_cache[callsign] = (iata_cs, now)
                return self.route_cache.get(callsign, (None, 0))[0]
            else:
                r.close()
        except Exception:
            pass
        return None

    def get_route(self, callsign):
        route = self.get_cached_route(callsign)
        if route is not None:
            return route
        return self.fetch_route(callsign)

    def get_display_callsign(self, callsign):
        # Prefer IATA callsign if recently cached; fall back to ICAO callsign
        if not callsign:
            return ""
        norm = self._norm_callsign(callsign)
        item = self.callsign_iata_cache.get(norm)
        if item:
            cs, ts = item
            if time.time() - ts <= self.ROUTE_TTL and cs:
                return cs
        # Try to fetch once to populate cache (throttled in fetch_route)
        try:
            self.fetch_route(norm)
        except Exception:
            pass
        item = self.callsign_iata_cache.get(norm)
        if item:
            cs, ts = item
            if time.time() - ts <= self.ROUTE_TTL and cs:
                return cs
        return norm
        
    def draw_png(self, filename, x, y):
        """Draw PNG file at specified position using correct PicoGraphics method"""
        if self.png and PNG_AVAILABLE:
            try:
                # Use the correct PicoGraphics PNG method
                self.png.open_file(filename)
                self.png.decode(x, y)
                gc.collect()
                return True
            except Exception as e:
                print(f"Failed to draw PNG {filename}: {e}")
                return False
        return False
    
    def _to_float(self, value, default=0.0):
        """Safely convert value to float. If list/tuple, take first element."""
        try:
            if isinstance(value, (list, tuple)):
                if len(value) == 0:
                    return float(default)
                value = value[0]
            return float(value)
        except Exception:
            return float(default)

    def sync_ntp(self):
        """Sync RTC from NTP (sets UTC)."""
        try:
            import ntptime
            if self.NTP_HOST:
                try:
                    ntptime.host = self.NTP_HOST
                except Exception:
                    pass
            ntptime.settime()
            self.ntp_last_sync = time.time()
            self.ntp_ok = True
            print("✓ NTP time synced")
        except Exception as e:
            print(f"✗ NTP sync failed: {e}")
            self.ntp_ok = False

    def _last_sunday(self, year, month):
        """Return day of month for the last Sunday in given month/year (UTC)."""
        # Start from day 31 down to 25 to find last Sunday quickly
        for day in range(31, 24, -1):
            try:
                epoch = time.mktime((year, month, day, 0, 0, 0, 0, 0))
                wday = time.localtime(epoch)[6]  # 0=Mon .. 6=Sun
                if wday == 6:
                    return day
            except Exception:
                continue
        return 31

    def _bst_bounds_epoch(self, year):
        """Compute BST start/end epochs for a given year (UTC)."""
        try:
            start_day = self._last_sunday(year, 3)
            end_day = self._last_sunday(year, 10)
            # BST: from last Sunday in March 01:00 UTC to last Sunday in October 01:00 UTC
            start_epoch = time.mktime((year, 3, start_day, 1, 0, 0, 0, 0))
            end_epoch = time.mktime((year, 10, end_day, 1, 0, 0, 0, 0))
            return start_epoch, end_epoch
        except Exception:
            return 0, 0

    def _uk_localtime(self):
        """Return UK local time tuple from RTC (assumed UTC).
        Applies BST between last Sun Mar 01:00 and last Sun Oct 01:00.
        """
        tm_utc = time.localtime()
        year = tm_utc[0]
        try:
            epoch = time.mktime(tm_utc)
        except Exception:
            # Fallback: construct epoch roughly
            epoch = 0
        start_epoch, end_epoch = self._bst_bounds_epoch(year)
        offset = 3600 if (start_epoch and end_epoch and start_epoch <= epoch < end_epoch) else 0
        try:
            return time.localtime(epoch + offset)
        except Exception:
            return tm_utc
    def get_png_dimensions(self, filename):
        """Read PNG IHDR to get width,height without decoding whole image."""
        try:
            with open(filename, 'rb') as f:
                header = f.read(24)
                # PNG signature is 8 bytes; IHDR chunk follows with 4B len, 4B type, then width,height
                if len(header) >= 24 and header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR':
                    w = int.from_bytes(header[16:20], 'big')
                    h = int.from_bytes(header[20:24], 'big')
                    return w, h
        except Exception as e:
            print(f"Could not read PNG dimensions for {filename}: {e}")
        return None, None

    def _clear_clip_safe(self):
        """Ensure clipping is cleared. If remove_clip is unavailable, reset to full area."""
        try:
            self.graphics.remove_clip()
            return
        except Exception:
            pass
        # Fallback: reset clip to full display bounds
        try:
            self.graphics.set_clip(0, 0, self.width, self.height)
        except Exception:
            pass

    def draw_png_fitted_11(self, filename, x, y):
        """Draw a PNG fitted into an 11x11 box at (x,y): center, crop, or integer upscale if possible."""
        if not (self.png and PNG_AVAILABLE):
            return False
        if not filename:
            return False
        src_w, src_h = self.get_png_dimensions(filename)
        try:
            self.png.open_file(filename)
        except Exception as e:
            # Log only once per missing/bad file
            if filename not in self._missing_logo_cache:
                print(f"Missing/invalid PNG: {filename}")
                self._missing_logo_cache.add(filename)
            return False

        # Default target box
        target_w, target_h = 11, 11

        # Try integer upscale if the decoder supports a scale argument
        scale_factor = 1
        if src_w and src_h and src_w <= 11 and src_h <= 11:
            # attempt to upscale to fit as much as possible but not exceed 11
            if src_w > 0 and src_h > 0:
                scale_factor = max(1, min(11 // src_w, 11 // src_h))

        # Compute draw position to center within 11x11
        draw_x, draw_y = x, y
        if src_w and src_h:
            out_w = src_w * scale_factor
            out_h = src_h * scale_factor
            draw_x = x + (target_w - out_w) // 2
            draw_y = y + (target_h - out_h) // 2

        # Clip to the 11x11 box so larger images are cropped
        did_clip = False
        try:
            self.graphics.set_clip(x, y, target_w, target_h)
            did_clip = True
        except Exception:
            did_clip = False

        try:
            # Try calling decode with optional scale parameter (if supported by pngdec)
            if scale_factor > 1:
                try:
                    self.png.decode(draw_x, draw_y, scale=scale_factor)
                except TypeError:
                    # Fallback to no-scale if scale kwarg unsupported
                    self.png.decode(draw_x, draw_y)
            else:
                self.png.decode(draw_x, draw_y)
            gc.collect()
            return True
        except Exception as e:
            if filename not in self._missing_logo_cache:
                print(f"PNG decode failed: {filename}")
                self._missing_logo_cache.add(filename)
            return False
        finally:
            if did_clip:
                self._clear_clip_safe()

    def draw_plane_symbol(self, x, y):
        """Draw plane icon from PNG if available, else a simple silhouette."""
        if self.draw_png_fitted_11("logos/plane.png", x, y):
            return True
        if self.draw_png_fitted_11("plane.png", x, y):
            return True
        # Fallback silhouette
            self.graphics.set_pen(self.WHITE)
            for i in range(11):
                for j in range(11):
                    if (i == 5 and 2 <= j <= 8) or (j == 5 and 3 <= i <= 7) or (i == 2 and j == 5) or (i == 8 and j == 5):
                        self.graphics.pixel(x + i, y + j)
        return True
    
    def get_airline_png_filename(self, airline_code):
        """Get PNG filename for airline code"""
        # Return filename based on airline code
        # Files should be named like: BAW.png, VIR.png, etc.
        # Prefer logos/ subfolder if present
        candidate = f"logos/{airline_code}.png"
        try:
            os.stat(candidate)
            return candidate
        except Exception:
            root_candidate = f"{airline_code}.png"
            try:
                os.stat(root_candidate)
                return root_candidate
            except Exception:
                return None
    
    # Removed old color-block fallback methods; we now use plane symbol when a logo is missing
    
    def draw_plane_icon_with_time(self):
        """Draw plane icon and multi-line centered date/time using tiny 3x5 font."""
        # Draw plane icon (fitted 11x11) using logo or silhouette fallback
        self.draw_plane_symbol(0, 0)

        # Use UK local time (UTC with BST adjustment)
        current_time = self._uk_localtime()
        date_str = f"{current_time[2]:02d}/{current_time[1]:02d}"
        time_str = f"{current_time[3]:02d}:{current_time[4]:02d}"
        
        # Render tiny text (3x5) centered in right-hand area
        left_x = 13
        avail_w = max(0, self.width - left_x)

        date_w = self.tiny_text_width(date_str)
        time_w = self.tiny_text_width(time_str)
        block_w = max(date_w, time_w)
        draw_x = left_x + max(0, (avail_w - block_w) // 2)

        # Date on first line (y=0), time on second line (y=6 to create 1px gap)
        self.draw_tiny_text(date_str, draw_x, 0, self.LIGHTBLUE)
        self.draw_tiny_text(time_str, draw_x, 6, self.YELLOW)
    
    def draw_corner_indicators(self, color):
        """Draw LEDs in corners to show system status"""
        self.graphics.set_pen(color)
        # Draw in actual corners
        self.graphics.pixel(0, 0)                          # Top-left
        self.graphics.pixel(self.width - 1, 0)             # Top-right
        self.graphics.pixel(0, self.height - 1)            # Bottom-left
        self.graphics.pixel(self.width - 1, self.height - 1)  # Bottom-right
    
    def draw_text_no_scroll(self, text, x, y, color):
        """Draw text without scrolling, truncate if too long"""
        self.graphics.set_pen(color)
        
        # Try to use smallest available font
        try:
            self.graphics.set_font("bitmap6")
        except:
            pass
            
        # Truncate text to fit without scrolling
        max_chars = (self.width - x) // 4  # Rough estimate
        if len(text) > max_chars:
            text = text[:max_chars]
            
        self.graphics.text(text, x, y, scale=1)

    def draw_callsign_two_tone(self, callsign, x, y, code_color, suffix_color):
        """Draw callsign as CODE+SUFFIX with different colors. Detect IATA vs ICAO to set code length (2 vs 3)."""
        # Ensure no clipping interferes with text
        self._clear_clip_safe()
        # Use small bitmap font if available
        try:
            self.graphics.set_font("bitmap6")
        except:
            pass

        max_w = max(0, self.width - x)
        if max_w <= 0:
            return

        cs = (callsign or "").upper()
        # Heuristic: if first 3 are all letters and not in IATA airline code set, default to 3; otherwise 2
        # Simpler: if third char is a digit, use 2; else 3. Works for most IATA (AA123, BA4832) vs ICAO (BAW123).
        airline_len = 2 if (len(cs) >= 3 and cs[2].isdigit()) else 3
        code = cs[:airline_len]
        suffix = cs[airline_len:] if len(cs) > airline_len else ""

        def fit_text(s, limit_w):
            if not s or limit_w <= 0:
                return "", 0
            # Fast path: fits as-is
            w = int(self.graphics.measure_text(s, scale=1))
            if w <= limit_w:
                return s, w
            # Trim until it fits
            while s:
                s = s[:-1]
                w = int(self.graphics.measure_text(s, scale=1))
                if w <= limit_w:
                    return s, w
            return "", 0

        # Fit and draw code
        code_draw, code_w = fit_text(code, max_w)
        if code_draw:
            self.graphics.set_pen(code_color)
            self.graphics.text(code_draw, x, y, scale=1)

        # Fit and draw suffix right after code
        rem_w = max(0, max_w - code_w)
        if rem_w > 0 and suffix:
            suffix_draw, _ = fit_text(suffix, rem_w)
            if suffix_draw:
                self.graphics.set_pen(suffix_color)
                self.graphics.text(suffix_draw, x + code_w, y, scale=1)

    def draw_callsign_two_tone_at_offset(self, callsign, y_offset):
        # Helper for animation: draws at vertical offset, keeping x fixed
        callsign = callsign or ""
        self.draw_callsign_two_tone(callsign, 13, 2 + y_offset, self.WHITE, self.LIGHTBLUE)

    def draw_logo_for_callsign(self, callsign):
        code = (callsign[:3] if callsign else "").upper()
        self.draw_airline_icon(0, 0, code)
        
    def connect_wifi(self):
        """Connect to WiFi network"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            self.wifi_connected = True
            return True
            
        print("Connecting to WiFi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Wait for connection
        max_wait = 10
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3:
                break
            max_wait -= 1
            time.sleep(1)
            
        if wlan.status() != 3:
            print("WiFi connection failed")
            self.wifi_connected = False
            return False
        else:
            print("WiFi connected")
            self.wifi_connected = True
            return True
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points on Earth using Haversine formula"""
        R = 6371  # Earth's radius in km
        lat1 = self._to_float(lat1)
        lon1 = self._to_float(lon1)
        lat2 = self._to_float(lat2)
        lon2 = self._to_float(lon2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2) * math.sin(dlat/2) + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlon/2) * math.sin(dlon/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    def get_bearing(self, lat1, lon1, lat2, lon2):
        """Calculate bearing from point 1 to point 2"""
        lat1 = self._to_float(lat1)
        lon1 = self._to_float(lon1)
        lat2 = self._to_float(lat2)
        lon2 = self._to_float(lon2)
        dlon = math.radians(lon2 - lon1)
        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        
        y = math.sin(dlon) * math.cos(lat2)
        x = (math.cos(lat1) * math.sin(lat2) - 
             math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
        
        bearing = math.atan2(y, x)
        return (math.degrees(bearing) + 360) % 360
    
    def is_commercial_flight(self, plane):
        """Check if this is a commercial flight we want to display"""
        callsign = plane.get('callsign', '').strip()
        
        # Must have a callsign
        if not callsign or callsign == 'Unknown':
            return False
            
        # Check if it's a known commercial airline
        airline_code = callsign[:3].upper()
        if airline_code not in self.commercial_airlines:
            return False
            
        # Filter out low altitude flights (likely small aircraft)
        altitude = plane.get('altitude', 0)
        if altitude < 3000:  # Below 3000 meters (~10,000 feet)
            return False
            
        # Must be airborne (not on ground)
        if plane.get('on_ground', False):
            return False
            
        return True
    
    # Removed airline color mapping; no longer used for fallbacks
    
    def draw_airline_icon(self, x, y, airline_code):
        """Draw airline logo PNG if available; otherwise fallback colored 11x11 block."""
        filename = self.get_airline_png_filename(airline_code)
        if not self.draw_png_fitted_11(filename, x, y):
            # Fallback to plane symbol instead of color block
            self.draw_plane_symbol(x, y)

    def ensure_dir(self, path):
        try:
            os.stat(path)
        except Exception:
            try:
                os.mkdir(path)
            except Exception:
                pass

    def file_size(self, path):
        try:
            st = os.stat(path)
            return st[6] if isinstance(st, tuple) and len(st) > 6 else st[0]
        except Exception:
            return -1

    def sync_github_logos(self):
        """Fetch PNGs for known airlines without listing the GitHub directory to avoid large JSON.
        Attempts direct downloads from a known raw base URL.
        """
        self.ensure_dir("logos")

        # If listing is explicitly allowed, fall back to API listing method
        if self.ALLOW_API_LOGO_LISTING:
            try:
                api_url = GITHUB_LOGOS_API_URL
            except NameError:
                api_url = None
            if api_url:
                # try listing (may OOM); if it fails, fall back silently
                try:
                    headers = {'User-Agent': 'GalacticUnicorn-PlaneTracker/1.0', 'Accept': 'application/vnd.github+json'}
                    try:
                        token = GITHUB_TOKEN
                        if token:
                            headers['Authorization'] = f'Bearer {token}'
                    except NameError:
                        pass
                    try:
                        resp = urequests.get(api_url, headers=headers, timeout=10)
                    except TypeError:
                        resp = urequests.get(api_url, headers=headers)
                    if resp.status_code == 200:
                        listing = resp.json()
                        resp.close()
                        # best-effort download from listing
                        for item in listing:
                            try:
                                if not item or item.get('type') != 'file':
                                    continue
                                name = item.get('name', '')
                                if not name.lower().endswith('.png'):
                                    continue
                                download_url = item.get('download_url')
                                local_path = f"logos/{name}"
                                # Skip if already present
                                if self.file_size(local_path) > 0:
                                    continue
                                try:
                                    r = urequests.get(download_url, headers={'User-Agent': 'GalacticUnicorn-PlaneTracker/1.0'}, timeout=10)
                                except TypeError:
                                    r = urequests.get(download_url, headers={'User-Agent': 'GalacticUnicorn-PlaneTracker/1.0'})
                                if r.status_code == 200:
                                    data = r.content
                                    r.close()
                                    with open(local_path, 'wb') as f:
                                        f.write(data)
                                else:
                                    r.close()
                                gc.collect()
                            except Exception:
                                gc.collect()
                        return
                    else:
                        resp.close()
                except Exception:
                    # fall through to raw base method
                    pass

        # Raw base method: try known airline codes only (small set) to avoid listing
        known_codes = list(self.commercial_airlines)
        for code in known_codes:
            print(f"Downloading logo for {code}")
            name = f"{code}.png"
            local_path = f"logos/{name}"
            if self.file_size(local_path) > 0:
                print(f"Logo for {code} already exists")
                continue
            url = f"{self.GITHUB_LOGOS_RAW_BASE}/{name}"
            try:
                try:
                    r = urequests.get(url, headers={'User-Agent': 'GalacticUnicorn-PlaneTracker/1.0'}, timeout=10)
                except TypeError:
                    r = urequests.get(url, headers={'User-Agent': 'GalacticUnicorn-PlaneTracker/1.0'})
                if r.status_code == 200:
                    data = r.content
                    r.close()
                    try:
                        with open(local_path, 'wb') as f:
                            f.write(data)
                    except Exception:
                        pass
                else:
                    r.close()
            except Exception:
                pass
            gc.collect()
    
    def draw_corner_indicators(self, color):
        """Draw LEDs in corners to show system status"""
        self.graphics.set_pen(color)
        # Draw in actual corners
        self.graphics.pixel(0, 0)                          # Top-left
        self.graphics.pixel(self.width - 1, 0)             # Top-right
        self.graphics.pixel(0, self.height - 1)            # Bottom-left
        self.graphics.pixel(self.width - 1, self.height - 1)  # Bottom-right
    
    def draw_scrolling_text(self, text, x, y, color, max_width=None):
        """Draw text that scrolls horizontally if too long"""
        if max_width is None:
            max_width = self.width - x
            
        self.graphics.set_pen(color)
        
        # Measure text width
        text_width = self.graphics.measure_text(text)
        
        if text_width <= max_width:
            # Text fits, draw normally
            self.graphics.text(text, x, y, scale=1)
            return text_width
        else:
            # Text too long, scroll it
            current_time = time.time()
            if current_time - self.last_scroll_time > 0.15:  # Scroll every 150ms
                self.scroll_offset += 1
                self.last_scroll_time = current_time
                
            # Reset scroll when we've scrolled past the text
            if self.scroll_offset > text_width + max_width:
                self.scroll_offset = 0
                
            # Draw the scrolled text
            scroll_x = x - self.scroll_offset
            self.graphics.text(text, scroll_x, y, scale=1)
            return max_width
    
    def get_auth_token(self):
        """Get OAuth token from OpenSky API using client credentials or username/password"""
        current_time = time.time()
        
        # Check if we have a valid token
        if self.auth_token and current_time < self.token_expires:
            return self.auth_token
            
        try:
            # Try OAuth client credentials first (preferred method)
            if OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET:
                return self.get_oauth_client_token()
            # Fall back to username/password OAuth
            elif OPENSKY_USERNAME and OPENSKY_PASSWORD:
                return self.get_oauth_user_token()
            else:
                return None
                
        except Exception as e:
            print(f"Token request failed: {e}")
            return None
    
    def get_oauth_client_token(self):
        """Get OAuth token using client credentials flow"""
        try:
            # OpenSky uses Keycloak for OAuth authentication
            token_url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
            
            print(f"Requesting OAuth token from: {token_url}")
            print(f"Client ID: {OPENSKY_CLIENT_ID}")
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # OAuth client credentials flow - send credentials in body
            data = f"grant_type=client_credentials&client_id={OPENSKY_CLIENT_ID}&client_secret={OPENSKY_CLIENT_SECRET}"
            
            print("Making OAuth token request...")
            response = urequests.post(token_url, headers=headers, data=data)
            print(f"OAuth response status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                print(f"Token response keys: {list(token_data.keys())}")
                response.close()
                
                if 'access_token' in token_data:
                    self.auth_token = token_data['access_token']
                    # Use expires_in if provided, otherwise default to 25 minutes
                    expires_in = token_data.get('expires_in', 1800)  # Default 30 min
                    self.token_expires = time.time() + expires_in - 300  # Refresh 5 min early
                    print(f"✓ Got OAuth token, expires in {expires_in} seconds")
                    print(f"Token preview: {self.auth_token[:20]}...")
                    return self.auth_token
                else:
                    print("✗ No access_token in response")
                    return None
            else:
                print(f"✗ OAuth client token failed: {response.status_code}")
                try:
                    error_text = response.text
                    print(f"Error response: {error_text[:200]}")
                except:
                    print("Could not read error response")
                    
                if response.status_code == 403:
                    print("Check your client ID and secret in SECRETS.py")
                elif response.status_code == 400:
                    print("Bad request - check client credentials format")
                    
                response.close()
                return None
                
        except Exception as e:
            print(f"✗ OAuth client token error: {e}")
            import sys
            sys.print_exception(e)
            return None
    
    def get_oauth_user_token(self):
        """Get OAuth token using username/password (legacy method)"""
        try:
            # Request new token using username/password
            auth_url = "https://opensky-network.org/api/auth/login"
            
            # Create basic auth header for token request
            import ubinascii
            credentials = ubinascii.b2a_base64(f"{OPENSKY_USERNAME}:{OPENSKY_PASSWORD}".encode()).decode().strip()
            headers = {'Authorization': f'Basic {credentials}'}
            
            response = urequests.post(auth_url, headers=headers)
            
            if response.status_code == 200:
                token_data = response.json()
                response.close()
                
                if 'token' in token_data:
                    self.auth_token = token_data['token']
                    # Tokens expire after 30 minutes, refresh after 25 minutes
                    self.token_expires = time.time() + 1500  # 25 minutes
                    return self.auth_token
            else:
                print(f"OAuth user token failed: {response.status_code}")
                response.close()
                return None
                
        except Exception as e:
            print(f"OAuth user token error: {e}")
            return None
    
    def fetch_planes(self):
        """Fetch plane data from OpenSky API"""
        self.fetching_data = True
        self.api_success = False
        
        # Clear any existing planes to free memory
        self.planes = []
        gc.collect()
        
        try:
            # Calculate bounding box
            lat_delta = SEARCH_RADIUS_KM / 111.0
            lon_delta = SEARCH_RADIUS_KM / (111.0 * math.cos(math.radians(HOME_LAT)))
            
            lamin = HOME_LAT - lat_delta
            lamax = HOME_LAT + lat_delta
            lomin = HOME_LON - lon_delta
            lomax = HOME_LON + lon_delta
            
            # Build URL
            url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lamax={lamax}&lomin={lomin}&lomax={lomax}"
            
            # Set up authentication headers
            headers = {}
            auth_failed = False
            
            # Try OAuth first (client credentials preferred, then username/password)
            if OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET:
                token = self.get_auth_token()
                if token:
                    headers['Authorization'] = f'Bearer {token}'
                else:
                    auth_failed = True
            elif OPENSKY_USERNAME and OPENSKY_PASSWORD:
                token = self.get_auth_token()
                if token:
                    headers['Authorization'] = f'Bearer {token}'
                else:
                    # Fall back to basic auth if OAuth fails
                    try:
                        import ubinascii
                        credentials = ubinascii.b2a_base64(f"{OPENSKY_USERNAME}:{OPENSKY_PASSWORD}".encode()).decode().strip()
                        headers['Authorization'] = f'Basic {credentials}'
                    except Exception as e:
                        auth_failed = True
            
            # Add user agent to help with rate limiting
            headers['User-Agent'] = 'GalacticUnicorn-PlaneTracker/1.0'
            
            # If authentication completely failed, don't make the request
            if auth_failed and (OPENSKY_CLIENT_ID or OPENSKY_USERNAME):
                return
            
            print(f"Making API request to: {url}")
            if 'Authorization' in headers:
                auth_type = "Bearer" if "Bearer" in headers['Authorization'] else "Basic"
                print(f"Using {auth_type} authentication")
            else:
                print("Using anonymous access")
                
            try:
                response = urequests.get(url, headers=headers, timeout=10)
            except TypeError:
                # Some urequests versions don't support timeout kwarg
                response = urequests.get(url, headers=headers)
            print(f"API response status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except MemoryError:
                    print("JSON parse MemoryError")
                    self.last_error_message = "UPDATE ERROR"
                    response.close()
                    return
                response.close()
                
                # Clear old planes and collect garbage before processing new data
                self.planes = []
                gc.collect()
                
                if data and 'states' in data and data['states']:
                    count_added = 0
                    for state in data['states']:
                        if state[6] is not None and state[5] is not None:  # Has lat/lon
                            distance = self.haversine_distance(HOME_LAT, HOME_LON, state[6], state[5])
                            if distance <= SEARCH_RADIUS_KM:
                                # Apply altitude filters if configured
                                altitude = state[7] if state[7] else 0
                                if (ALTITUDE_FILTER_MIN <= altitude <= ALTITUDE_FILTER_MAX and
                                    (SHOW_GROUND_AIRCRAFT or not (state[8] if state[8] is not None else False))):
                                    
                                    plane = {
                                        'icao24': state[0],
                                        'callsign': state[1].strip() if state[1] else 'Unknown',
                                        'latitude': state[6],
                                        'longitude': state[5],
                                        'altitude': altitude,
                                        # omit velocity/heading to reduce memory
                                        'distance': distance,
                                        # compute bearing only when needed later
                                        'on_ground': state[8] if state[8] is not None else False
                                    }
                                    
                                    # Only add commercial flights
                                    if self.is_commercial_flight(plane):
                                        self.planes.append(plane)
                                        count_added += 1
                                        if count_added >= self.MAX_PLANES:
                                            break
                
                # Sort by distance for information only
                self.planes.sort(key=lambda x: x['distance'])
                print(f"✓ Found {len(self.planes)} flights (capped {len(self.planes)}/{self.MAX_PLANES}) in {SEARCH_RADIUS_KM}km radius")
                
                # Merge into persistent display queue
                try:
                    self.merge_display_queue(self.planes)
                except Exception as e:
                    print(f"Queue merge error: {e}")
                self.api_success = True
                
                # Clean up the large data structure
                del data
                gc.collect()
                
            elif response.status_code == 401:
                print("✗ 401 Unauthorized - token expired/invalid")
                response.close()
                # Clear invalid token
                self.auth_token = None
                self.token_expires = 0
                # Wait before retry
                self.fetch_due_at = time.time() + 60
                
            elif response.status_code == 403:
                print("✗ 403 Forbidden - check credentials")
                response.close()
                # Clear invalid token and wait longer
                self.auth_token = None
                self.token_expires = 0
                self.fetch_due_at = time.time() + 300  # 5 minute delay
                
            elif response.status_code == 503:
                print("✗ 503 Service Unavailable - OpenSky API down")
                response.close()
                # Wait longer before next attempt when API is down
                self.fetch_due_at = time.time() + 60  # Wait 1 minute
                
            elif response.status_code == 429:
                print("✗ 429 Rate Limited")
                response.close()
                # Wait much longer if rate limited
                self.fetch_due_at = time.time() + 300  # 5 minute delay
                
            else:
                print(f"✗ API Error: {response.status_code}")
                response.close()
                
        except MemoryError:
            print("API request MemoryError")
            self.last_error_message = "UPDATE ERROR"
        except Exception as e:
            print(f"API request failed: {e}")
            self.last_error_message = "UPDATE ERROR"
            # Force garbage collection on errors too
            gc.collect()
        
        self.fetching_data = False
        gc.collect()  # Clean up memory
    
    def merge_display_queue(self, new_list):
        """Merge new planes into persistent display_queue.
        Keep existing order for survivors, drop missing, append new planes.
        """
        # Prepare key set from new list
        new_keys = []
        seen = set()
        for p in new_list:
            k = p.get('icao24') or p.get('callsign')
            if not k or k in seen:
                continue
            seen.add(k)
            new_keys.append(k)

        def key_of(p):
            return p.get('icao24') or p.get('callsign')

        # Filter current queue to those still present
        filtered = [p for p in self.display_queue if key_of(p) in seen]

        # Append brand-new planes in order
        existing = set(key_of(p) for p in filtered)
        for p in new_list:
            k = key_of(p)
            if k and k not in existing:
                filtered.append(p)
                existing.add(k)

        self.display_queue = filtered

    def _frame_cycle_index(self):
        # Cycle: 4 plane frames then 1 time frame
        return self.frame_index % 5
    
    def draw_info_display(self):
        """Draw clean airline info display"""
        self.graphics.set_pen(self.BLACK)
        self.graphics.clear()
        
        # Clock only mode overrides
        if self.clock_only:
            # Reset animation and frame key so we snap to the next plane when leaving clock
            self.anim_active = False
            self.current_frame_key = None
            self.next_frame_key = None
            self.draw_plane_icon_with_time()
            return
        
        # Show yellow corners when fetching data
        if self.fetching_data:
            self.draw_corner_indicators(self.YELLOW)
            return
        
        # Show plane icon and time when API successful but no commercial flights found
        if self.api_success and not self.planes:
            self.draw_plane_icon_with_time()
            return
            
        # Show yellow corners if API failed or no response yet
        if not self.api_success:
            self.draw_corner_indicators(self.YELLOW)
            # Show error text if available
            if self.last_error_message:
                try:
                    self.graphics.set_font("bitmap6")
                except:
                    pass
                self.graphics.set_pen(self.YELLOW)
                # Center "UPDATE ERROR" if it fits
                msg = self.last_error_message
                w = int(self.graphics.measure_text(msg, scale=1))
                x = max(0, (self.width - w) // 2)
                self.graphics.text(msg, x, 2, scale=1)
            return
        
        # Rotate frames every 3 seconds: plane, plane, plane, plane, time
        current_time = time.time()
        if current_time - self.last_frame_time >= 4:
            self.frame_index += 1
            self.last_frame_time = current_time

        # Plane count overlay supersedes normal content
        now = time.time()
        if self.count_overlay_until and now < self.count_overlay_until:
            self.graphics.set_pen(self.BLACK)
            self.graphics.clear()
            # Plane icon centered left and count centered right
            self.draw_plane_symbol(0, 0)
            count = len(self.display_queue)
            msg = f"{count} Flights" if count != 1 else "1 Flight"
            try:
                self.graphics.set_font("bitmap6")
            except:
                pass
            self.graphics.set_pen(self.CYAN)
            w = int(self.graphics.measure_text(msg, scale=1))
            x = max(13, (self.width - w) // 2)
            self.graphics.text(msg, x, 2, scale=1)
            return

        if not self.display_queue:
            self.draw_plane_icon_with_time()
            return

        cycle = self._frame_cycle_index()
        if cycle == 4:
            self.draw_plane_icon_with_time()
            return

        num_planes = len(self.display_queue)
        if num_planes <= 0:
            self.draw_plane_icon_with_time()
            return

        plane_cycle = self.frame_index // 5
        plane_idx = (plane_cycle * 4 + cycle) % num_planes
        try:
            plane = self.display_queue[plane_idx]
        except Exception:
            self.draw_plane_icon_with_time()
            return
        callsign = plane.get('callsign', '').strip()

        # Draw current plane without animation
        self.draw_logo_for_callsign(callsign)
        display_cs = self.get_display_callsign(callsign)
        self.draw_callsign_two_tone(display_cs, 13, -1, self.WHITE, self.LIGHTBLUE)
        route = self.get_route(callsign)
        if route:
            # Draw route with normal font: YELLOW code, ORANGE arrow, YELLOW code
            try:
                self.graphics.set_font("bitmap6")
            except Exception:
                pass
            # Split on '>'
            parts = route.split('>')
            if len(parts) == 2:
                o, d = parts[0], parts[1]
                x = 13
                y = 5
                self.graphics.set_pen(self.YELLOW)
                self.graphics.text(o, x, y, scale=1)
                x += int(self.graphics.measure_text(o, scale=1))
                self.graphics.set_pen(self.ORANGE)
                self.graphics.text('>', x, y, scale=1)
                x += int(self.graphics.measure_text('>', scale=1))
                self.graphics.set_pen(self.YELLOW)
                self.graphics.text(d, x, y, scale=1)

        # (removed bottom overlay; handled earlier as a full-screen overlay)
    
    def update_display(self):
        """Update the LED matrix display"""
        # Night mode check (UK time)
        # Compute UK local time (UTC with BST) for night-mode decision
        tm = self._uk_localtime()
        hour = tm[3]
        self.night_mode = (self.NIGHT_START_HOUR <= hour < self.NIGHT_END_HOUR)
        # Dim during night, full brightness during day
        try:
            self.gu.set_brightness(self.NIGHT_BRIGHTNESS if self.night_mode else self.DAY_BRIGHTNESS)
        except Exception:
            pass

        if self.night_mode:
            # Clock only, no API activity here
            self.graphics.set_pen(self.BLACK)
            self.graphics.clear()
            self.draw_plane_icon_with_time()
        else:
            self.draw_info_display()
        self.gu.update(self.graphics)
        # Periodic garbage collection to prevent memory leaks
        gc.collect()
    
    def run(self):
        """Main program loop"""
        # Connect to WiFi
        if not self.connect_wifi():
            while True:
                # Show red corners if WiFi failed
                self.graphics.set_pen(self.BLACK)
                self.graphics.clear()
                self.draw_corner_indicators(self.RED)
                # Show WIFI ERROR message
                try:
                    self.graphics.set_font("bitmap6")
                except:
                    pass
                self.graphics.set_pen(self.RED)
                msg = "WIFI ERROR"
                try:
                    w = int(self.graphics.measure_text(msg, scale=1))
                except Exception:
                    w = len(msg) * 4
                x = max(0, (self.width - w) // 2)
                self.graphics.text(msg, x, 2, scale=1)
                self.gu.update(self.graphics)
                time.sleep(1)
        
        # Sync GitHub logos once at startup
        try:
            self.sync_github_logos()
            self.last_logos_sync = time.time()
        except Exception as e:
            print(f"Logo sync failed: {e}")
        
        # Main loop
        while True:
            current_time = time.time()
            
            # One-time NTP sync soon after boot and periodic resync
            if self.wifi_connected and (not self.ntp_ok or (current_time - self.ntp_last_sync > self.NTP_SYNC_INTERVAL)):
                self.sync_ntp()
            
            # Initialize fetch_due_at so the first loop triggers an update
            if self.fetch_due_at == 0:
                self.fetch_due_at = current_time

            # Periodic GitHub logos re-sync
            if current_time - self.last_logos_sync > self.LOGOS_SYNC_INTERVAL:
                try:
                    self.sync_github_logos()
                except Exception as e:
                    print(f"Logo periodic sync failed: {e}")
                self.last_logos_sync = current_time
                gc.collect()
            
            # Update plane data periodically (skip during night mode)
            if not self.night_mode and current_time >= self.fetch_due_at:
                self.fetch_planes()
                self.last_api_update = current_time
                self.fetch_due_at = current_time + self.API_INTERVAL
            
            # Update display
            self.update_display()
            
            # Handle button presses
            if self.gu.is_pressed(GalacticUnicorn.SWITCH_A):
                # Toggle clock-only mode
                self.clock_only = not self.clock_only
                time.sleep(0.3)  # Debounce
            if self.gu.is_pressed(GalacticUnicorn.SWITCH_B):
                # Show plane count for 5 seconds
                self.count_overlay_until = time.time() + 5
                time.sleep(0.3)
            if self.gu.is_pressed(GalacticUnicorn.SWITCH_D):
                # Force immediate API update
                self.fetch_planes()
                now = time.time()
                self.last_api_update = now
                # Kick the scheduler so periodic updates resume without button
                self.fetch_due_at = now + self.API_INTERVAL
                time.sleep(0.3)
            
            time.sleep(DISPLAY_UPDATE_INTERVAL)

# Create and run the plane tracker
if __name__ == "__main__":
    try:
        tracker = PlaneTracker()
        tracker.run()
    except Exception as e:
        # In production (no Thonny), auto-reset after a crash
        try:
            import sys
            sys.print_exception(e)
        except Exception:
            pass
        try:
            import machine
            machine.reset()
        except Exception:
            pass
