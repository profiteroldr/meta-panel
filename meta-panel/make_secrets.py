from getpass import getpass
import secrets
from werkzeug.security import generate_password_hash
password=getpass('Giriş şifresi (en az 12 karakter): ')
if len(password)<12: raise SystemExit('En az 12 karakter kullanın.')
print('ADMIN_PASSWORD_HASH='+generate_password_hash(password))
print('SECRET_KEY='+secrets.token_hex(32))
