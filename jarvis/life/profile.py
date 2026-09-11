import json
from pathlib import Path
from datetime import date, timedelta


class PersonalProfile:
    def __init__(self, directory):
        self.path = Path(directory) / "profile.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
    def get(self, key): return self.data.get(key)
    def set(self, key, value):
        self.data[key] = value; self.path.write_text(json.dumps(self.data, indent=2))


class GoalManager:
    def __init__(self, profile): self.path = profile.path.parent / "goals.json"; self.goals = json.loads(self.path.read_text()) if self.path.exists() else []
    def add(self, title, priority="normal", related_blocks=None):
        g = {"goal_id": f"goal_{len(self.goals)+1}", "title": title, "priority": priority, "related_blocks": related_blocks or [], "progress": 0}
        self.goals.append(g); self.path.write_text(json.dumps(self.goals, indent=2)); return g
    def update_progress(self, goal_id, progress):
        for g in self.goals:
            if g["goal_id"] == goal_id: g["progress"] = progress
        self.path.write_text(json.dumps(self.goals, indent=2))
    def all(self): return self.goals


class SpecialEventManager:
    def __init__(self, profile): self.path = profile.path.parent / "events.json"; self.events = json.loads(self.path.read_text()) if self.path.exists() else []
    def add(self, day, title, importance="normal"):
        e = {"date": day, "title": title, "importance": importance}; self.events.append(e); self.path.write_text(json.dumps(self.events, indent=2)); return e
    def upcoming(self, days=30, ref=None):
        ref = ref or date.today(); end = ref + timedelta(days=days)
        return [e for e in self.events if ref <= date.fromisoformat(e["date"]) <= end]
