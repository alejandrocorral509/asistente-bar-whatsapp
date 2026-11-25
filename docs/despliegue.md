# Despliegue del asistente del bar (FastAPI + WhatsApp Cloud API)

> Investigado el 25 de noviembre de 2026 en las páginas oficiales de cada proveedor y de Meta.
> Los precios y límites cambian a menudo: vuelve a mirar los enlaces antes de decidir.
> Cuando algo no se ha podido confirmar en una fuente oficial, se indica.

## Resumen

- **Hosting recomendado: Render (plan Free).** No pide tarjeta para el plan gratuito, te da HTTPS válido en `*.onrender.com` (Meta lo exige) y tiene **Secret Files**, que deja la llave JSON de Google en una ruta. Así `GOOGLE_CREDENCIALES` sigue funcionando sin tocar `main.py`. Su pega es que se duerme a los 15 minutos sin tráfico y tarda alrededor de un minuto en despertar. Para una demo de portfolio vale. Para un bar de verdad, conviene pasar a una instancia de pago o a Cloud Run.
- **Lo más probable es que te bloqueara esto:** el número de prueba **solo puede escribir a una lista de hasta 5 números verificados**. Cualquier otro número devuelve el error `131030` ("recipient not in allowed list"). Por eso no podían usarlo clientes reales ni amigos que no hubieras añadido antes. La otra causa típica es el **token temporal, que caduca en menos de 24 horas**.

---

## 1. Hosting: comparativa

