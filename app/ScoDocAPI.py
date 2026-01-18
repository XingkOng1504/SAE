import requests
from typing import Dict, List, Optional, Tuple
from flask import current_app

class ScoDocAPI:
    """Classe pour interagir avec l'API ScoDoc"""
    
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Effectue une requête GET générique"""
        url = f"{self.base_url}{endpoint}"
        try:
            # Timeout de 60s car récupérer une promo entière peut être long
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            # Gestion du cas où l'API renvoie du texte brut au lieu de JSON
            if 'application/json' in response.headers.get('Content-Type', ''):
                return response.json()
            else:
                try:
                    return response.json()
                except:
                    return None

        except Exception as e:
            current_app.logger.error(f"Erreur API {endpoint}: {e}")
            return None

    def test_connexion(self) -> Tuple[bool, str]:
        """Ping simple pour vérifier l'accès"""
        try:
            res = self._make_request("/api/v1/info/version")
            return (True, "Connexion OK") if res else (False, "Pas de réponse de l'API")
        except Exception as e:
            return False, str(e)

    # --- DONNÉES STRUCTURELLES ---

    def get_departements(self) -> List[Dict]:
        res = self._make_request("/api/v1/departements")
        return res.get('departements', []) if res else []

    def get_formations(self) -> List[Dict]:
        """Récupère toutes les formations"""
        res = self._make_request("/api/v1/formations")
        return res.get('formations', []) if res else []

    def get_referentiel_competences(self, formation_id: int) -> Optional[Dict]:
        """
        Récupère le référentiel (Parcours, Compétences, UE) d'une formation.
        Vital pour remplir les tables 'parcours' et 'competence'.
        """
        return self._make_request(f"/api/v1/formation/{formation_id}/referentiel_competences")

    # --- DONNÉES ÉTUDIANTS / RÉSULTATS ---

    def get_formsemestres_query(self, annee_scolaire: int) -> List[Dict]:
        """
        Récupère tous les semestres (FormSemestres) d'une année donnée.
        """
        return self._make_request("/api/v1/formsemestres/query", params={'annee_scolaire': annee_scolaire})

    def get_decisions_jury(self, formsemestre_id: int) -> List[Dict]:
        """
        Récupère TOUS les résultats (étudiants, décisions, moyennes) pour un semestre.
        C'est ici qu'on trouve les notes et les validations de compétences.
        """
        return self._make_request(f"/api/v1/formsemestre/{formsemestre_id}/decisions_jury")