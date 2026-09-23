#!/bin/bash
# Builds "LEOBOG AMG65 Studio.app" into dist/. Requires: pip install -r requirements.txt pyinstaller
set -e
cd "$(dirname "$0")"

clang -dynamiclib -arch arm64 -arch x86_64 -o libusbflash.dylib usb_flash_bridge.c \
  -framework IOKit -framework CoreFoundation

pyinstaller --noconfirm --clean --windowed \
  --name "LEOBOG AMG65 Studio" \
  --osx-bundle-identifier com.leobog.amg65.studio \
  --add-data "index.html:." \
  --add-data "app.js:." \
  --add-data "driver.js:." \
  --add-data "layout.js:." \
  --add-data "ledmatrix.js:." \
  --add-data "styles.css:." \
  --add-data "assets:assets" \
  --add-binary "libusbflash.dylib:." \
  app_main.py

echo "Xong: dist/LEOBOG AMG65 Studio.app"
