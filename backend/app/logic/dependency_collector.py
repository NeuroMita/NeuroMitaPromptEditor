# File: backend\app\logic\dependency_collector.py
import re
import collections
from typing import Set, TYPE_CHECKING

if TYPE_CHECKING:
    from app.logic.path_resolver import AbstractPathResolver

# Regex patterns to find paths in DSL content
# 1. Placeholders: [<path.script>] or [<path.txt>]
PLACEHOLDER_RE = re.compile(r"\[<([^\]]+\.(?:script|txt))>]")

# 2. Inline LOAD: LOAD [TAG] FROM "path" or 'path'
INLINE_LOAD_RE = re.compile(r"""\bLOAD(?:\s+[A-Z0-9_]+)?\s+FROM\s+(['"])(.+?)\1""", re.IGNORECASE)

# 3. For RETURN statements, we look for LOAD clauses within their arguments
#    Matches: LOAD "path", LOAD TAG FROM "path", LOAD_REL "path"
#    This will be applied to the argument part of a RETURN line.
LOAD_IN_ARG_RE = re.compile(r"""\bLOAD\s+(?:[A-Z0-9_]+\s+FROM\s+)?(['"])(.+?)\1""", re.IGNORECASE)
LOAD_REL_IN_ARG_RE = re.compile(r"""\bLOAD_REL\s+(['"])(.+?)\1""", re.IGNORECASE)


class DslDependencyCollector:
    def __init__(self, resolver: 'AbstractPathResolver'):
        self.resolver = resolver
        # Assuming .script and .txt files are the ones that can contain further dependencies.
        self.parsable_extensions = ('.script', '.txt')

    def _is_parsable(self, resolved_path_id: str) -> bool:
        return any(resolved_path_id.lower().endswith(ext) for ext in self.parsable_extensions)

    def _parse_content_for_relative_paths(self, content: str) -> Set[str]:
        """
        Parses content and extracts all unique relative paths mentioned in
        placeholders or LOAD/LOAD_REL commands.
        """
        found_relative_paths: Set[str] = set()

        # Find placeholders [<...>]
        for match in PLACEHOLDER_RE.finditer(content):
            found_relative_paths.add(match.group(1))

        # Find inline LOAD ... FROM "..."
        for match in INLINE_LOAD_RE.finditer(content):
            found_relative_paths.add(match.group(2))
        
        # Find paths in RETURN statements
        # Split content into lines to process RETURN statements
        for line in content.splitlines():
            stripped_line = line.strip()
            if stripped_line.upper().startswith("RETURN "):
                args_part = stripped_line[len("RETURN "):].strip()
                
                for match in LOAD_IN_ARG_RE.finditer(args_part):
                    found_relative_paths.add(match.group(2))
                for match in LOAD_REL_IN_ARG_RE.finditer(args_part):
                    found_relative_paths.add(match.group(2))
        
        return found_relative_paths

    def collect_dependencies(self, entry_point_rel_path: str) -> Set[str]:
        """
        Collects all unique resolved path IDs for an entry point and its dependencies.

        Args:
            entry_point_rel_path: The relative path to the entry file (e.g., "main_template.txt")
                                  from the character's base data path or current resolver context.

        Returns:
            A set of unique resolved_path_ids (absolute paths or unique identifiers).
        """
        
        all_resolved_dependencies: Set[str] = set()
        
        # Queue stores resolved_path_ids to process
        # The resolver's initial context (pushed by Character model or API) should be the character's base data path.
        # So, resolving entry_point_rel_path initially should be correct.
        try:
            entry_point_resolved_id = self.resolver.resolve_path(entry_point_rel_path)
        except Exception as e: # PathResolverError
            # If the entry point itself cannot be resolved, return empty set or raise
            # For now, let's log and return empty, or re-raise as a specific collector error.
            # print(f"Could not resolve entry point '{entry_point_rel_path}': {e}")
            raise # Re-raise the PathResolverError

        queue = collections.deque([entry_point_resolved_id])
        visited_resolved_ids: Set[str] = set()

        while queue:
            current_resolved_id = queue.popleft()

            if current_resolved_id in visited_resolved_ids:
                continue
            
            visited_resolved_ids.add(current_resolved_id)
            all_resolved_dependencies.add(current_resolved_id)

            # Only parse files that can contain further dependencies
            if not self._is_parsable(current_resolved_id):
                continue

            try:
                content = self.resolver.load_text(current_resolved_id, f"dependency collection for {entry_point_rel_path}")
            except Exception as e: # PathResolverError
                # If a dependency can't be loaded, log it and skip.
                # Or, decide if this should be a critical error for the collection process.
                # print(f"Warning: Could not load dependency '{current_resolved_id}': {e}")
                continue # Skip this unreadable file

            relative_paths_in_current_file = self._parse_content_for_relative_paths(content)

            # Set context for resolving paths found *within* current_resolved_id
            current_file_dirname_id = self.resolver.get_dirname(current_resolved_id)
            self.resolver.push_base_context(current_file_dirname_id)
            
            for rel_path in relative_paths_in_current_file:
                try:
                    dependency_resolved_id = self.resolver.resolve_path(rel_path)
                    if dependency_resolved_id not in visited_resolved_ids:
                        queue.append(dependency_resolved_id)
                except Exception as e: # PathResolverError
                    # If a relative path inside a file can't be resolved, log and skip.
                    # print(f"Warning: Could not resolve path '{rel_path}' found in '{current_resolved_id}': {e}")
                    continue
            
            self.resolver.pop_base_context() # Restore previous context

        return all_resolved_dependencies