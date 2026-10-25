"""GLM through the user-selected FreeTheAI gateway, limited to two free routes."""
import json
import time

import httpx

from .config import FREE_GLM_MODELS, FREETHEAI_URL, Settings
from .llm import Completion, LLMError


class FreeGLMClient:
    def __init__(self, settings: Settings, *, transport=None):
        if settings.base_url != FREETHEAI_URL:
            raise LLMError('Для GLM разрешён только HTTPS API FreeTheAI.')
        if settings.model not in FREE_GLM_MODELS:
            raise LLMError('Разрешены только две настроенные бесплатные модели GLM.')
        self.settings = settings
        self.transport = transport

    def complete(self, system, payload, schema):
        key = self.settings.api_key.get_secret_value()
        if not key:
            raise LLMError('FREETHEAI_API_KEY не задан.')
        # The gateway forwards compatible fields but does not promise JSON Schema.
        # Request JSON in the prompt and validate locally; no silent repair call.
        request = {
            'model': self.settings.model,
            'temperature': self.settings.temperature,
            'max_tokens': self.settings.max_tokens,
            'stream': False,
            'messages': [
                {'role': 'system', 'content': system + '\nReturn only a JSON object matching this schema, without Markdown: '
                 + json.dumps(schema.model_json_schema(), ensure_ascii=False)},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
            ],
        }
        started = time.monotonic()
        try:
            with httpx.Client(timeout=httpx.Timeout(self.settings.timeout_seconds, connect=10),
                              transport=self.transport, follow_redirects=False) as client:
                response = client.post(FREETHEAI_URL + '/chat/completions', json=request,
                                       headers={'Authorization': 'Bearer ' + key})
        except httpx.HTTPError:
            raise LLMError('Сетевая ошибка FreeTheAI; повтор не выполнен. Расход квоты неизвестен.') from None
        if response.status_code != 200:
            # Bodies can echo prompts or credentials. Keep the error safe for logs.
            raise LLMError(f'FreeTheAI HTTP {response.status_code}; повтор и смена модели не выполнены.')
        try:
            body = response.json()
            choice = body['choices'][0]
            if choice['finish_reason'] != 'stop':
                raise LLMError('GLM не завершила ответ; частичный результат отклонён, повтор не выполнен.')
            content = choice['message']['content']
            if not isinstance(content, str):
                raise ValueError('Text expected')
            result = schema.model_validate_json(content)
            # Reject any accidental secret echo before persistence or UI output.
            if key in result.model_dump_json():
                raise ValueError('Sensitive output')
            model = body['model']
            if not isinstance(model, str) or not model or len(model) > 100 or key in model:
                raise ValueError('Invalid model')
            usage = {}
            for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                value = body.get('usage', {}).get(name)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    usage[name] = value
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            raise LLMError('GLM вернула ответ, не соответствующий схеме; повтор не выполнен.') from None
        return Completion(result, 'freetheai', model, 'live', 1,
                          round((time.monotonic() - started) * 1000), usage)