Requisitos de esta app:
- Una sola app FastAPI (`uvicorn main:app`) que lee variables de entorno (`ANTHROPIC_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `GOOGLE_SHEET_ID`, `GOOGLE_CREDENCIALES`).
- `GOOGLE_CREDENCIALES` es la **ruta a un archivo** JSON (`gspread.service_account(filename=...)`), así que el hosting tiene que poder colocar ese archivo en disco de forma segura.
- Meta llama al webhook por HTTPS con un certificado válido: "Self-signed certificates are not supported" ([Meta, Create a webhook endpoint](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint)).
- Arranques en frío: si Meta no recibe un 200, "retries delivery with decreasing frequency until the request succeeds, for up to 7 days" ([Meta, Webhooks overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview)). Un servicio dormido **no pierde el mensaje**: la respuesta llega con retraso y puede repetirse (la notificación puede llegar duplicada). Aun así, a un cliente que espera respuesta, un minuto se le hace largo.

| | **Render Free** | **Railway Free** | **Fly.io Free** | **Google Cloud Run** |
|---|---|---|---|---|
| Capa gratuita | 750 h de instancia al mes por workspace | 1 $ de uso al mes (más una prueba única de 5 $ durante 30 días) | 5 $ de uso al mes con tarjeta; sin tarjeta, 1 $ que caduca a los 7 días | Capa gratuita mensual por cuenta de facturación (cifras abajo) |
| ¿Tarjeta? | No para el plan Free | No | Las páginas oficiales se contradicen (ver abajo) | **Sí**, hace falta cuenta de facturación |
| Se duerme | A los 15 min sin tráfico entrante | A los 5–10 min sin tráfico **saliente** | Si activas el autoapagado, sí | Escala a cero si no hay peticiones |
| Despertar | "About one minute" | "A small amount of time"; la primera petición puede dar 502 | No confirmado | Unos segundos (no confirmado en la página oficial) |
| JSON de Google | **Secret Files** → `/etc/secrets/<archivo>` | Solo variables (hay que tocar el código) | `fly secrets` (hay que tocar el código) | Secret Manager montado como archivo |
| Dificultad | Baja | Baja | Media (CLI, Dockerfile o `fly launch`) | Media-alta (proyecto GCP, IAM) |

### Render (recomendado)
- **Free tier** ([render.com/docs/free](https://render.com/docs/free)): "750 Free instance hours" por workspace y mes, y un servicio dormido no gasta horas. Se duerme a los 15 minutos sin tráfico entrante y despertar "takes about one minute". Render "might restart a Free web service at any time". El disco es efímero, cosa que aquí da igual porque los datos van a Google Sheets. Tiene un límite de ancho de banda: si se agota y no hay método de pago, el servicio se suspende hasta fin de mes.
- **Mantenerlo despierto con un ping** cuenta como tráfico y gasta horas. Con un solo servicio, 750 h dan para el mes entero (31 días × 24 h = 744 h), pero con dos servicios ya no.
- **Variables y secretos** ([Render, Environment Variables and Secrets](https://render.com/docs/configure-environment-variables)): las variables se ponen en *Environment* del servicio. El JSON se sube como **Secret File**, y en ejecución queda en `/etc/secrets/<filename>` (máximo 1 MB entre todos los archivos). La página `render.com/docs/secret-files` devolvía 404 el día de la consulta, así que el dato viene de la página de variables.
- **Pasos**:
  1. Sube el repo a GitHub sin `.env` ni JSON (comprueba el `.gitignore`).
  2. En Render: *New → Web Service* → conecta el repo → *Language: Python*.
  3. Build command: `pip install -r requirements.txt`.
  4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
  5. *Instance type: Free*.
  6. *Environment*: añade las 5 variables y sube la llave como Secret File (por ejemplo `google.json`). Luego pon `GOOGLE_CREDENCIALES=/etc/secrets/google.json`.
  7. Despliega y abre `https://<tu-servicio>.onrender.com/` para comprobar que responde.
  8. En Meta (*WhatsApp → Configuration*), callback URL `https://<tu-servicio>.onrender.com/webhook` y verify token igual a `WHATSAPP_VERIFY_TOKEN`. Suscríbete al campo `messages`.

### Railway
- **Free tier** ([docs.railway.com/pricing/free-trial](https://docs.railway.com/pricing/free-trial), [plans](https://docs.railway.com/pricing/plans)): plan Free a 0 $ con "$1 of resource usage each month", sin tarjeta y sin acumular. Las cuentas nuevas reciben además una prueba única de 5 $ durante 30 días. Los servicios Free "sleep after 5 to 10 minutes without outbound traffic". Según la página [Serverless](https://docs.railway.com/reference/app-sleeping), al despertar la primera petición puede devolver 502, y entonces Meta reintenta. El plan Hobby cuesta 5 $/mes con 5 $ de uso incluidos.
- **Riesgo**: 1 $ al mes es muy poco. No he podido confirmar cuánto aguanta esta app con ese presupuesto, así que tendrías que medirlo.
- **Secretos**: variables en *Variables*. No he encontrado una función equivalente a los Secret Files, así que para el JSON habría que cambiar el código para leerlo de una variable, con `gspread.service_account_from_dict(json.loads(...))`.
- **Pasos**: *New Project → Deploy from GitHub repo* → variables → *Generate Domain* (HTTPS) → start command `uvicorn main:app --host 0.0.0.0 --port $PORT`.

### Fly.io
- **Free tier** ([docs.fly.io/about/free-trial](https://docs.fly.io/about/free-trial)): "Every new Fly.io account starts on the Free plan". Sin tarjeta tienes 1 $ de crédito que caduca a los 7 días; con tarjeta, 5 $ de uso al mes, hasta 3 máquinas. Si te pasas de los 5 $, pasa automáticamente a pago por uso. La página de [precios](https://docs.fly.io/about/pricing) dice en cambio que "All organizations ... require a credit card on file", así que en la práctica **cuenta con meter tarjeta**. La máquina más pequeña (`shared-cpu-1x`, 256 MB) cuesta 2,19 $/mes encendida en las regiones más baratas. No he comprobado si 256 MB bastan para esta app.
- **Secretos**: `fly secrets set CLAVE=valor`. Para el JSON, mismo cambio de código que en Railway, o escribir el archivo al arrancar.
- **Pasos**: instalar `flyctl` → `fly launch` (genera `fly.toml`) → `fly secrets set ...` → `fly deploy`.

### Google Cloud Run
- **Free tier** ([Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)): con facturación por petición, "2 million requests per month", "360,000 GB-seconds of memory, 180,000 vCPU-seconds" y 1 GB de salida desde Norteamérica al mes. Algunos resultados de búsqueda de la página de precios hablan de 240.000 vCPU-s y 450.000 GiB-s; [cloud.google.com/run/pricing](https://cloud.google.com/run/pricing) no se pudo leer, así que confírmalo allí. "A Google Cloud billing account is required", es decir, **tarjeta**.
- **Secretos** ([Cloud Run, secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)): guarda el JSON en Secret Manager y móntalo como archivo con `gcloud run deploy SERVICIO --source . --update-secrets=/etc/secrets/google.json=NOMBRE_SECRETO:latest`. Después pon `GOOGLE_CREDENCIALES=/etc/secrets/google.json`. La cuenta de servicio de Cloud Run necesita el rol `roles/secretmanager.secretAccessor`. Lo bueno es que encaja con el código actual.
- **Pros y contras**: es la opción más "profesional" para el CV y despierta más rápido que Render, pero configurar el proyecto, la facturación y los permisos IAM lleva más trabajo.

### Koyeb (descartado)
La página de [precios](https://www.koyeb.com/pricing) solo muestra planes de pago (Pro, desde 29 $/mes más cómputo). La [documentación de scale-to-zero](https://www.koyeb.com/docs/run-and-scale/scale-to-zero) aún menciona una "Free Instance" que se duerme tras 1 hora sin tráfico, pero **no he podido confirmar que siga disponible para cuentas nuevas**.

### Recomendación
1. **Ahora (demo de portfolio): Render Free.** Sin tarjeta y sin tocar el código, y un enlace HTTPS que puedes poner en el CV y en la web de chat pública. Avisa en el README de que el primer mensaje puede tardar alrededor de un minuto.
2. **Si lo usa un bar real:** Render de pago para que no se duerma (precio en [render.com/pricing](https://render.com/pricing), no consultado hoy) o Cloud Run. Elige según si prefieres sencillez o aprender GCP.

---

## 2. WhatsApp Cloud API: qué no puede hacer el número de prueba

### Límites del número de prueba
| Límite | Qué dice Meta | Fuente |
|---|---|---|
| **Máximo 5 destinatarios** | "you can send free messages to up to 5 recipient phone numbers". Cada número se añade y se verifica con un código que llega por WhatsApp. | [Get started (versión clásica)](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/), [Sandbox](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sandbox) |
| **No escribe a números no verificados** | El número de prueba "can only exchange messages and calls with phone numbers on its recipient list"; si no, error `131030`. | [Sandbox](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sandbox), [Changelog](https://developers.facebook.com/documentation/business-messaging/whatsapp/changelog/) |
| **Token temporal** | "expires quickly and is not suitable for development purposes". Un post oficial de Meta dice "expires in less than 24 hours". | [Get started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [Blog de Meta](https://developers.facebook.com/blog/post/2022/12/05/auth-tokens) |
| **Ventana de 24 h** | Solo puedes enviar mensajes libres (no plantilla) si el cliente te ha escrito en las últimas 24 h. Fuera de esa ventana, "businesses can only send template messages". Con el número de prueba se usa la plantilla `hello_world`. | [Pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) |
| **App en modo desarrollo** | "some webhooks will not be sent if your app is in Dev mode" | [Webhooks overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview) |
| **¿Puede pasar a producción?** | La documentación nueva no lo dice explícitamente. El número de prueba se "generated and registered for you automatically" y en producción se usa un número propio. No he encontrado una frase oficial que prohíba usarlo en producción, pero el límite de 5 destinatarios lo impide en la práctica. | [Phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers) |

Sin confirmar en fuentes oficiales: si el número de prueba permite cambiar el nombre visible y si los mensajes que *recibe* de números que no están en la lista llegan al webhook.

**Qué te bloqueaba, probablemente:** para que el asistente lo pruebe alguien que no está en tu lista (un cliente del bar, un reclutador o la demo pública) hace falta un número real. Con el de prueba, enviar a esa persona da `131030`. Si en cambio el fallo era que "dejó de funcionar de un día para otro", la causa es el token temporal (en `.env.example` ya pone que caduca cada día). Ese problema se arregla con el token permanente, sin número real.

### Token permanente (usuario del sistema)
Según [Access tokens](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens):
1. Ve a [business.facebook.com](https://business.facebook.com) → *Configuración del negocio* → *Usuarios del sistema* → *Añadir* (rol Admin o Empleado).
2. *Asignar activos*: tu **app**, con control total ("Manage app"), y tu **cuenta de WhatsApp**. Si es Empleado, también la cuenta de mensajería con acceso parcial o total. Sin esos activos, las llamadas devuelven el error 200.
3. Pulsa *Generar token*, elige la app, la **caducidad** ("token expiration preference"; Meta no detalla las opciones en esa página, pero según guías de terceros son 60 días o "nunca") y estos **3 permisos**:
   - `business_management`
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
4. Copia el token **una sola vez** a `WHATSAPP_TOKEN`, en el `.env` local y en las variables del hosting. No lo subas nunca a GitHub.

Funciona también con el número de prueba, así que es lo primero que conviene hacer, aunque no compres número.

### Usar un número real
Requisitos según [Business phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers) y [Display names](https://developers.facebook.com/documentation/business-messaging/whatsapp/display-names):
- **Número sin WhatsApp**: "Numbers already in use with WhatsApp cannot be registered unless they are deleted first". Si es el número del bar y ya usa WhatsApp Business App, hay que borrar esa cuenta antes, o usar otra línea.
- Tiene que ser tuyo, con prefijo de país y de zona (sin números cortos) y poder recibir **SMS o llamada** para el código de verificación.
- **PIN de verificación en dos pasos**, obligatorio al registrarlo.
- **Nombre visible**: se da al registrar el número y se revisa según las [directrices de nombre visible](https://www.facebook.com/business/help/757569725593362), que no he leído. Se puede cambiar 10 veces cada 30 días, y tras cada cambio aprobado hay que volver a registrar el número.
- **Verificación del negocio**: no es obligatoria para empezar, pero sin ella el portfolio empieza con un límite de **250** destinatarios únicos cada 24 h *fuera de la ventana de atención* y como máximo **2 números** registrados. Al verificar el negocio, el límite sube a 2.000 y los números a 20 ([Messaging limits](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits)). Para que un bar responda a quien le escribe, 250 es más que suficiente.
- **Método de pago** en la cuenta de WhatsApp (Billing Hub), si vas a pasar de la capa gratuita.

### Cuánto cuesta (según la página de precios de Meta, actualizada el 1 de octubre de 2026)
- Meta cobra **por mensaje entregado** desde el 1 de julio de 2025. Los mensajes que **el cliente** envía al negocio no se cobran.
- **Desde el 1 de octubre de 2026, los mensajes de servicio ya no son gratis sin límite:** "Meta provides 1,000 free service messages per month" por número, y cobra a partir del mensaje 1.001. Sin método de pago, Meta deja de entregarlos al agotarse los gratuitos. Las plantillas *utility* que se envían dentro de la ventana también se cobran desde esa fecha.
- Las respuestas del asistente a clientes que escriben primero son **mensajes de servicio**. Si un bar pequeño no pasa de 1.000 respuestas al mes por número, el coste de Meta sería 0 €. Es una deducción mía a partir de las reglas, no una cifra de Meta.
- **Precio por mensaje en España**: está en las *rate cards* (CSV/PDF) enlazadas desde la [página de precios](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing), que no he abierto. No pongo cifras hasta confirmarlas allí.
- El número en sí: Meta no cobra por registrarlo según lo que he leído, pero no he encontrado una frase oficial que lo diga. El coste real es la línea o SIM (lo que cobre tu operador) y, si algún día te pasas, los mensajes.
- Sin confirmar: si los mensajes del número de prueba cuentan para algo. La documentación clásica los llama "free messages".

**¿Merece la pena?** Solo si un bar real lo va a usar. Para el portfolio basta con el número de prueba, el token permanente y la web de chat pública: el reclutador prueba el chat web, y el vídeo o las capturas enseñan WhatsApp funcionando.

---

## 3. Checklist para más adelante

**Fase A — Demo pública (sin número real)**
- [ ] Crear el usuario del sistema y el token permanente (3 permisos) y ponerlo en `WHATSAPP_TOKEN`.
- [ ] Comprobar que `.env` y el JSON de Google no están en git (`git status`, `.gitignore`).
- [ ] Crear el Web Service en Render (Free): build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- [ ] Meter las variables en Render y subir el JSON como Secret File. Poner `GOOGLE_CREDENCIALES=/etc/secrets/<archivo>.json`.
- [ ] Compartir la hoja de Google con el email de la cuenta de servicio (si no estaba ya).
- [ ] Abrir `https://<servicio>.onrender.com/` y comprobar que responde.
- [ ] En Meta, configurar el webhook `https://<servicio>.onrender.com/webhook`, verificarlo y suscribirlo a `messages`.
- [ ] Enviar un WhatsApp desde un número de tu lista y comprobar la respuesta y la fila en Sheets.
- [ ] Poner en el README el enlace al chat web y avisar del arranque en frío (alrededor de 1 min).
- [ ] Revisar si conviene pasar la app de Meta a modo Live para recibir todos los webhooks.

**Fase B — Bar real (solo si alguien lo va a usar)**
- [ ] Conseguir un número sin WhatsApp (o borrar la cuenta de WhatsApp Business del bar) que reciba SMS o llamadas.
- [ ] Añadirlo en WhatsApp Manager con el nombre visible del bar y el PIN de dos pasos, y verificarlo por SMS o voz.
- [ ] Cambiar `WHATSAPP_PHONE_NUMBER_ID` por el ID del número nuevo.
- [ ] Añadir un método de pago en Billing Hub y consultar la rate card de España.
- [ ] Opcional: verificar el negocio para subir los límites.
- [ ] Pasar a una instancia que no se duerma (Render de pago o Cloud Run).
- [ ] Revisar la normativa de protección de datos (RGPD) para los datos de reservas de clientes reales.
