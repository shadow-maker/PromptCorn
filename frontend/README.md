
# PromptCorn - Frontend

Interfaz web de PromptCorn, un asistente cinematografico que permite descubrir peliculas, recibir recomendaciones y consultar donde verlas.

## 1. Tecnologias

- React 19
- Vite 8
- JavaScript
- CSS

## 2. Requisitos

- Node.js compatible con Vite 8
- npm

## 3. Instalacion

El frontend vive en la carpeta `frontend/` del repositorio del proyecto:

```bash
git clone https://github.com/shadow-maker/PromptCorn.git
cd PromptCorn/frontend
npm install
```

## 4. Configuracion

Crear un archivo `.env` a partir de `.env.example`.

Configurar la variable:

```env
VITE_API_URL=
```

Esta variable contendra la URL completa del endpoint `POST /chat` de la API del chat (contrato en `docs/contratos.md`).

Si se deja vacia, la aplicacion funciona en modo demostracion.

No guardar claves privadas ni credenciales en variables `VITE_`, porque son visibles desde el navegador.

## 5. Ejecucion local

```bash
npm run dev
```

## 6. Compilacion

```bash
npm run build
```

Los archivos de produccion se generan en `dist/`.

Para probar la compilacion:

```bash
npm run preview
```

## 7. Comunicacion con el backend

El frontend envia una solicitud HTTP POST con esta estructura:

```json
{
  "user_id": "usuario_identificado",
  "message": "Recomiendame una pelicula de ciencia ficcion"
}
```

Admite respuestas con los campos `response`, `message` o `respuesta`.

## 8. Funcionalidades

- Chat conversacional.
- Envio de mensajes.
- Indicador de procesamiento.
- Identificacion local del usuario.
- Nueva conversacion en la interfaz.
- Modo demostracion.
- Conexion configurable con API Gateway.

## 9. Estado del proyecto

El frontend funciona localmente en modo demostracion. La integracion real requiere configurar la URL de API Gateway y completar el despliegue coordinado del backend en AWS.
