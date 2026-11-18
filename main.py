# Asistente de WhatsApp para un bar: el servidor
import json
import anthropic # Importamos librería de anthropic
import os
import requests # Para mandar las respuestas a WhatsApp
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
Escribes en WhatsApp: para la negrita usa un solo asterisco (*así*), nunca dos.

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

# Le paso el mensaje del cliente a Claude y me devuelve la respuesta
def preguntar_a_claude(mensaje: str) -> str:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=16000,
        system=INSTRUCCIONES,
        messages=[{"role": "user", "content": mensaje}],
    )

    texto = ""
    for bloque in respuesta.content:
        if bloque.type == "text":
            texto += bloque.text
    return texto

# Mando un mensaje de WhatsApp a un número, a través de la API de Meta
def enviar_whatsapp(numero: str, texto: str):
    url = f"https://graph.facebook.com/v25.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    cabeceras = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    cuerpo = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto},
    }
    respuesta = requests.post(url, headers=cabeceras, json=cuerpo, timeout=20)
    print("WhatsApp ha contestado:", respuesta.status_code, respuesta.text)

@app.post("/preguntar")
def preguntar(pregunta: Pregunta):
    return {"respuesta": preguntar_a_claude(pregunta.mensaje)}

@app.get("/webhook")
def verificar_webhook(request: Request):
    modo = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    reto = request.query_params.get("hub.challenge")

    if modo == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(reto)

    raise HTTPException(status_code=403)


@app.post("/webhook")
async def recibir_mensaje(request: Request):
    datos = await request.json()
    valor = datos["entry"][0]["changes"][0]["value"]

    # Meta también avisa de otras cosas (mensaje entregado, leído...): solo nos interesan los mensajes nuevos
    if "messages" not in valor:
        return {"ok": True}

    mensaje = valor["messages"][0]
    numero = mensaje["from"]

    # De momento solo entendemos texto (no audios, fotos ni ubicaciones)
    if mensaje["type"] != "text":
        enviar_whatsapp(numero, "De momento solo entiendo mensajes de texto 🙂")
        return {"ok": True}

    texto = mensaje["text"]["body"]
    print(f"Mensaje recibido: {texto}")

    respuesta = preguntar_a_claude(texto)
    enviar_whatsapp(numero, respuesta)
    return {"ok": True}