"""
🎮 Game Engine Module
Sistema de gamificación para motivar la rehabilitación

Características:
- Sistema de puntos
- Logros desbloqueables
- Desafíos diarios
- Rachas de práctica
- Niveles y progresión
"""

from datetime import datetime, timedelta
from typing import Dict, List
import random
from database import Database


class GameEngine:
    """Motor de gamificación"""
    
    def __init__(self):
        self.db = Database()
        
        # Definición de logros
        self.achievements = {
            "first_word": {
                "name": "Primera Palabra",
                "description": "Completaste tu primera palabra correctamente",
                "icon": "🌟",
                "points": 10
            },
            "perfect_10": {
                "name": "Perfecto 10",
                "description": "10 palabras perfectas seguidas",
                "icon": "🎯",
                "points": 50
            },
            "category_master": {
                "name": "Maestro de Categoría",
                "description": "Completaste todas las palabras de una categoría",
                "icon": "🏆",
                "points": 100
            },
            "daily_streak_3": {
                "name": "Racha de 3 días",
                "description": "Practicaste 3 días seguidos",
                "icon": "🔥",
                "points": 30
            },
            "daily_streak_7": {
                "name": "Racha de 7 días",
                "description": "Practicaste una semana completa",
                "icon": "💪",
                "points": 70
            },
            "daily_streak_30": {
                "name": "Racha de 30 días",
                "description": "¡Un mes completo de práctica!",
                "icon": "👑",
                "points": 300
            },
            "level_up": {
                "name": "Subir de Nivel",
                "description": "Avanzaste al siguiente nivel",
                "icon": "⬆️",
                "points": 25
            },
            "phrase_master": {
                "name": "Maestro de Frases",
                "description": "Completaste 10 frases correctamente",
                "icon": "💬",
                "points": 80
            },
            "speed_demon": {
                "name": "Velocista",
                "description": "Completaste 5 palabras en menos de 1 minuto",
                "icon": "⚡",
                "points": 40
            },
            "comeback_kid": {
                "name": "Nunca Rendirse",
                "description": "Mejoraste una palabra difícil después de 5 intentos",
                "icon": "🦸",
                "points": 60
            },
            "explorer": {
                "name": "Explorador",
                "description": "Probaste todas las categorías",
                "icon": "🗺️",
                "points": 50
            },
            "night_owl": {
                "name": "Búho Nocturno",
                "description": "Practicaste después de las 10pm",
                "icon": "🦉",
                "points": 15
            },
            "early_bird": {
                "name": "Madrugador",
                "description": "Practicaste antes de las 7am",
                "icon": "🐦",
                "points": 15
            },
            "century": {
                "name": "Centenario",
                "description": "100 palabras completadas",
                "icon": "💯",
                "points": 100
            },
            "thousand": {
                "name": "Mil Palabras",
                "description": "1000 intentos realizados",
                "icon": "🎉",
                "points": 200
            }
        }
        
        # Desafíos diarios predefinidos
        self.daily_challenges = [
            {
                "type": "complete_words",
                "title": "Palabras del Día",
                "description": "Completa {count} palabras hoy",
                "count": 10,
                "points": 20
            },
            {
                "type": "perfect_score",
                "title": "Perfección",
                "description": "Consigue {count} puntuaciones perfectas (>90%)",
                "count": 5,
                "points": 30
            },
            {
                "type": "category_focus",
                "title": "Enfoque",
                "description": "Practica {count} palabras de la categoría '{category}'",
                "count": 8,
                "category": None,  # Se asigna dinámicamente
                "points": 25
            },
            {
                "type": "level_challenge",
                "title": "Desafío de Nivel",
                "description": "Completa {count} palabras del nivel {level}",
                "count": 5,
                "level": None,
                "points": 35
            },
            {
                "type": "time_challenge",
                "title": "Contra Reloj",
                "description": "Completa {count} palabras en menos de 5 minutos",
                "count": 8,
                "points": 40
            }
        ]
    
    def calculate_points(self, progress_data: Dict) -> int:
        """
        Calcula puntos basados en el rendimiento
        
        Args:
            progress_data: Datos del intento
        
        Returns:
            Puntos ganados
        """
        score = progress_data.get("score", 0)
        patient_id = progress_data.get("patient_id", "default")
        
        points = 0
        reasons = []
        
        # Puntos base por intento
        points += 1
        reasons.append("intento")
        
        # Puntos por puntuación
        if score >= 90:
            points += 10
            reasons.append("puntuación perfecta")
        elif score >= 70:
            points += 5
            reasons.append("buen intento")
        elif score >= 50:
            points += 2
            reasons.append("progreso")
        
        # Bonus por racha
        streak = self._get_current_streak(patient_id)
        if streak > 0:
            bonus = min(streak * 2, 20)  # Máximo 20 puntos bonus
            points += bonus
            reasons.append(f"racha de {streak}")
        
        # Guardar puntos
        if points > 0:
            self.db.add_points(patient_id, points, ", ".join(reasons))
        
        # Verificar logros
        self._check_achievements(patient_id, progress_data)
        
        return points
    
    def _get_current_streak(self, patient_id: str) -> int:
        """Obtiene la racha actual de días consecutivos"""
        from sqlalchemy import func
        from database import Progress
        
        session = self.db.SessionLocal()
        try:
            # Obtener fechas distintas de práctica ordenadas desc
            results = session.query(
                func.date(Progress.created_at).label('day')
            ).filter(
                Progress.patient_id == patient_id
            ).distinct().order_by(
                func.date(Progress.created_at).desc()
            ).limit(30).all()
            
            if not results:
                return 0
            
            streak = 0
            today = datetime.now().date()
            
            for i, row in enumerate(results):
                # Manejar diferentes formatos de fecha
                day_value = row.day
                if isinstance(day_value, str):
                    day = datetime.strptime(day_value, "%Y-%m-%d").date()
                elif hasattr(day_value, 'date'):
                    day = day_value.date() if callable(getattr(day_value, 'date', None)) else day_value
                else:
                    day = day_value
                
                expected = today - timedelta(days=i)
                
                if day == expected:
                    streak += 1
                else:
                    break
            
            return streak
        finally:
            session.close()
    
    def _check_achievements(self, patient_id: str, progress_data: Dict):
        """Verifica y desbloquea logros"""
        from database import GAME_PREFIX, is_attempt_correct
        score = progress_data.get("score", 0)
        is_speech = not str(progress_data.get("word_id", "")).startswith(GAME_PREFIX)

        # Primera palabra (bien dicha: con el umbral del nivel, no con un 70 fijo)
        if is_speech and is_attempt_correct(score, progress_data.get("is_correct")):
            self.db.unlock_achievement(patient_id, "first_word")
        
        # Rachas
        streak = self._get_current_streak(patient_id)
        if streak >= 3:
            self.db.unlock_achievement(patient_id, "daily_streak_3")
        if streak >= 7:
            self.db.unlock_achievement(patient_id, "daily_streak_7")
        if streak >= 30:
            self.db.unlock_achievement(patient_id, "daily_streak_30")
        
        # Hora del día
        hour = datetime.now().hour
        if hour >= 22 or hour < 5:
            self.db.unlock_achievement(patient_id, "night_owl")
        if hour >= 5 and hour < 7:
            self.db.unlock_achievement(patient_id, "early_bird")
        
        # Verificar centenario
        stats = self._get_quick_stats(patient_id)
        if stats.get("correct_attempts", 0) >= 100:
            self.db.unlock_achievement(patient_id, "century")
        if stats.get("total_attempts", 0) >= 1000:
            self.db.unlock_achievement(patient_id, "thousand")
    
    def _get_quick_stats(self, patient_id: str) -> Dict:
        """Obtiene estadísticas rápidas"""
        from sqlalchemy import func, case
        from database import GAME_PREFIX, Progress, correct_sql

        session = self.db.SessionLocal()
        try:
            # Solo intentos de pronunciación (las partidas de juegos no cuentan como palabras)
            result = session.query(
                func.count(Progress.id).label('total_attempts'),
                func.sum(case((correct_sql(), 1), else_=0)).label('correct_attempts')
            ).filter(
                Progress.patient_id == patient_id,
                ~Progress.word_id.like(GAME_PREFIX + "%")
            ).first()
            
            return {
                'total_attempts': (result.total_attempts if result else 0) or 0,
                'correct_attempts': (result.correct_attempts if result else 0) or 0
            }
        finally:
            session.close()
    
    def get_daily_challenge(self) -> Dict:
        """Obtiene el desafío diario"""
        # Usar fecha como semilla para consistencia
        today = datetime.now().strftime("%Y-%m-%d")
        random.seed(today)
        
        # Seleccionar desafío aleatorio
        challenge = random.choice(self.daily_challenges).copy()
        
        # Personalizar si es necesario
        if challenge["type"] == "category_focus":
            categories = self.db.get_categories()
            if categories:
                cat = random.choice(categories)
                challenge["category"] = cat["id"]
                challenge["category_name"] = cat["name"]
                challenge["description"] = challenge["description"].format(
                    count=challenge["count"],
                    category=cat["name"]
                )
        elif challenge["type"] == "level_challenge":
            challenge["level"] = random.randint(1, 3)
            challenge["description"] = challenge["description"].format(
                count=challenge["count"],
                level=challenge["level"]
            )
        else:
            challenge["description"] = challenge["description"].format(
                count=challenge["count"]
            )
        
        challenge["id"] = f"daily_{today}"
        challenge["date"] = today
        
        return challenge
    
    def complete_challenge(self, patient_id: str, challenge_id: str, score: int) -> Dict:
        """Marca un desafío como completado"""
        challenge = self.get_daily_challenge()
        
        if challenge["id"] != challenge_id:
            return {"success": False, "message": "Desafío no válido"}
        
        # Dar puntos
        points = challenge.get("points", 10)
        self.db.add_points(patient_id, points, f"Desafío diario: {challenge['title']}")
        
        return {
            "success": True,
            "points_earned": points,
            "message": f"¡Desafío completado! +{points} puntos"
        }
    
    def get_achievements(self, patient_id: str) -> Dict:
        """Obtiene logros desbloqueados y disponibles"""
        unlocked = self.db.get_achievements(patient_id)
        unlocked_types = {a["achievement_type"] for a in unlocked}
        
        result = {
            "unlocked": [],
            "locked": [],
            "total_unlocked": len(unlocked),
            "total_available": len(self.achievements)
        }
        
        for ach_id, ach_data in self.achievements.items():
            item = {
                "id": ach_id,
                **ach_data
            }
            
            if ach_id in unlocked_types:
                # Encontrar fecha de desbloqueo
                for u in unlocked:
                    if u["achievement_type"] == ach_id:
                        item["unlocked_at"] = u["unlocked_at"]
                        break
                result["unlocked"].append(item)
            else:
                result["locked"].append(item)
        
        return result
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Obtiene tabla de clasificación"""
        from sqlalchemy import func
        from database import Patient, Points, Progress
        
        session = self.db.SessionLocal()
        try:
            # Construir query con joins
            results = session.query(
                Patient.id,
                Patient.name,
                func.coalesce(func.sum(Points.points), 0).label('total_points'),
                func.count(func.distinct(Progress.id)).label('total_attempts')
            ).outerjoin(
                Points, Patient.id == Points.patient_id
            ).outerjoin(
                Progress, Patient.id == Progress.patient_id
            ).group_by(
                Patient.id, Patient.name
            ).order_by(
                func.coalesce(func.sum(Points.points), 0).desc()
            ).limit(limit).all()
            
            return [{
                'id': r.id,
                'name': r.name,
                'total_points': int(r.total_points),
                'total_attempts': r.total_attempts
            } for r in results]
        finally:
            session.close()
    
    def get_player_level(self, patient_id: str) -> Dict:
        """Calcula el nivel del jugador basado en puntos"""
        total_points = self.db.get_total_points(patient_id)
        
        # Niveles: cada nivel requiere más puntos
        levels = [
            (0, "Principiante", "🌱"),
            (100, "Aprendiz", "🌿"),
            (300, "Practicante", "🌳"),
            (600, "Avanzado", "⭐"),
            (1000, "Experto", "🌟"),
            (1500, "Maestro", "💫"),
            (2500, "Gran Maestro", "👑"),
            (5000, "Leyenda", "🏆")
        ]
        
        current_level = levels[0]
        next_level = levels[1] if len(levels) > 1 else None
        
        for i, (points_req, name, icon) in enumerate(levels):
            if total_points >= points_req:
                current_level = (points_req, name, icon)
                next_level = levels[i + 1] if i + 1 < len(levels) else None
        
        progress_to_next = 0
        if next_level:
            current_min = current_level[0]
            next_min = next_level[0]
            progress_to_next = min(100, ((total_points - current_min) / (next_min - current_min)) * 100)
        
        return {
            "level": current_level[1],
            "icon": current_level[2],
            "total_points": total_points,
            "progress_to_next": round(progress_to_next, 1),
            "next_level": next_level[1] if next_level else None,
            "points_to_next": (next_level[0] - total_points) if next_level else 0
        }
    
    def get_mini_game(self, game_type: str = "random") -> Dict:
        """Obtiene un mini juego"""
        games = [
            {
                "type": "word_match",
                "name": "Emparejar Palabras",
                "description": "Escucha y selecciona la palabra correcta",
                "icon": "🎯",
                "difficulty": 1
            },
            {
                "type": "category_sort",
                "name": "Clasificar Palabras",
                "description": "Arrastra cada palabra a su categoría",
                "icon": "📦",
                "difficulty": 2
            },
            {
                "type": "complete_phrase",
                "name": "Completa la Frase",
                "description": "Di la palabra que falta en la frase",
                "icon": "💬",
                "difficulty": 2
            },
            {
                "type": "speed_round",
                "name": "Ronda Rápida",
                "description": "Di tantas palabras como puedas en 60 segundos",
                "icon": "⚡",
                "difficulty": 3
            },
            {
                "type": "memory_game",
                "name": "Memoria",
                "description": "Recuerda y repite la secuencia de palabras",
                "icon": "🧠",
                "difficulty": 3
            }
        ]
        
        if game_type == "random":
            return random.choice(games)
        
        for game in games:
            if game["type"] == game_type:
                return game
        
        return games[0]
