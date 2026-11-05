"""Password-gated private demo; deploy behind HTTPS with one application worker."""
import base64
import binascii
import os
import secrets
from starlette.responses import JSONResponse


def live_enabled():
    return os.getenv('DEMO_ALLOW_LIVE', '0' if os.getenv('PUBLIC_DEMO')=='1' else '1')=='1'


async def demo_guard(request, call_next):
    public=os.getenv('PUBLIC_DEMO')=='1'
    password=os.getenv('APP_DEMO_PASSWORD','')
    if public and not password:
        return JSONResponse({'detail':'Закрытая демонстрация не настроена.'},status_code=503)
    if password:
        supplied=request.headers.get('authorization','')
        valid=False
        if supplied.startswith('Basic '):
            try:
                username,secret=base64.b64decode(supplied[6:],validate=True).decode().split(':',1)
                valid=secrets.compare_digest(username.encode(),b'demo') and secrets.compare_digest(secret.encode(),password.encode())
            except (binascii.Error,ValueError,UnicodeError):
                pass
        if not valid:
            return JSONResponse({'detail':'Войдите в демонстрацию.'},status_code=401,
                                headers={'WWW-Authenticate':'Basic realm="AIMedicine", charset="UTF-8"'})
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        local_dev = not public and origin in {'http://127.0.0.1:5173','http://localhost:5173'}
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/') and not local_dev:
            return JSONResponse({'detail':'Недопустимый источник запроса.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    return response
