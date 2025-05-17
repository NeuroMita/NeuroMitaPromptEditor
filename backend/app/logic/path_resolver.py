# File: backend\app\logic\path_resolver.py
from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING
import os
from pathlib import Path

if TYPE_CHECKING:
    pass

class PathResolverError(Exception):
    """Custom exception for path resolver issues."""
    def __init__(self, message: str, path: str | None = None, original_exception: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.path = path
        self.original_exception = original_exception

    def __str__(self):
        s = f"PathResolverError: {self.message}"
        if self.path:
            s += f" (Path: {self.path})"
        if self.original_exception:
            s += f" Caused by: {type(self.original_exception).__name__}: {self.original_exception}"
        return s

class AbstractPathResolver(ABC):
    @abstractmethod
    def __init__(self, global_prompts_root: str, character_base_data_path: str):
        self.global_prompts_root = os.path.abspath(global_prompts_root)
        self.character_base_data_path = os.path.abspath(character_base_data_path)
        self._context_dir_stack: List[str] = [] 

    @abstractmethod
    def resolve_path(self, rel_path: str) -> str:
        pass

    @abstractmethod
    def load_text(self, resolved_path_id: str, context_for_error_msg: str) -> str:
        pass

    @abstractmethod
    def get_dirname(self, resolved_path_id: str) -> str:
        pass

    def push_base_context(self, resolved_dir_path_id: str):
        if not os.path.isabs(resolved_dir_path_id):
            raise PathResolverError(f"Context path must be absolute: {resolved_dir_path_id}")
        self._context_dir_stack.append(resolved_dir_path_id)

    def pop_base_context(self):
        if not self._context_dir_stack:
            raise PathResolverError("Attempted to pop from an empty context directory stack.")
        self._context_dir_stack.pop()

    def _get_current_context_dir(self) -> str:
        if self._context_dir_stack:
            return self._context_dir_stack[-1]
        return self.character_base_data_path

class LocalPathResolver(AbstractPathResolver):
    def __init__(self, global_prompts_root: str, character_base_data_path: str):
        super().__init__(global_prompts_root, character_base_data_path)
        if not os.path.isabs(self.global_prompts_root):
            raise ValueError("LocalPathResolver: global_prompts_root must be an absolute path.")
        if not os.path.isabs(self.character_base_data_path):
            raise ValueError("LocalPathResolver: character_base_data_path must be an absolute path.")
        
        norm_global_root = os.path.normpath(self.global_prompts_root)
        norm_char_base = os.path.normpath(self.character_base_data_path)

        if not (norm_char_base.startswith(norm_global_root + os.sep) or norm_char_base == norm_global_root):
            try:
                if os.path.commonpath([norm_global_root, norm_char_base]) != norm_global_root:
                    raise PathResolverError(
                        f"Security Error: Character base path '{norm_char_base}' "
                        f"is outside the global prompts root '{norm_global_root}'.",
                        path=norm_char_base
                    )
            except ValueError: 
                 raise PathResolverError(
                    f"Security Error: Character base path '{norm_char_base}' cannot be reconciled with "
                    f"global prompts root '{norm_global_root}' (e.g. different drives).",
                    path=norm_char_base
                )

    def _secure_join(self, base_abs_path: str, rel_path_segment: str) -> str:
        # This function now assumes base_abs_path is the correct base to join with.
        # The logic to prevent "Scripts/Scripts" type duplication, if still needed due to
        # DslInterpreter's specific calling patterns for execute_dsl_script,
        # might need to be here or handled by how rel_path_segment is passed to it.
        # For now, let's assume resolve_path picks the correct base.
        
        combined_path = os.path.join(base_abs_path, rel_path_segment)
        norm_combined_abs_path = os.path.normpath(os.path.abspath(combined_path))
        norm_global_root = os.path.normpath(self.global_prompts_root)

        if not (norm_combined_abs_path.startswith(norm_global_root + os.sep) or norm_combined_abs_path == norm_global_root):
            try:
                if os.path.commonpath([norm_global_root, norm_combined_abs_path]) != norm_global_root:
                    raise PathResolverError(
                        f"Security Error: Path '{norm_combined_abs_path}' (from base '{base_abs_path}' and segment '{rel_path_segment}') "
                        f"is outside the allowed global prompts root '{norm_global_root}'.",
                        path=norm_combined_abs_path
                    )
            except ValueError:
                 raise PathResolverError(
                    f"Security Error: Path '{norm_combined_abs_path}' cannot be safely combined with Prompts root '{norm_global_root}'.",
                    path=norm_combined_abs_path
                )
        return norm_combined_abs_path

    def resolve_path(self, rel_path: str) -> str:
        if os.path.isabs(rel_path):
            raise PathResolverError(f"Absolute paths are not permitted for DSL resolution: '{rel_path}'", path=rel_path)

        # Normalize the input relative path for consistent checking
        norm_rel_path = os.path.normpath(rel_path)

        # 1. Paths starting with _Common* are relative to global_prompts_root
        if norm_rel_path.startswith(("_CommonPrompts" + os.sep, "_CommonScripts" + os.sep)) or \
           norm_rel_path == "_CommonPrompts" or norm_rel_path == "_CommonScripts": # Handle if it's just the dir name
            return self._secure_join(self.global_prompts_root, norm_rel_path)
        
        # 2. Paths starting with './' or '../' are relative to the current context directory
        # (directory of the file currently being processed by DslInterpreter)
        if norm_rel_path.startswith("." + os.sep) or norm_rel_path.startswith(".." + os.sep):
            current_script_dir_context = self._get_current_context_dir()
            return self._secure_join(current_script_dir_context, norm_rel_path)

        # 3. All other paths (e.g., "Scripts/file.txt", "Main/data.txt") are considered
        #    relative to the character's base data path. This is the crucial change.
        #    The DslInterpreter's context stack is for explicit relative paths (./, ../).
        #    Implicitly root-relative paths use character_base_data_path.
        
        # Before joining with character_base_data_path, we need to handle the "Scripts/Scripts" case
        # if rel_path itself is something like "Scripts/file.script" and character_base_data_path
        # is ".../CharDir" and the DslInterpreter is calling execute_dsl_script with "Scripts/file.script".
        # This specific scenario was addressed by the previous _secure_join modification.
        # Let's re-integrate that logic carefully.

        # The DslInterpreter calls `resolver.resolve_path(rel_path_placeholder)` first.
        # If rel_path_placeholder is "Scripts/foo.script", and current context is char_base_path,
        # it resolves to "char_base_path/Scripts/foo.script".
        # Then DslInterpreter calls `execute_dsl_script(rel_path_placeholder)`.
        # Inside execute_dsl_script, it calls `resolver.resolve_path(rel_script_path)` again
        # where rel_script_path is "Scripts/foo.script".
        # The context is now "char_base_path/Scripts".
        # If this rule #3 applies, it would try to resolve "Scripts/foo.script" against "char_base_path",
        # leading to "char_base_path/Scripts/foo.script", which is correct.

        # The problem arises if `_secure_join` *itself* tries to be too smart and re-strips "Scripts".
        # The previous `_secure_join` logic:
        # base_name = Path(base_abs_path).name
        # rel_path_parts = Path(os.path.normpath(rel_path_segment)).parts
        # if rel_path_parts and base_name == rel_path_parts[0] and len(rel_path_parts) > 1:
        #    effective_rel_path_segment = str(Path(*rel_path_parts[1:]))
        # This logic should ONLY apply if `base_abs_path` is the *current script context* and `rel_path_segment`
        # is the *original placeholder path* being re-resolved by `execute_dsl_script`.

        # Let's simplify _secure_join and put path interpretation solely in resolve_path.
        # _secure_join will just join and secure.

        # If we are here, it's not _Common*, not ./, not ../.
        # These paths are meant to be relative to the character's root.
        return self._secure_join(self.character_base_data_path, norm_rel_path)


    def load_text(self, resolved_path_id: str, context_for_error_msg: str) -> str:
        try:
            if not os.path.isfile(resolved_path_id):
                raise FileNotFoundError(f"Path is not a file or does not exist: {resolved_path_id}")
            with open(resolved_path_id, 'r', encoding='utf-8') as f:
                return f.read().rstrip()
        except FileNotFoundError as e:
            raise PathResolverError(f"File not found '{os.path.basename(resolved_path_id)}' (context: {context_for_error_msg}, full path: {resolved_path_id})", path=resolved_path_id, original_exception=e) from e
        except Exception as e: 
            raise PathResolverError(f"Error reading file '{os.path.basename(resolved_path_id)}' (context: {context_for_error_msg}, full path: {resolved_path_id})", path=resolved_path_id, original_exception=e) from e

    def get_dirname(self, resolved_path_id: str) -> str:
        dir_name = os.path.dirname(resolved_path_id)
        norm_dir_name = os.path.normpath(dir_name)
        norm_global_root = os.path.normpath(self.global_prompts_root)

        if not (norm_dir_name.startswith(norm_global_root + os.sep) or norm_dir_name == norm_global_root):
            try:
                if os.path.commonpath([norm_global_root, norm_dir_name]) != norm_global_root:
                    raise PathResolverError(
                        f"Security Error: Derived directory name '{norm_dir_name}' (from '{resolved_path_id}') is outside the global prompts root '{norm_global_root}'.",
                        path=norm_dir_name
                    )
            except ValueError:
                raise PathResolverError(
                    f"Security Error: Derived directory name '{norm_dir_name}' cannot be reconciled with global prompts root '{norm_global_root}'.",
                    path=norm_dir_name
                )
        return norm_dir_name

class RemotePathResolver(AbstractPathResolver):
    def __init__(self, global_prompts_root_url: str, character_base_data_path_segment: str, api_token: str | None = None):
        self.global_prompts_root_url = global_prompts_root_url.rstrip('/')
        self.character_base_url = f"{self.global_prompts_root_url}/{character_base_data_path_segment.strip('/')}"
        super().__init__(self.global_prompts_root_url, self.character_base_url)
        self.api_token = api_token

    def _construct_url(self, base_url: str, path_segment: str) -> str:
        from urllib.parse import urljoin
        if not base_url.endswith('/'):
            base_url_for_join = base_url + '/'
        else:
            base_url_for_join = base_url
        return urljoin(base_url_for_join, path_segment)

    def resolve_path(self, rel_path: str) -> str:
        # This logic would need similar careful consideration for remote paths
        norm_rel_path = rel_path # Basic normalization for URLs might be different
        
        if norm_rel_path.startswith(("_CommonPrompts/", "_CommonScripts/")):
            return self._construct_url(self.global_prompts_root_url, norm_rel_path)
        
        if norm_rel_path.startswith("./") or norm_rel_path.startswith("../"):
            current_script_dir_context_url = self._get_current_context_dir() # This is a URL
            return self._construct_url(current_script_dir_context_url, norm_rel_path)
            
        # Default to character base URL for other paths
        return self._construct_url(self.character_base_url, norm_rel_path)


    def load_text(self, resolved_path_id_url: str, context_for_error_msg: str) -> str:
        # Placeholder for actual HTTP GET request
        if "error" in resolved_path_id_url.lower():
            raise PathResolverError(f"Simulated error loading remote resource '{resolved_path_id_url}'", path=resolved_path_id_url)
        if "notfound" in resolved_path_id_url.lower():
            raise PathResolverError(f"Simulated 404 for remote resource '{resolved_path_id_url}'", path=resolved_path_id_url, original_exception=FileNotFoundError("Mock HTTP 404"))
        return f"Content from remote URL: {resolved_path_id_url}\n(Original context: {context_for_error_msg})"

    def get_dirname(self, resolved_path_id_url: str) -> str:
        from urllib.parse import urlparse, urlunparse
        parsed_url = urlparse(resolved_path_id_url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        if len(path_parts) <= 1 and path_parts[0] == '':
            return urlunparse((parsed_url.scheme, parsed_url.netloc, '/', '', '', ''))

        dir_path_parts = path_parts[:-1]
        dir_path_str = "/".join(dir_path_parts)
        
        if dir_path_str:
            full_dir_path = f"/{dir_path_str}/"
        else: 
            full_dir_path = "/" 
        return urlunparse((parsed_url.scheme, parsed_url.netloc, full_dir_path, '', '', ''))