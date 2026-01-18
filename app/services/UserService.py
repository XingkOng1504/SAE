
from app.models.UserDAO import UserSqliteDAO as UserDAO

class UserService():
	"""
	Classe dédiée à la logique des utilisateurs
	"""
	def __init__(self):
		self.udao = UserDAO()

	def login(self, password):
		return self.udao.verifyMDP(password)
	
	def changepwd(self,password):
		return self.udao.change_mdp(password)
	
	def getSwitchMDP(self):
		return self.udao.getSwitch_mdp()
