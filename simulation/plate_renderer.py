"""
Synthetic Indian License Plate & Vehicle Crop Image Generator.
Generates realistic HSRP (High Security Registration Plate) crops with
blue IND security strip, chromium hologram icon, bold embossed typography,
and camera sensor noise for multi-camera CCTV demo feeds.
"""

import os
import cv2
import numpy as np
import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Tuple, Optional

OUTPUT_CROPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crops")


class PlateCropRenderer:
    def __init__(self, output_dir: str = OUTPUT_CROPS_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_plate_crop(self, plate_number: str, vehicle_type: str = "Sedan",
                            is_commercial: bool = False,
                            night_mode: bool = False) -> Tuple[str, str]:
        """
        Renders a high-detail synthetic plate crop.
        Returns: (file_path, base64_data_uri)
        """
        plate_str = plate_number.upper().strip()
        width, height = 480, 150

        # Background color: White for private, Yellow for commercial/cab
        if is_commercial:
            bg_color = (245, 200, 30) if not night_mode else (180, 150, 20)
        else:
            bg_color = (245, 245, 248) if not night_mode else (190, 195, 200)

        # Create PIL Image
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Outer black border
        border_color = (25, 25, 30)
        draw.rectangle([4, 4, width - 5, height - 5], outline=border_color, width=4)
        draw.rectangle([8, 8, width - 9, height - 9], outline=(120, 125, 130), width=1)

        # Left Blue HSRP Strip (IND)
        strip_width = 54
        draw.rectangle([9, 9, strip_width, height - 9], fill=(24, 75, 160))

        # Blue strip chromium hologram circle
        draw.ellipse([20, 24, 44, 48], outline=(220, 230, 255), width=2, fill=(60, 110, 200))
        draw.ellipse([27, 31, 37, 41], fill=(240, 245, 255))

        # "IND" Text in Blue Strip
        try:
            ind_font = ImageFont.truetype("arialbd.ttf", 16)
        except Exception:
            ind_font = ImageFont.load_default()
        draw.text((18, 75), "IND", fill=(255, 255, 255), font=ind_font)

        # Main Plate Text (Format e.g. HR 26 DQ 5551)
        formatted_plate = self._format_plate_display(plate_str)

        try:
            # Try high-impact sans-serif font
            plate_font = ImageFont.truetype("arialbd.ttf", 56)
        except Exception:
            try:
                plate_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 52)
            except Exception:
                plate_font = ImageFont.load_default()

        # Center the text in the right section
        text_bbox = draw.textbbox((0, 0), formatted_plate, font=plate_font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        text_x = strip_width + ((width - strip_width) - text_w) // 2
        text_y = (height - text_h) // 2 - 8

        # Embossed shadow effect
        draw.text((text_x + 2, text_y + 2), formatted_plate, fill=(160, 160, 165), font=plate_font)
        draw.text((text_x, text_y), formatted_plate, fill=(15, 18, 22), font=plate_font)

        # Laser watermark code bottom right
        try:
            small_font = ImageFont.truetype("arial.ttf", 10)
        except Exception:
            small_font = ImageFont.load_default()
        draw.text((width - 110, height - 20), "AA10928491", fill=(140, 140, 150), font=small_font)

        # Convert to OpenCV for camera sensor noise and realistic CCTV lighting
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Add camera gaussian noise & subtle vignette
        noise = np.random.normal(0, 4.0, cv_img.shape).astype(np.uint8)
        cv_img = cv2.add(cv_img, noise)

        if night_mode:
            # Slight blue tint and lower brightness
            cv_img = cv2.convertScaleAbs(cv_img, alpha=0.85, beta=-15)

        # Save to disk
        filename = f"crop_{plate_str}_{int(np.random.randint(1000, 9999))}.jpg"
        filepath = os.path.join(self.output_dir, filename)
        cv2.imwrite(filepath, cv_img, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Generate Base64
        _, buffer = cv2.imencode('.jpg', cv_img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        b64_str = base64.b64encode(buffer).decode('utf-8')
        base64_data_uri = f"data:image/jpeg;base64,{b64_str}"

        return filepath, base64_data_uri

    @staticmethod
    def _format_plate_display(raw: str) -> str:
        """Formats e.g. HR26DQ5551 to HR 26 DQ 5551 for visual beauty."""
        clean = raw.upper().replace(" ", "").replace("-", "")
        if len(clean) == 10:
            return f"{clean[0:2]} {clean[2:4]} {clean[4:6]} {clean[6:10]}"
        elif len(clean) == 9:
            return f"{clean[0:2]} {clean[2:4]} {clean[4:5]} {clean[5:9]}"
        return raw


# Global singleton instance
renderer = PlateCropRenderer()
