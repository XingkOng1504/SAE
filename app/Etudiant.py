class EtudiantView:
    """
    Objet de transfert de données (DTO) pour l'affichage
    dans la vue index.html
    """
    def __init__(self, ine, annee_univ, annee_but, resultat, dept, rythme):
        self.ine = ine
        self.annee_univ = annee_univ
        self.annee_but = annee_but
        self.resultat = resultat
        self.dept = dept
        self.rythme = rythme