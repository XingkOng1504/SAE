import os
import json
import glob
import re
from app.DonneeDAO import DonneeDAO
from app.Etudiant import EtudiantView
from flask import current_app

class DonneeService:
    def __init__(self):
        self.dao = DonneeDAO()

    def is_database_ready(self):
        """Demande au DAO si les données sont cohérentes"""
        return self.dao.check_data_integrity()

    def get_form_dept(self):
        """Retourne les options de département pour le formulaire"""
        return self.dao.get_all_departements()

    def get_form_annees(self):
        """Retourne les options d'années pour le formulaire"""
        return self.dao.get_all_annees()    

    def get_search_results(self, year, dept, rythme):
        """Retourne les objets EtudiantView après recherche"""
        if not year:
            return []
        
        try:
            annee_int = int(year)
            rows = self.dao.search_etudiants(annee_int, dept, rythme)
            # Transformation des lignes SQL en objets métier
            return [
                EtudiantView(
                    ine=row['ine'], 
                    annee_univ=row['annee_universitaire'], 
                    annee_but=row['annee_but'], 
                    resultat=row['resultat'], 
                    dept=row['dept'], 
                    rythme=row['rythme']
                ) for row in rows
            ]
        except ValueError:
            return []

    def get_sankey_stats(self, year, dept, rythme):
        """Retourne les statistiques pour le diagramme de Sankey"""
        if not year:
            return None
        
        try:
            return self.dao.get_sankey_data(year, dept, rythme)
        except Exception as e:
            print(f"Erreur calcul Sankey : {e}")
            return None
            