import json
from flask import current_app
import os

class RegleDAO():

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "..", "static", "data", "regles.json")
        with open(file_path,"r",encoding="utf-8") as f:
            self.regles = json.load(f)

    def save(self): #commit
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "..", "static", "data", "regles.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.regles, f, indent=4, ensure_ascii=False)

    def ajouter_regle(self, nom, description, condition):
        self.regles.append({
            "nom": nom,
            "description": description,
            "condition": condition,
            "statut": True
        })
        self.save()

    def supprimer_regle(self, index):
        if 0 <= index < len(self.regles):
            self.regles.pop(index)
            self.save()

    def modifier_statut(self, index, statut):
        if 0 <= index < len(self.regles):
            self.regles[index]["statut"] = statut
            self.save()

    def get_regles(self):
        return self.regles
    
    def finSQL(self):
        conditions = []
        for r in self.regles:
            if r["statut"]== True:
                conditions.append(r["condition"])
        if not conditions:
            return ""
        return " AND ".join(conditions)
    
        