import os
import requests
import json

class SimpleAIService:
    def __init__(self):
        self.provider = os.getenv('AI_PROVIDER', 'openai').lower()
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.openai_api_base = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        # Permitir configurar el modelo de Gemini por .env
        # Valores válidos comunes: gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro, y sus sufijos -latest
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash').strip()
        # Version de API: 'v1' o 'v1beta'
        self.gemini_api_version = os.getenv('GEMINI_API_VERSION', 'v1beta').strip()
        # Enviar API key por header como en el curl de muestra
        self.gemini_use_header_key = True
    
    def generate_response(self, question, context, conversation_history=None):
        """Genera una respuesta usando el proveedor de IA configurado"""
        try:
            # Construir el prompt del sistema
            system_prompt = """Eres un asistente inteligente especializado en responder preguntas sobre documentos PDF. 

Tu trabajo es:
1. Analizar el contenido de los documentos proporcionados
2. Responder preguntas específicas basándote únicamente en la información contenida en esos documentos
3. Si la información no está disponible en los documentos, indicarlo claramente
4. Proporcionar respuestas precisas, útiles y bien estructuradas
5. Citar el documento específico cuando sea relevante

Reglas importantes:
- Solo responde basándote en el contenido de los documentos proporcionados
- Si no encuentras la información en los documentos, di "No encuentro esa información en los documentos proporcionados"
- Sé preciso y conciso en tus respuestas
- Cuando sea posible, menciona de qué documento específico proviene la información"""

            if self.provider == 'openai' and self.openai_api_key:
                return self._generate_openai_response(system_prompt, question, context, conversation_history)
            elif self.provider == 'gemini' and self.gemini_api_key:
                return self._generate_gemini_response(system_prompt, question, context, conversation_history)
            else:
                return "Error: No se ha configurado correctamente el proveedor de IA. Por favor, configura las credenciales de OpenAI o Gemini."
                
        except Exception as e:
            print(f"Error generando respuesta de IA ({self.provider}): {str(e)}")
            return "Lo siento, hubo un error al procesar tu pregunta. Por favor, inténtalo de nuevo."
    
    def _generate_openai_response(self, system_prompt, question, context, conversation_history):
        """Genera respuesta usando OpenAI con requests"""
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Agregar historial de conversación si existe
        if conversation_history:
            for msg in conversation_history[-10:]:  # Últimos 10 mensajes
                role = "user" if msg.is_user else "assistant"
                messages.append({"role": role, "content": msg.content})
        
        # Agregar contexto de documentos
        if context.strip():
            context_message = f"CONTENIDO DE LOS DOCUMENTOS:\n\n{context}\n\nPREGUNTA DEL USUARIO: {question}"
        else:
            context_message = f"No hay documentos seleccionados. PREGUNTA DEL USUARIO: {question}"
        
        messages.append({"role": "user", "content": context_message})
        
        # Llamar a OpenAI usando requests
        headers = {
            'Authorization': f'Bearer {self.openai_api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-4o-mini',
            'messages': messages,
            'max_tokens': 1000,
            'temperature': 0.7
        }
        
        response = requests.post(
            f'{self.openai_api_base}/chat/completions',
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            return f"Error en la API de OpenAI: {response.status_code}"
    
    def _generate_gemini_response(self, system_prompt, question, context, conversation_history):
        """Genera respuesta usando Gemini con requests"""
        # Construir el prompt completo para Gemini
        full_prompt = f"{system_prompt}\n\n"
        
        # Agregar historial de conversación si existe
        if conversation_history:
            full_prompt += "HISTORIAL DE CONVERSACIÓN:\n"
            for msg in conversation_history[-10:]:  # Últimos 10 mensajes
                role = "Usuario" if msg.is_user else "Asistente"
                full_prompt += f"{role}: {msg.content}\n"
            full_prompt += "\n"
        
        # Agregar contexto de documentos
        if context.strip():
            full_prompt += f"CONTENIDO DE LOS DOCUMENTOS:\n\n{context}\n\n"
        else:
            full_prompt += "No hay documentos seleccionados.\n\n"
        
        full_prompt += f"PREGUNTA DEL USUARIO: {question}\n\nRESPUESTA:"
        
        # Llamar a Gemini usando requests (compatible con curl de muestra)
        model = self.gemini_model
        base = f"https://generativelanguage.googleapis.com/{self.gemini_api_version}"
        # Si usamos header para la API key, no la añadimos en la query
        if self.gemini_use_header_key:
            url = f"{base}/models/{model}:generateContent"
        else:
            url = f"{base}/models/{model}:generateContent?key={self.gemini_api_key}"
        
        headers = {
            'Content-Type': 'application/json'
        }
        if self.gemini_use_header_key:
            headers['X-goog-api-key'] = self.gemini_api_key
        
        # Estructura de contents como en el ejemplo de curl (sin 'role')
        data = {
            'contents': [{
                'parts': [{
                    'text': full_prompt
                }]
            }],
            'generationConfig': {
                'maxOutputTokens': 1000,
                'temperature': 0.7
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                return result['candidates'][0]['content']['parts'][0]['text']
            else:
                return "No se pudo generar una respuesta con Gemini."
        else:
            # Si hay 404 con alias '-latest', intentar sin '-latest' como fallback
            if response.status_code == 404 and model.endswith('-latest'):
                try:
                    fallback_model = model.replace('-latest', '')
                    if self.gemini_use_header_key:
                        fallback_url = f"{base}/models/{fallback_model}:generateContent"
                    else:
                        fallback_url = f"{base}/models/{fallback_model}:generateContent?key={self.gemini_api_key}"
                    fallback_resp = requests.post(fallback_url, headers=headers, json=data, timeout=30)
                    if fallback_resp.status_code == 200:
                        result = fallback_resp.json()
                        if 'candidates' in result and len(result['candidates']) > 0:
                            return result['candidates'][0]['content']['parts'][0]['text']
                    # Si el fallback también falla, devolver detalle
                    return (
                        f"Error en la API de Gemini (fallback {fallback_model}): "
                        f"{fallback_resp.status_code} - {fallback_resp.text}"
                    )
                except Exception as e:
                    return f"Error en la API de Gemini (fallback): {str(e)}"
            # Incluir el cuerpo de respuesta para mejor diagnóstico
            return f"Error en la API de Gemini: {response.status_code} - {response.text}"
    
    def get_provider_info(self):
        """Retorna información sobre el proveedor de IA actual"""
        return {
            'provider': self.provider,
            'model': 'gpt-4o-mini' if self.provider == 'openai' else self.gemini_model,
            'configured': (self.provider == 'openai' and bool(self.openai_api_key)) or 
                         (self.provider == 'gemini' and bool(self.gemini_api_key))
        }

# Instancia global del servicio de IA
ai_service = SimpleAIService()

