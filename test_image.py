#!/usr/bin/env python3
"""Quick check: does your GOOGLE_API_KEY actually generate an Imagen image?

Run:  python test_image.py

It loads .env, calls the SAME image pipeline the autoposter uses (Imagen 4 Ultra,
2K, the upgraded cinematic prompt), saves the result to sample_image.png, and opens
it. No LinkedIn posting and no queue needed — this only tests image generation.
"""

import os
import shutil
import sys

# Reuse the poster's exact image path (this also loads .env and reads
# GOOGLE_API_KEY / IMAGEN_MODEL / IMAGE_SIZE).
import linkedin_poster as lp

SAMPLE_PROMPT = (
    "A human hand and a sleek matte-black robotic hand together assembling a "
    "glowing circuit board on a dark workbench, blue sparks suspended in the air, "
    "dramatic side light, shallow depth of field"
)


def main():
    if not lp.GOOGLE_API_KEY:
        sys.exit(
            "No GOOGLE_API_KEY found.\n"
            "  -> Open .env and set:  GOOGLE_API_KEY=AIza...\n"
            "     (get/check a key at https://aistudio.google.com/apikey)\n"
            "Then run this again."
        )

    print("Key detected.")
    print("  Model: %s" % lp.IMAGEN_MODEL)
    print("  Size : %s" % lp.IMAGE_SIZE)
    print("Generating a sample image (this can take 10-30s)...\n")

    path = lp.generate_image(SAMPLE_PROMPT, post_id=999, style="photo")

    if not path:
        sys.exit(
            "\nImage generation did NOT return an image. See the warning above.\n"
            "Most common causes:\n"
            "  1. Billing not enabled on THIS key's project (Imagen needs billing).\n"
            "  2. The 'another payment profile has an issue' warning is on the\n"
            "     project your key belongs to -> fix it in Google Cloud Console.\n"
            "  3. google-genai not installed -> pip install -r requirements.txt\n"
            "  4. The model name is wrong -> check IMAGEN_MODEL in .env."
        )

    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_image.png")
    shutil.copy(path, dest)
    print("\nSUCCESS — your key generates images.")
    print("Saved to: %s" % dest)
    try:
        lp.open_image(dest)
    except Exception:
        print("(Open it manually to view.)")


if __name__ == "__main__":
    main()
