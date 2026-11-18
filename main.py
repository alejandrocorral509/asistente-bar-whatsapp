# Asistente de WhatsApp para un bar: el servidor
import json
import anthropic # Importamos librería de anthropic
import os 
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv # Importamos función para leer el .env

load_dotenv() # lee el archivo .env y carga la clave 

cliente = anthropic.Anthropic() # Creamos el cliente

MODELO = "claude-haiku-5-5" # Constante con el modelo elegido de Anthropic
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


# Cargo los datos del bar una sola vez, al arrancar
with open("datos/bar.json", encoding="utf-8") as archivo:
    BAR = json.load(archivo) # Constante del bar

INSTRUCCIONES = f"""Eres el asistente de WhatsApp de {BAR['nombre']}.
Tienes que hablar de una manera cercana y corta con el cliente.
Solo responde con datos del bar. Si algo no está, di que no lo sabes.
Cumple siempre con las normas de los datos.

Datos del bar:
{json.dumps(BAR, ensure_ascii=False, indent=2)}"""

app = FastAPI() # Crear tu aplicación web

class Pregunta(BaseModel):
    mensaje: str

@app.get("/") # Cuando alguien pida la dirección "/", ejecuta la función
def inicio():
    return {"mensaje": f"El asistente de {BAR['nombre']} esta funcionando"} # Devuelves un diccionario y FastApi lo convierte en JSON

@app.get("/horario")
def horario():
    return BAR["horario"]

@app.get("/carta")
def carta():
    return BAR["carta"]

@app.post("/preguntar")
def preguntar(pregunta: Pregunta):
    respuesta = cliente.messages.create(
        model= MODELO,
        max_tokens=16000,
        system=INSTRUCCIONES,
        messages=[{"role": "user", "content": pregunta.mensaje}],
    )

    texto = ""
    for bloque in respuesta.content:
        if bloque.type == "text":
            texto += bloque.text
    return {"respuesta": texto}

@app.get("/webhook")
def verificar_webhook(request: Request):
    modo = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    reto = request.query_params.get("hub.challenge")

    if modo == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(reto)

    raise HTTPException(status_code=403)