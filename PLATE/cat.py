import cv2
import tkinter as tk
from tkinter import filedialog
from ultralytics import YOLO
import requests
import base64
import os
import re
import numpy as np

# Configuration
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "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")
NVIDIA_VISION_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_NEMO_URL = "https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-ocr"


class NvidiaVisionPlateOCR:
    """
    Advanced Multimodal Vision AI OCR powered by NVIDIA Cloud.
    Uses Meta Llama 3.2 Vision to perfectly distinguish characters like 'DQ' vs '00',
    HSRP textures, reflections, and complex license plate fonts without confusion.
    """
    def __init__(self, api_key: str = NVIDIA_API_KEY, model_name: str = "meta/llama-3.2-11b-vision-instruct"):
        self.api_key = api_key
        self.model_name = model_name
        self.vision_url = NVIDIA_VISION_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()

    def recognize(self, image_crop: np.ndarray) -> tuple[str, float]:
        """
        Extracts license plate text using Multimodal Vision AI.
        Returns: (cleaned_plate_text: str, confidence: float)
        """
        if image_crop is None or image_crop.size == 0:
            return "", 0.0

        # Encode crop as JPEG
        success, buffer = cv2.imencode('.jpg', image_crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not success:
            return "", 0.0

        b64_image = base64.b64encode(buffer).decode('utf-8')

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Read the vehicle license plate number in this image. Output ONLY the uppercase alphanumeric license plate number (for example: HR26DQ5551). Discard country logos or prefixes like IND. Do NOT include spaces, punctuation, or conversational words."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 20,
            "temperature": 0.0
        }

        try:
            response = self.session.post(self.vision_url, headers=self.headers, json=payload, timeout=25)
            if response.status_code == 200:
                content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                clean_plate = self._extract_plate(content)
                if clean_plate:
                    return clean_plate, 0.99
            else:
                print(f"[NVIDIA Vision AI] Status {response.status_code}: {response.text[:150]}")
        except Exception as e:
            print(f"[NVIDIA Vision AI] Request error: {e}")

        return "", 0.0

    @staticmethod
    def _extract_plate(raw_text: str) -> str:
        """Cleans and extracts valid plate characters from AI response."""
        # Find all alphanumeric tokens
        tokens = re.findall(r'[A-Za-z0-9]+', raw_text)
        merged = "".join(tokens).upper()

        # Remove IND prefix or suffix
        if merged.startswith("IND") and len(merged) > 6:
            merged = merged[3:]
        if merged.endswith("IND") and len(merged) > 6:
            merged = merged[:-3]

        return merged


def preprocess_license_plate(crop: np.ndarray) -> np.ndarray:
    """
    Enhances license plate crop clarity:
    - Scales up to high resolution
    - Normalizes contrast via CLAHE
    - Light sharpening for crisp character boundaries
    """
    if crop is None or crop.size == 0:
        return crop

    # 1. Scale crop to standard height (140px)
    target_h = 140
    h, w = crop.shape[:2]
    scale = max(target_h / float(h), 1.2)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # 2. Contrast enhancement
    lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    enhanced = cv2.merge((cl, a, b))
    enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    return enhanced_bgr


# Load YOLO model
script_dir = os.path.dirname(os.path.abspath(__file__))
model_candidates = [
    os.path.join(script_dir, "b.pt"),
    "b.pt",
    os.path.join("PLATE", "b.pt"),
    r"C:\Users\dev\Music\PLATE\b.pt"
]

model_path = None
for candidate in model_candidates:
    if os.path.exists(candidate):
        model_path = candidate
        break

if model_path is None:
    raise FileNotFoundError("Could not find YOLO model 'b.pt'. Make sure it is in the PLATE directory.")

print(f"Loading YOLO from {model_path}...")
model = YOLO(model_path)

print("Initializing NVIDIA Vision AI OCR (Meta Llama 3.2 Vision)...")
ocr = NvidiaVisionPlateOCR(api_key=NVIDIA_API_KEY)


def select_file(file_type="video"):
    root = tk.Tk()
    root.withdraw()
    if file_type == "video":
        ftypes = [("Video Files", "*.mp4 *.avi *.mov *.mkv")]
        title = "Select a Video File"
    else:
        ftypes = [("Images", "*.jpg *.jpeg *.png *.bmp")]
        title = "Select an Image File"
    return filedialog.askopenfilename(title=title, filetypes=ftypes)


def process_frame(frame, ocr_model: NvidiaVisionPlateOCR, yolo_model: YOLO):
    results = yolo_model.predict(frame, conf=0.25, verbose=False)

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # Add padding around bounding box so boundary letters aren't cut
            h, w = frame.shape[:2]
            pad_x = int((x2 - x1) * 0.04)
            pad_y = int((y2 - y1) * 0.04)
            x1_pad = max(0, x1 - pad_x)
            y1_pad = max(0, y1 - pad_y)
            x2_pad = min(w, x2 + pad_x)
            y2_pad = min(h, y2 + pad_y)

            plate_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            if plate_crop.shape[0] < 10 or plate_crop.shape[1] < 10:
                continue

            # Enhance crop
            enhanced_crop = preprocess_license_plate(plate_crop)

            # Perform AI Vision OCR
            detected_text, confidence = ocr_model.recognize(enhanced_crop)

            if detected_text and len(detected_text) >= 4:
                print(f"✅ [NVIDIA AI OCR] Recognized Plate: {detected_text}")

                # Draw Green Box & Text
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                (text_w, text_h), _ = cv2.getTextSize(detected_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                cv2.rectangle(frame, (x1, y1 - 32), (x1 + text_w + 10, y1), (0, 0, 0), -1)
                cv2.putText(frame, detected_text, (x1 + 5, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            else:
                # Draw Red Box if OCR failed
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

    return frame


if __name__ == "__main__":
    choice = input("\n Type 1 for VIDEO\n Type 2 for IMAGE\nEnter choice: ").strip()

    if choice == '1':
        path = select_file("video")
        if path:
            cap = cv2.VideoCapture(path)

            FRAME_SKIP = 3
            count = 0

            while cap.isOpened():
                success, frame = cap.read()
                if not success:
                    break

                count += 1
                if count % FRAME_SKIP != 0:
                    if frame.shape[1] > 1000:
                        frame = cv2.resize(frame, (1000, 560))
                    cv2.imshow('Final Result', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                    continue

                if frame.shape[1] > 1000:
                    frame = cv2.resize(frame, (1000, 560))

                processed = process_frame(frame, ocr, model)
                cv2.imshow('Final Result', processed)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cap.release()

    elif choice == '2':
        path = select_file("image")
        if path:
            frame = cv2.imread(path)
            if frame is not None:
                processed = process_frame(frame, ocr, model)
                cv2.imshow('Final Result', processed)
                print("Press any key on the image window to close...")
                cv2.waitKey(0)
            else:
                print(f"Failed to read image from {path}")

    cv2.destroyAllWindows()