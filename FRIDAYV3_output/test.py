import os
from dotenv import load_dotenv, dotenv_values

path = r"D:\Downloads\FRIDAYV4\FRIDAYV3_output\.env"
print("File exists:", os.path.exists(path))
print("Contents:", dotenv_values(path))