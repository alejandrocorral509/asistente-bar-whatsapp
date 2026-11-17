# Asistente de WhatsApp para un bar: el servidor
from fastapi import FastAPI

app = FastAPI() # Crear tu aplicación web

@app.get("/") # Cuando alguien pida la dirección "/", ejecuta la función
def inicio():
    return {"mensaje": "El asistente del bar esta funcionando"} # Devuelves un diccionario y FastApi lo convierte en JSON

@app.get("/horario")
def horario():
    return {"horario": "De 12:00 a 00:00, cerrado los lunes"}