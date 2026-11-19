# Asistente de WhatsApp para un bar: el servidor
import json
import anthropic # Importamos librería de anthropic
import os
import requests # Para mandar las respuestas a WhatsApp
import gspread # Para escribir en Google Sheets
from datetime import date, datetime # Para saber la fecha de hoy y la hora de cada reserva
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv # Importamos función para leer el .env

load_dotenv() # lee el archivo .env y carga la clave 

cliente = anthropic.Anthropic() # Creamos el cliente

MODELO = "claude-haiku-5-5" # Constante con el modelo elegido de Anthropic
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
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

# Conversación de cada cliente: número de teléfono -> lista de mensajes
CONVERSACIONES = {}

# Herramientas que Claude puede pedir usar (como el tiempo de Elfito)
HERRAMIENTAS = [
    {
        "name": "guardar_reserva",
        "description": "Guarda una reserva en el libro del bar. Úsala solo cuando el cliente ya te haya dado nombre, día, hora y número de personas, y la reserva cumpla el horario y las normas del bar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la persona que reserva"},
                "dia": {"type": "string", "description": "Fecha de la reserva en formato AAAA-MM-DD"},
                "hora": {"type": "string", "description": "Hora de la reserva en formato HH:MM"},
                "personas": {"type": "integer", "description": "Número de personas"},
            },
            "required": ["nombre", "dia", "hora", "personas"],
        },
    }
]

# Me conecto a la hoja de Google una sola vez, al arrancar, con la llave de la cuenta de servicio
cuenta_google = gspread.service_account(filename=os.getenv("GOOGLE_CREDENCIALES"))
HOJA_RESERVAS = cuenta_google.open_by_key(os.getenv("GOOGLE_SHEET_ID")).sheet1

# Guarda la reserva como una fila nueva en Google Sheets y le devuelve a Claude cómo ha ido
def guardar_reserva(numero: str, datos: dict) -> str:
    if datos["personas"] > 8:
        return "No guardada: son más de 8 personas, tienen que llamar al bar."

    # El orden tiene que ser el de las columnas: Nombre, Día, Hora, Personas, Teléfono, Guardada el
    fila = [
        datos["nombre"],
        datos["dia"],
        datos["hora"],
        datos["personas"],
        numero,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ]

    try:
        HOJA_RESERVAS.append_row(fila)
    except Exception as error: # Si Google falla, que Claude no diga que está reservado
        print("Error al guardar en Google Sheets:", error)
        return "No guardada: ha habido un problema técnico. Pide al cliente que llame al bar."

    print("Reserva guardada:", datos["nombre"], datos["dia"], datos["hora"], datos["personas"], "personas")
    return "Reserva guardada correctamente."

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

# Le paso el mensaje del cliente a Claude (con toda su conversación) y me devuelve la respuesta
def preguntar_a_claude(numero: str, mensaje: str) -> str:
    # Si es la primera vez que escribe este número, le creo su conversación vacía
    if numero not in CONVERSACIONES:
        CONVERSACIONES[numero] = []

    historial = CONVERSACIONES[numero]
    historial.append({"role": "user", "content": mensaje})

    # Claude no sabe qué día es: se lo digo yo, para que entienda "mañana" o "el sábado"
    hoy = date.today()
    fecha_de_hoy = f"\n\nHoy es {DIAS_SEMANA[hoy.weekday()]} {hoy.isoformat()}."

    # Bucle de herramientas: mientras Claude pida usar una, la uso y le devuelvo el resultado
    while True:
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=16000,
            system=INSTRUCCIONES + fecha_de_hoy,
            tools=HERRAMIENTAS,
            messages=historial, # Toda la conversación, no solo el último mensaje
        )

        # Guardo la respuesta de Claude tal cual (puede llevar texto y peticiones de herramienta)
        historial.append({"role": "assistant", "content": [bloque.model_dump() for bloque in respuesta.content]})

        if respuesta.stop_reason != "tool_use":
            break # Claude ya ha terminado: no pide ninguna herramienta

        resultados = []
        for bloque in respuesta.content:
            if bloque.type == "tool_use" and bloque.name == "guardar_reserva":
                resultado = guardar_reserva(numero, bloque.input)
                resultados.append({"type": "tool_result", "tool_use_id": bloque.id, "content": resultado})
        historial.append({"role": "user", "content": resultados})

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
    return {"respuesta": preguntar_a_claude("prueba", pregunta.mensaje)} # Sin WhatsApp no hay número: uso "prueba"

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

    respuesta = preguntar_a_claude(numero, texto)
    enviar_whatsapp(numero, respuesta)
    return {"ok": True}