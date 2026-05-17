import cv2
import numpy as np
import os

def extract_icons(image_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    img = cv2.imread(image_path)
    if img is None:
        print("Image not found!")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Ищем контуры: используем Canny с очень низким порогом
    edges = cv2.Canny(gray, 20, 100)
    kernel = np.ones((5,5), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    boxes = []
    
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        
        # Разрешаем больший разброс размеров и пропорций
        aspect_ratio = float(w)/h
        area = w * h
        if 0.5 <= aspect_ratio <= 2.0 and 800 <= area <= 20000:
            is_overlap = False
            for bx, by, bw, bh in boxes:
                cx1, cy1 = x + w/2, y + h/2
                cx2, cy2 = bx + bw/2, by + bh/2
                if abs(cx1 - cx2) < min(w, bw) and abs(cy1 - cy2) < min(h, bh):
                    is_overlap = True
                    break
            
            if not is_overlap:
                boxes.append((x, y, w, h))

    # Сортируем: сначала верхние (по y), потом слева направо (по x)
    boxes.sort(key=lambda b: (b[1] // 50, b[0]))
    
    extracted_count = 0
    for i, (x, y, w, h) in enumerate(boxes):
        pad = 5
        y1 = max(0, y - pad)
        y2 = min(img.shape[0], y + h + pad)
        x1 = max(0, x - pad)
        x2 = min(img.shape[1], x + w + pad)
        
        icon = img[y1:y2, x1:x2]
        cv2.imwrite(os.path.join(output_dir, f"asset_candidate_{i:02d}.png"), icon)
        extracted_count += 1
        
    print(f"Extracted {extracted_count} candidates.")

extract_icons(r"c:\Users\Toxa\Desktop\XP HEROES\assets\screenshot.png", r"c:\Users\Toxa\Desktop\XP HEROES\assets")
