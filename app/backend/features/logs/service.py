from ...docker.compose import ComposeService
from ...stacks.models import StackDefinition


class LogsService:
    def __init__(self, compose_service: ComposeService, output_line_limit: int):
        self._compose = compose_service
        self._output_line_limit = output_line_limit

    def get_logs(self, stack: StackDefinition, tail: int = 200) -> dict:
        result = self._compose.logs(stack, tail=tail)
        return {
            "stack_id": stack.id,
            "success": result.exit_code == 0,
            "result": result.to_dict(self._output_line_limit),
        }
