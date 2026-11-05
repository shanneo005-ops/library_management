"""
make_qr_poster.py  -  separate tool (not part of the admin website)
-------------------------------------------------------------------
Makes a printable A4 poster with the member QR code, then opens it in your browser.

How to use (PyCharm): right-click this file > Run 'make_qr_poster'
  - Press Enter to use this computer's Wi-Fi address, or paste your own link
    (for example the address of the hosted website).
  - The browser opens the poster. Click "Print Poster" (choose A4 and turn on
    "Background graphics"), or choose "Save as PDF".

Needs only Python - no installs. The browser needs internet once to draw the QR.
"""
import json
import socket
import sys
import webbrowser
from pathlib import Path

PORT = 5000   # the port your app.py runs on


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))     # UDP: nothing is actually sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


POSTER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Library QR Poster</title>
<style>
  :root { --tan:#dfccad; --brown:#b3905b; }
  * { box-sizing:border-box; }
  @page { size:A4 portrait; margin:0; }
  html, body { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  body { margin:0; background:#eee; font-family:"Times New Roman", Times, serif; color:#000; }
  .toolbar { text-align:center; padding:14px; font:13px Arial, sans-serif; color:#555; }
  .btn { display:inline-block; background:var(--brown); border:2px solid #111; border-radius:12px;
         padding:12px 26px; font:bold 15px Arial, sans-serif; cursor:pointer; color:#000; margin:0 6px; }
  .poster { width:210mm; height:297mm; margin:0 auto 24px; background:var(--tan); padding:10mm;
            display:flex; flex-direction:column; }
  .poster-inner { flex:1; background:#fff; border:2.5mm solid var(--brown); border-radius:12mm;
                  display:flex; flex-direction:column; align-items:center; text-align:center; padding:8mm 10mm; }
  h1 { font-size:12mm; line-height:1.1; margin:0 0 3mm; }
  .tag { font-size:6mm; margin:0 0 6mm; }
  .qr-frame { background:#fff; border:1mm solid #000; border-radius:6mm; padding:6mm; }
  .qr-frame img { display:block; width:100mm; height:100mm; image-rendering:pixelated; }
  .scan { margin:6mm 0; background:var(--brown); border:1mm solid #000; border-radius:6mm; white-space:nowrap;
          padding:2.5mm 10mm; font:bold 7.5mm Arial, sans-serif; letter-spacing:.5mm; }
  .steps { text-align:left; font-size:5mm; line-height:1.4; margin:0 0 auto; padding-left:9mm; }
  .steps li { margin-bottom:1.5mm; }
  .url { font:4mm Arial, sans-serif; color:#333; word-break:break-all; margin-top:6mm; }
  .wifi { font:3.6mm Arial, sans-serif; color:#555; margin-top:2mm; }
  .error { color:#b00020; font:bold 14px Arial, sans-serif; }
  @media print { body { background:var(--tan); } .toolbar { display:none; } .poster { margin:0; overflow:hidden; } }
</style></head>
<body>
<div class="toolbar">
  <button class="btn" onclick="window.print()">Print Poster</button><br>
  In the print window choose paper size A4 and turn on &ldquo;Background graphics&rdquo; for the brown colours.
</div>
<div class="poster"><div class="poster-inner">
  <h1>Library Book<br>Management System</h1>
  <div class="tag">Want to borrow a book?</div>
  <div class="qr-frame"><div id="qr"></div></div>
  <div class="scan">SCAN TO BORROW A BOOK</div>
  <ol class="steps">
    <li>Scan the QR code with your phone camera.</li>
    <li>Search for the book you want.</li>
    <li>Tap <strong>Borrow / Request</strong> and fill in your details.</li>
    <li>Save or print your receipt &mdash; it shows your return date.</li>
  </ol>
  <div class="url" id="url"></div>
  <div class="wifi">Connect to the library Wi-Fi first if the page does not open.</div>
</div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js"></script>
<script>
  (function () {
    var link = __URL__;
    document.getElementById("url").textContent = link;
    var box = document.getElementById("qr");
    try {
      var qr = qrcode(0, "Q");
      qr.addData(link);
      qr.make();
      box.innerHTML = qr.createImgTag(10, 0);
    } catch (e) {
      box.innerHTML = "<p class='error'>Could not load the QR generator. Check your internet connection and reload.</p>";
    }
  })();
</script>
</body></html>
"""


def main():
    default = f"http://{get_lan_ip()}:{PORT}/member"
    if len(sys.argv) > 1:
        link = sys.argv[1].strip()
    else:
        print(f"Link members will open (press Enter to use {default}):")
        link = input("> ").strip() or default
    if not link.lower().startswith(("http://", "https://")):
        link = "http://" + link

    out = Path(__file__).with_name("qr_poster.html")
    out.write_text(POSTER.replace("__URL__", json.dumps(link)), encoding="utf-8")
    print(f"Poster saved: {out}")
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
