import numpy as np
import heapq
import cv2
import os
import json

class PathFinder:
    def __init__(self, walkability_map_path, wall_offset=5):
        self.map_path = walkability_map_path
        self.wall_offset = wall_offset
        self.grid = None
        
        # Для Global Canvas нам нужны координаты региона
        self.map_dir = os.path.dirname(walkability_map_path)
        self.region_info_path = os.path.join(self.map_dir, "region.json")
        self.region = None
        
        self.load_and_prepare_map()

    def load_and_prepare_map(self):
        try:
            # 1. Загружаем регион (координаты выреза)
            if os.path.exists(self.region_info_path):
                with open(self.region_info_path, "r") as f:
                    self.region = json.load(f)
            
            # 2. Загружаем ГЛОБАЛЬНУЮ карту
            with open(self.map_path, "rb") as f:
                chunk = np.frombuffer(f.read(), dtype=np.uint8)
                full_img = cv2.imdecode(chunk, cv2.IMREAD_GRAYSCALE)
            
            if full_img is None:
                raise Exception("Не удалось декодировать карту")

            # 3. Вырезаем рабочий кусок (если есть инфо о регионе)
            if self.region:
                scale = self.region.get("scale")
                if scale is None:
                    # Динамический фолбек на текущий масштаб экрана для старых карт
                    from PyQt6.QtWidgets import QApplication
                    screen = QApplication.primaryScreen()
                    scale = screen.devicePixelRatio() if screen else 1.0
                    
                px = int(self.region["x"] * scale)
                py = int(self.region["y"] * scale)
                pw = int(self.region["w"] * scale)
                ph = int(self.region["h"] * scale)
                
                y2, x2 = min(full_img.shape[0], py+ph), min(full_img.shape[1], px+pw)
                img = full_img[py:y2, px:x2]
            else:
                img = full_img

        except Exception as e:
            raise Exception(f"Ошибка при подготовке карты: {e}")

        # Инвертируем, чтобы стены были 255, а дороги 0
        _, binary = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV)

        if self.wall_offset > 0:
            # Раздуваем препятствия (стены)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.wall_offset * 2 + 1, self.wall_offset * 2 + 1))
            binary = cv2.dilate(binary, kernel)

        # Переводим в Grid: True - проходимо (дорога), False - стена
        self.grid = (binary == 0)
        self.height, self.width = self.grid.shape

    def find_nearest_walkable(self, node):
        r, c = node
        best_node = None
        min_dist = float('inf')
        
        search_radius = 100
        min_r = max(0, r - search_radius)
        max_r = min(self.height, r + search_radius + 1)
        min_c = max(0, c - search_radius)
        max_c = min(self.width, c + search_radius + 1)
        
        for nr in range(min_r, max_r):
            for nc in range(min_c, max_c):
                if self.grid[nr, nc]:
                    dist = (nr - r)**2 + (nc - c)**2
                    if dist < min_dist:
                        min_dist = dist
                        best_node = (nr, nc)
                        
        if best_node:
            import math
            print(f"DEBUG NAV: Point {node} was adjusted to nearest walkable {best_node} (dist: {math.sqrt(min_dist):.1f} physical px)")
        else:
            print(f"DEBUG NAV: Point {node} could not be adjusted (no walkable cell found within {search_radius} physical px)")
        return best_node

    def get_path(self, start_logical, end_logical):
        """
        Ищет путь. 
        Координаты логические (пиксели региона).
        Возвращает список логических точек [(x,y)...]
        """
        if self.grid is None:
            print("DEBUG NAV: Cannot plan path because grid is None!")
            return None
        
        scale = 1.0
        if self.region:
            scale = self.region.get("scale")
            if scale is None:
                # Динамический фолбек на текущий масштаб экрана для старых карт
                from PyQt6.QtWidgets import QApplication
                screen = QApplication.primaryScreen()
                scale = screen.devicePixelRatio() if screen else 1.0
        
        # 1. Переводим ЛОГИЧЕСКИЕ в ФИЗИЧЕСКИЕ (сетка)
        start_phys = (int(start_logical[1] * scale), int(start_logical[0] * scale)) # (row, col)
        end_phys = (int(end_logical[1] * scale), int(end_logical[0] * scale))

        print(f"DEBUG NAV: --- Planning Path ---")
        print(f"DEBUG NAV: Scale factor: {scale}")
        print(f"DEBUG NAV: Start logical: {start_logical} -> physical: {start_phys} (walkable: {self.grid[start_phys] if (0 <= start_phys[0] < self.height and 0 <= start_phys[1] < self.width) else 'out of bounds'})")
        print(f"DEBUG NAV: End logical: {end_logical} -> physical: {end_phys} (walkable: {self.grid[end_phys] if (0 <= end_phys[0] < self.height and 0 <= end_phys[1] < self.width) else 'out of bounds'})")

        # 2. Проверка границ
        if not (0 <= start_phys[0] < self.height and 0 <= start_phys[1] < self.width):
            print(f"DEBUG NAV: Start physical {start_phys} is out of map bounds (height: {self.height}, width: {self.width})!")
            return None
        if not (0 <= end_phys[0] < self.height and 0 <= end_phys[1] < self.width):
            print(f"DEBUG NAV: End physical {end_phys} is out of map bounds (height: {self.height}, width: {self.width})!")
            return None
        
        # 3. Если старт в стене (раздутой), ищем замену
        if not self.grid[start_phys]:
            start_phys = self.find_nearest_walkable(start_phys)
            if not start_phys:
                print(f"DEBUG NAV: Start physical {start_phys} is in a wall and no walkable neighbor found!")
                return None

        # 3.5 Если финиш в стене (раздутой), ищем замену
        if not self.grid[end_phys]:
            end_phys = self.find_nearest_walkable(end_phys)
            if not end_phys:
                print(f"DEBUG NAV: End physical {end_phys} is in a wall and no walkable neighbor found!")
                return None

        # 4. A* на физической сетке
        queue = [(0, start_phys)]
        came_from = {start_phys: None}
        cost_so_far = {start_phys: 0}
        
        iterations = 0
        while queue:
            iterations += 1
            _, current = heapq.heappop(queue)
            if current == end_phys: break
                
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                neighbor = (current[0] + dy, current[1] + dx)
                if 0 <= neighbor[0] < self.height and 0 <= neighbor[1] < self.width:
                    if self.grid[neighbor]:
                        new_cost = cost_so_far[current] + (1.41 if dx!=0 and dy!=0 else 1)
                        if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                            cost_so_far[neighbor] = new_cost
                            priority = new_cost + self.heuristic(neighbor, end_phys)
                            heapq.heappush(queue, (priority, neighbor))
                            came_from[neighbor] = current
                            
        print(f"DEBUG NAV: A* finished in {iterations} iterations.")
        if end_phys not in came_from:
            print("DEBUG NAV: A* failed to find a path between adjusted physical coordinates!")
            return None
            
        # 5. Восстановление пути (физического)
        path_phys = []
        curr = end_phys
        while curr is not None:
            path_phys.append(curr)
            curr = came_from[curr]
        path_phys.reverse()
        
        # 6. Сглаживание и перевод в ЛОГИЧЕСКИЕ для бота
        smoothed = self.smooth_path(path_phys)
        res_path = [(p[1] / scale, p[0] / scale) for p in smoothed]
        print(f"DEBUG NAV: Path successfully calculated! Raw: {len(path_phys)} points, Smoothed: {len(res_path)} points.")
        print(f"DEBUG NAV: Final logical path: {res_path}")
        return res_path

    def heuristic(self, a, b):
        return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

    def smooth_path(self, path):
        if len(path) <= 2: return path
        smoothed = [path[0]]
        for i in range(1, len(path) - 1):
            p1, p2, p3 = smoothed[-1], path[i], path[i+1]
            if not self.is_line_clear(p1, p3):
                smoothed.append(p2)
        smoothed.append(path[-1])
        return smoothed

    def is_line_clear(self, p1, p2):
        # row, col
        r1, c1 = p1
        r2, c2 = p2
        dist = int(np.hypot(r2 - r1, c2 - c1))
        # Количество точек проверки должно соответствовать расстоянию, чтобы не пропустить узкие стены
        points = max(10, dist)
        for i in range(points + 1):
            r = int(r1 + (r2 - r1) * i / points)
            c = int(c1 + (c2 - c1) * i / points)
            if not (0 <= r < self.height and 0 <= c < self.width) or not self.grid[r, c]:
                return False
        return True
