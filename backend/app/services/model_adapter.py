from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


@dataclass
class ModelResult:
    content: str
    model: str


class ModelAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class ModelAdapter:
    def __init__(self, base_url: str, api_key: str, model_name: str, timeout_seconds: int = 45):
        self.base_url = normalize_model_base_url(base_url)
        self.api_key = api_key.strip()
        self.model_name = model_name.strip()
        self.timeout_seconds = timeout_seconds
        self.client = self._build_client()

    def generate(self, messages: list[dict[str, str]], locale: str) -> ModelResult:
        del locale

        if not self.api_key:
            raise ModelAPIError(
                "Model API key is not configured. Please set API Key (Token) in model configuration.",
                status_code=400,
            )

        if self._is_nvidia_endpoint():
            return self._generate_nvidia_stream(messages)
        return self._generate_standard(messages)

    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    def update_config(self, base_url: str, api_key: str, model_name: str) -> None:
        self.base_url = normalize_model_base_url(base_url)
        self.api_key = api_key.strip()
        self.model_name = model_name.strip()
        self.client = self._build_client()

    def _build_client(self) -> OpenAI:
        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout_seconds,
        )

    def _is_nvidia_endpoint(self) -> bool:
        return "integrate.api.nvidia.com" in self.base_url.lower()

    def _generate_standard(self, messages: list[dict[str, str]]) -> ModelResult:
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        except APIConnectionError as exc:
            raise ModelAPIError(
                "Failed to reach model API. Please check Base URL and network connectivity.",
                status_code=502,
            ) from exc
        except APITimeoutError as exc:
            raise ModelAPIError(
                "Model API request timed out. Please retry or increase timeout.",
                status_code=504,
            ) from exc
        except APIStatusError as exc:
            message = self._extract_status_error(exc)
            raise ModelAPIError(message, status_code=502) from exc

        choice = completion.choices[0] if completion.choices else None
        msg = choice.message if choice else None
        content = (msg.content or "").strip() if msg else ""
        if not content:
            raise ModelAPIError("Model API response is missing message content.", status_code=502)

        return ModelResult(content=content, model=(completion.model or self.model_name))

    def _generate_nvidia_stream(self, messages: list[dict[str, str]]) -> ModelResult:
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.2,
                top_p=1,
                max_tokens=16384,
                response_format={"type": "json_object"},
                extra_body={
                    "chat_template_kwargs": {
                        "enable_thinking": True,
                        "clear_thinking": False,
                    }
                },
                stream=True,
            )
        except APIConnectionError as exc:
            raise ModelAPIError(
                "Failed to reach model API. Please check Base URL and network connectivity.",
                status_code=502,
            ) from exc
        except APITimeoutError as exc:
            raise ModelAPIError(
                "Model API request timed out. Please retry or increase timeout.",
                status_code=504,
            ) from exc
        except APIStatusError as exc:
            message = self._extract_status_error(exc)
            raise ModelAPIError(message, status_code=502) from exc

        content_chunks: list[str] = []
        model_name = self.model_name

        try:
            for chunk in completion:
                if getattr(chunk, "model", None):
                    model_name = chunk.model

                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                if len(choices) == 0 or getattr(choices[0], "delta", None) is None:
                    continue

                delta = choices[0].delta
                text_part = getattr(delta, "content", None)
                if isinstance(text_part, str) and text_part:
                    content_chunks.append(text_part)
        except APIConnectionError as exc:
            raise ModelAPIError(
                "Streaming response was interrupted. Please check network connectivity and retry.",
                status_code=502,
            ) from exc

        content = "".join(content_chunks).strip()
        if not content:
            raise ModelAPIError("Model API response is missing message content.", status_code=502)

        return ModelResult(content=content, model=model_name)

    def _extract_status_error(self, exc: APIStatusError) -> str:
        status = getattr(exc, "status_code", None) or 500
        detail = ""

        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                if isinstance(payload.get("error"), dict):
                    detail = str(payload["error"].get("message") or "")
                if not detail and "message" in payload:
                    detail = str(payload.get("message") or "")
        except Exception:
            detail = str(getattr(exc.response, "text", "") or "").strip()

        if status in {401, 403}:
            base = "Model API authentication failed. Please verify API Key (Token)."
        elif status == 429:
            base = "Model API rate limit exceeded. Please retry later."
        elif 400 <= status < 500:
            base = "Model API request was rejected."
        else:
            base = "Model API returned an upstream server error."

        if detail:
            return f"{base} Upstream detail: {detail}"
        return f"{base} Upstream status: {status}."


def normalize_model_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return normalized

    while normalized.lower().endswith(CHAT_COMPLETIONS_SUFFIX):
        normalized = normalized[: -len(CHAT_COMPLETIONS_SUFFIX)].rstrip("/")

    return normalized
