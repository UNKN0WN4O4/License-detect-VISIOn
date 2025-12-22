import cv2
import tkinter as tk
from tkinter import filedialog
from ultralytics import YOLO
from paddleocr import PaddleOCR
import os
import logging

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"
logging.getLogger("ppocr").setLevel(logging.ERROR) 

print("Loading YOLO...")
model = YOLO(r"C:\Users\dev\Music\PLATE\b.pt") 

print("Loading PaddleOCR...")
ocr = PaddleOCR(use_textline_orientation=True, lang='en')

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

def process_frame(frame, ocr_model, yolo_model):
    
    results = yolo_model.predict(frame, conf=0.25, verbose=False)
    
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
           
            plate_crop = frame[y1:y2, x1:x2]
            if plate_crop.shape[0] < 10 or plate_crop.shape[1] < 10:
                continue
            
            
            plate_crop = cv2.resize(plate_crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

            
            ocr_result = ocr_model.ocr(plate_crop)

           
            detected_text = ""
            confidence = 0.0

            if ocr_result and ocr_result[0]:
                res = ocr_result[0]
                
                # Case: PaddleX Format (The one you have)
                # It returns a dict with 'rec_texts': ['HP01...', 'IND']
                if isinstance(res, dict):
                    if 'rec_texts' in res:
                        # Join all found texts (e.g. "HP01 H 5011" + "IND")
                        text_list = res['rec_texts']
                        detected_text = " ".join(text_list)
                        
                        
                        if 'rec_scores' in res and len(res['rec_scores']) > 0:
                            confidence = sum(res['rec_scores']) / len(res['rec_scores'])
                        else:
                            confidence = 0.99 # Assume high if missing
                            
                    elif 'rec_text' in res: # Fallback for other versions
                        detected_text = res['rec_text']
                        confidence = res.get('rec_score', 0.0)

                
                elif isinstance(res, list):
                    
                    texts = []
                    scores = []
                    for line in res:
                        if isinstance(line, list) and len(line) >= 2:
                            texts.append(line[1][0])
                            scores.append(line[1][1])
                    if texts:
                        detected_text = " ".join(texts)
                        confidence = sum(scores) / len(scores)

            
            if detected_text:
                
                clean_text = detected_text.replace('IND', '') # Remove IND logo text
                clean_text = clean_text.replace(' ', '').upper()
                
                # Loose Filter: As long as we have > 4 chars, show it
                if len(clean_text) > 4:
                    print(f"✅ Found: {clean_text} (Conf: {confidence:.2f})")
                    
                    # Draw Green Box & Text
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    (w, h), _ = cv2.getTextSize(clean_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                    cv2.rectangle(frame, (x1, y1 - 30), (x1 + w, y1), (0, 0, 0), -1)
                    cv2.putText(frame, clean_text, (x1, y1 - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                else:
                    # Draw Red Box if text is too short (garbage)
                     cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            else:
                 # Draw Red Box if OCR failed
                 cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

    return frame


choice = input("\n Type 1 for VIDEO\n Type 2 for IMAGE\nEnter choice: ")

if choice == '1':
    path = select_file("video")
    if path:
        cap = cv2.VideoCapture(path)
        
        FRAME_SKIP = 3 
        count = 0
        
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break
            
            count += 1
            if count % FRAME_SKIP != 0:
                 if frame.shape[1] > 1000:
                    frame = cv2.resize(frame, (1000, 560))
                 cv2.imshow('Final Result', frame)
                 if cv2.waitKey(1) & 0xFF == ord('q'): break
                 continue

            if frame.shape[1] > 1000:
                frame = cv2.resize(frame, (1000, 560))
                
            processed = process_frame(frame, ocr, model)
            cv2.imshow('Final Result', processed)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
        cap.release()

elif choice == '2':
    path = select_file("image")
    if path:
        frame = cv2.imread(path)
        processed = process_frame(frame, ocr, model)
        cv2.imshow('Final Result', processed)
        print("Press any key on the image window to close...")
        cv2.waitKey(0)

cv2.destroyAllWindows()