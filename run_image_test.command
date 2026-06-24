#!/bin/bash
# Double-click this file in Finder to generate a sample AI image.
# (First, make sure GOOGLE_API_KEY is filled in the .env file in this folder.)

cd "$(dirname "$0")" || exit 1

echo "================================================"
echo "  LinkedIn Autoposter — sample image test"
echo "================================================"
echo

if ! grep -qE '^GOOGLE_API_KEY=.+' .env 2>/dev/null; then
  echo "!! GOOGLE_API_KEY is empty in .env"
  echo "   Open .env in this folder, paste your key after GOOGLE_API_KEY="
  echo "   (get one at https://aistudio.google.com/apikey), save, then run again."
  echo
  echo "Press any key to close."
  read -n 1 -s
  exit 1
fi

# The image test only needs these two packages (not playwright).
echo "==> Checking Python packages (requests, google-genai)..."
if ! python3 -c "import requests, google.genai" 2>/dev/null; then
  echo "    Installing (first run only, can take a minute)..."
  python3 -m pip install --quiet --upgrade requests google-genai \
    || python3 -m pip install --quiet --break-system-packages --upgrade requests google-genai \
    || python3 -m pip install --quiet --user --break-system-packages --upgrade requests google-genai
fi

# Re-check; if still missing, show a clear message instead of a traceback.
if ! python3 -c "import requests, google.genai" 2>/dev/null; then
  echo
  echo "!! Could not install required packages automatically."
  echo "   Run this once in Terminal, then double-click again:"
  echo "     python3 -m pip install --break-system-packages requests google-genai"
  echo
  echo "Press any key to close."
  read -n 1 -s
  exit 1
fi

echo "==> Generating a sample image..."
echo
python3 test_image.py

echo
echo "Done. Press any key to close."
read -n 1 -s
