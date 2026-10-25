import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from .config import Settings
from .llm import LLMError
from .smoke import run_smoke


def main():
    parser = argparse.ArgumentParser(description="Проверка соединения без медицинских данных")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--provider", choices=("mistral", "glm"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        settings = Settings.from_env(provider=args.provider, env_file=args.env_file).model_copy(update={"mode": args.mode})
        result = {"success": True, **run_smoke(settings).as_dict()}
        code = 0
    except (LLMError, ValidationError) as error:
        message = str(error) if isinstance(error, LLMError) else "Некорректные настройки; проверьте .env.example."
        result = {"success": False, "mode": args.mode, "error": message}
        code = 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
