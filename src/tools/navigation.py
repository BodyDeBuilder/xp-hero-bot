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
                x, y, w, h = int(self.region["x"]), int(self.region["y"]), int(self.region["w"]), int(self.region["h"])
                y2, x2 = min(full_img.shape[0], y+h), min(full_img.shape[1], x+w)
                img = full_img[y:y2, x:x2]
            else:
                img = full_img

        except Exception as e:
            raise Exception(f"Ошибка при подготовке карты: {e}")

        # Дальнейшая логика остается прежней (инверсия и раздутие)
        _, binary = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV)

        if self.wall_offset > 0:
            # Раздуваем препятствия (стены) на заданное кол-во пикселей
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.wall_offset * 2 + 1, self.wall_offset * 2 + 1))
            binary = cv2.dilate(binary, kernel)

        # Возвращаем обратно: дороги - True (1), стены - False (0)
        self.grid = (binary == 0)
        self.height, self.width = self.grid.shape

    def find_nearest_walkable(self, node):
        """Ищет ближайшую свободную точку в радиусе 20 пикселей."""
        r, c = node
        best_node = None
        min_dist = float('inf')
        
        search_radius = 20
        for dr in range(-search_radius, search_radius + 1):
            for dc in range(-search_radius, search_radius + 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.height and 0 <= nc < self.width:
                    if self.grid[nr, nc]:
                        dist = dr*dr + dc*dc
                        if dist < min_dist:
                            min_dist = dist
                            best_node = (nr, nc)
        return best_node

    def get_path(self, start, end):
        """
        Ищет путь от start (x,y) до end (x,y).
        Координаты логические (пиксели на карте).
        Возвращает список точек [(x1,y1), (x2,y2)...] или None
        """
        start_node = (int(start[1]), int(start[0])) # (row, col)
        end_node = (int(end[1]), int(end[0]))

        print(f"DEBUG PathFinder: Ищем путь от {start_node} до {end_node}")

        # Проверка границ
        if not (0 <= start_node[0] < self.height and 0 <= start_node[1] < self.width):
            print(f"DEBUG PathFinder: Старт {start_node} вне границ карты ({self.height}x{self.width})")
            return None
        if not (0 <= end_node[0] < self.height and 0 <= end_node[1] < self.width):
            print(f"DEBUG PathFinder: Цель {end_node} вне границ карты")
            return None
        
        # Если старт или цель в стене (из-за wall_offset), ищем ближайшую точку
        if not self.grid[start_node]:
            print(f"DEBUG PathFinder: Старт {start_node} находится в стене (раздутой). Ищем замену...")
            new_start = self.find_nearest_walkable(start_node)
            if new_start:
                print(f"DEBUG PathFinder: Старт заменен на {new_start}")
                start_node = new_start
            else:
                print("DEBUG PathFinder: Не удалось найти свободную точку рядом со стартом.")
                return None

        if not self.grid[end_node]:
            print(f"DEBUG PathFinder: Цель {end_node} находится в стене. Ищем замену...")
            new_end = self.find_nearest_walkable(end_node)
            if new_end:
                print(f"DEBUG PathFinder: Цель заменена на {new_end}")
                end_node = new_end
            else:
                print("DEBUG PathFinder: Не удалось найти свободную точку рядом с целью.")
                return None

        # Алгоритм A*
        queue = [(0, start_node)]
        came_from = {}
        cost_so_far = {start_node: 0}
        
        # 8 направлений движения
        neighbors = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]

        while queue:
            current_priority, current = heapq.heappop(queue)

            if current == end_node:
                break

            for dx, dy in neighbors:
                next_node = (current[0] + dx, current[1] + dy)
                
                # Проверка проходимости
                if 0 <= next_node[0] < self.height and 0 <= next_node[1] < self.width:
                    if not self.grid[next_node]:
                        continue
                    
                    # Стоимость шага (диагональ чуть дороже)
                    new_cost = cost_so_far[current] + (1.41 if dx != 0 and dy != 0 else 1)
                    
                    if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                        cost_so_far[next_node] = new_cost
                        # Эвристика: Манхэттенское расстояние или Евклидово
                        priority = new_cost + self.heuristic(next_node, end_node)
                        heapq.heappush(queue, (priority, next_node))
                        came_from[next_node] = current

        if end_node not in came_from:
            return None

        # Восстановление пути
        path = []
        curr = end_node
        while curr != start_node:
            path.append((curr[1], curr[0])) # Обратно в (x, y)
            curr = came_from[curr]
        path.reverse()
        
        # Сглаживание пути (упрощенно: берем каждую 3-5 точку, чтобы не дергать мышь на каждый пиксель)
        smoothed_path = path[::5]
        if not smoothed_path or smoothed_path[-1] != path[-1]:
            smoothed_path.append(path[-1])
            
        return smoothed_path

    def heuristic(self, a, b):
        return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
